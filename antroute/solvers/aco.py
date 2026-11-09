"""WP7: Ant Colony System for the crowd-aware TDOP (docs/04-algorytm.md).

Variants (all through parameters):
  ACS-A      one pheromone matrix + antipheromone            time_bins_tau=1
  ACS-B      pheromone per 3 h bin of the day                time_bins_tau=8
  ACS-noφ    no antipheromone                                gamma=0
  ACS-static no crowd penalty in the solver                  solver_lam=0 (scoring keeps lambda)
  ACS-LS     ACS-A + local search on the iteration best      local_search=true (D9)

Usage (one scenario):
  python -m antroute.solvers.aco --n 50 --start 08:00 --budget 480 --seed 1 \
      --scenario antroute/scenario/examples/free_museum_morning.yaml
"""

from __future__ import annotations

import time
from collections.abc import Callable

import numpy as np

from antroute.model.evaluate import surge_value
from antroute.solvers.greedy import greedy
from antroute.solvers.kernels import (
    BETA,
    BIN_MIN,
    DPHI,
    GAMMA,
    N_PRM,
    PSI,
    Q0,
    TAU0,
    THETA,
    global_update,
    local_search,
    run_ants,
    seed_rng,
)
from antroute.solvers.result import SolverResult

VARIANTS = {
    "acs_a": {},                                     # parameters from docs 4.7 (q0 = 0.9)
    "acs_b": {"time_bins_tau": 8},
    "acs_ls": {"local_search": True, "q0": 0.5},     # main method: D9 + q0 tuned (E4, K4)
    "nophi": {"gamma": 0.0},
    "static": {"solver_lam": 0.0},
    "b": {"time_bins_tau": 8},
    "acs_nophi": {"gamma": 0.0},
    "acs_static": {"solver_lam": 0.0},
    "phidoc": {"phi_event_types": ["crowd_surge"]},   # docs 4.4: event antipheromone only for surges
}


def tau0_value(profit_greedy: float, n: int, mode: str) -> float:
    """D1: 'profit_over_n' -> Profit_greedy / N; 'doc' -> 1 / (N * Profit_greedy) (docs 4.3)."""
    pg = max(profit_greedy, 1e-6)
    if mode == "profit_over_n":
        return pg / n
    if mode == "doc":
        return 1.0 / (n * pg)
    raise ValueError(f"unknown tau0_mode {mode!r}")


EVENT_TYPES = ("crowd_surge", "closure", "traffic")


def event_antipheromone(problem, phi_max: float, bin_min: float, nbins: int,
                        types=EVENT_TYPES) -> np.ndarray:
    """Antipheromone from the events the planner knows, per (venue, time bin).

    crowd_surge: phi_max * E_j(b), E at the middle of the bin (docs 4.4).
    closure:     phi_max on the closed venue in every bin that overlaps the window.
    traffic:     phi_max * (1 - 1/m) on venues inside the area, in bins that overlap the window
                 (m = factor; a road that is practically closed gives almost phi_max).
    The docs version uses only crowd_surge (``types=["crowd_surge"]``).
    """
    phi = np.zeros((problem.n + 1, nbins))
    starts = np.arange(nbins) * bin_min
    mids = starts + 0.5 * bin_min

    def overlap(ts, te):
        return (starts < te) & (starts + bin_min > ts)

    if "crowd_surge" in types:
        for j in {int(v) for v in problem.surge[:, 0]}:
            phi[j] += phi_max * np.array([surge_value(problem.surge, j, t) for t in mids])
    if "closure" in types:
        for j, ts, te in problem.closure:
            phi[int(j), overlap(ts, te)] += phi_max
    if "traffic" in types:
        for k, (ts, te, factor) in enumerate(problem.traffic):
            phi[np.ix_(problem.tnode[k], overlap(ts, te))] += phi_max * (1.0 - 1.0 / factor)
    return phi


def make_prm(a: dict, tau0: float) -> np.ndarray:
    prm = np.zeros(N_PRM)
    prm[BETA], prm[Q0], prm[PSI], prm[TAU0] = a["beta"], a["q0"], a["psi"], tau0
    prm[GAMMA], prm[DPHI], prm[THETA] = a["gamma"], a["dphi"], a["theta"]
    prm[BIN_MIN] = a["bin_minutes"]
    return prm


def acs(problem, aco: dict, seed: int = 0, iterations: int | None = None,
        time_limit: float | None = None, tau: np.ndarray | None = None,
        phi_ants: np.ndarray | None = None,
        on_iteration: Callable[[int, SolverResult, np.ndarray, np.ndarray], None] | None = None,
        ) -> SolverResult:
    """Run ACS on ``problem`` (the problem as the planner sees it).

    ``aco`` is the ``aco`` config section (+ ``bin_minutes``, ``horizon_minutes`` and optional
    ``solver_lam``). ``tau``/``phi_ants`` give a warm start (docs 4.5); ``tau`` is then smoothed
    with kappa towards the new tau0.
    """
    t_start = time.perf_counter()
    iterations = aco["iterations"] if iterations is None else iterations
    time_limit = aco["time_limit_s"] if time_limit is None else time_limit
    solver_problem = problem
    if aco.get("solver_lam") is not None:
        solver_problem = problem.replace(lam=float(aco["solver_lam"]))
    P = solver_problem.arrays()
    n1 = problem.n + 1
    n_venues = max(int(problem.allowed.sum()), 1)
    nb = int(aco.get("time_bins_tau", 1))
    nbins = int(aco["horizon_minutes"] // aco["bin_minutes"])

    seed_rng(seed)
    g = greedy(solver_problem)
    tau0 = tau0_value(g.profit, n_venues, aco["tau0_mode"])
    if tau is None:
        tau = np.full((nb, n1, n1), tau0)
    else:
        tau = (1.0 - aco["kappa"]) * tau + aco["kappa"] * tau0
    phi_ants = np.zeros((n1, nbins)) if phi_ants is None else phi_ants.copy()
    phi_ev = event_antipheromone(solver_problem, aco["phi_max"], aco["bin_minutes"], nbins,
                                 aco.get("phi_event_types", EVENT_TYPES))
    prm = make_prm(aco, tau0)

    best_r = np.asarray(g.route, dtype=np.int64)
    best_p = g.profit
    history: list[float] = []
    ls_done: set[tuple] = set()
    it = 0
    for it in range(1, iterations + 1):
        routes, lens, profits = run_ants(P, tau, phi_ev, phi_ants, prm, int(aco["m"]))
        a = int(np.argmax(profits))
        it_r, it_p = routes[a, :lens[a]].copy(), float(profits[a])
        if aco.get("local_search") and tuple(it_r) not in ls_done:
            ls_done.add(tuple(it_r))
            it_r, it_p = local_search(P, it_r, 50)
        if it_p > best_p + 1e-12:
            best_r, best_p = it_r, float(it_p)
        global_update(P, tau, best_r, best_p, aco["rho"])
        phi_ants *= 1.0 - aco["rho_phi"]
        history.append(best_p)
        if on_iteration is not None:
            snap = SolverResult(route=best_r.tolist(), profit=best_p, method="acs", iterations=it)
            on_iteration(it, snap, tau, phi_ev + phi_ants)
        if time.perf_counter() - t_start > time_limit:
            break
    return SolverResult(route=best_r.tolist(), profit=best_p, method="acs",
                        time_s=time.perf_counter() - t_start, iterations=it, history=history,
                        tau=tau, phi_ants=phi_ants, tau0=tau0,
                        info={"greedy_profit": g.profit})


def aco_params(cfg: dict, variant: str = "acs_a", override: dict | None = None) -> dict:
    """The ``aco`` config section merged with model constants, a variant and an override.

    Variants combine with '+', e.g. ``"acs_ls+nophi"`` = main method without antipheromone.
    """
    a = dict(cfg["aco"])
    a["bin_minutes"] = cfg["model"]["bin_minutes"]
    a["horizon_minutes"] = cfg["model"]["horizon_minutes"]
    for part in variant.split("+"):
        if part not in VARIANTS:
            raise ValueError(f"unknown ACS variant {part!r}")
        a.update(VARIANTS[part])
    a.update(override or {})
    return a


def main() -> None:
    import argparse
    import json

    from antroute.config import fmt_hhmm, load_config, parse_hhmm
    from antroute.model.evaluate import evaluate_route
    from antroute.model.instance import build_instance
    from antroute.model.problem import Problem
    from antroute.scenario.events import load_scenario
    from antroute.solvers.replan import plan_day

    ap = argparse.ArgumentParser(description="Run ACS for one scenario")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--start-point", default="times_square")
    ap.add_argument("--start", default="08:00")
    ap.add_argument("--budget", type=float, default=480)
    ap.add_argument("--persona", default="culture")
    ap.add_argument("--variant", default="acs_ls", help="variant, e.g. acs_ls or acs_ls+nophi")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--scenario", default=None)
    ap.add_argument("--warm", action="store_true", help="warm start after an announced event")
    ap.add_argument("--out", default=None, help="JSON output file")
    a = ap.parse_args()

    cfg = load_config()
    scenario = load_scenario(a.scenario)
    inst = build_instance(a.n, a.start_point, cfg=cfg, include=scenario.venue_ids())
    problem = Problem.build(inst, cfg, a.persona, parse_hhmm(a.start), a.budget,
                            scenario=scenario)
    params = aco_params(cfg, a.variant)
    day = plan_day(problem, lambda p, st, first: acs_solve(p, st, first, params, a.seed),
                   warm=a.warm)
    rep = evaluate_route(problem.with_events(None), day.route)
    for r in rep.rows:
        print(f"{fmt_hhmm(r['arrival'])}  {r['category']:20s} {r['venue_id']}  "
              f"crowd={r['crowd']:.2f}  profit={r['profit']:.3f}")
    print(f"profit={rep.profit:.4f} feasible={rep.feasible} ({rep.violation}) "
          f"back={fmt_hhmm(rep.end_time)} budget_use={rep.budget_use:.2f}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"profit": rep.profit, "feasible": rep.feasible, "rows": rep.rows}, fh,
                      indent=1)


def acs_solve(problem, state, first: bool, params: dict, seed: int):
    """Adapter for :func:`antroute.solvers.replan.plan_day`."""
    kw = {}
    if not first:
        kw["iterations"] = params["replan_iterations"]
        if state is not None:
            kw["tau"], kw["phi_ants"] = state.tau, state.phi_ants
    res = acs(problem, params, seed=seed, **kw)
    return res, res


if __name__ == "__main__":
    main()
