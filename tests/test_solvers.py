"""WP6-WP8: solvers against the oracle (K4), determinism (K7), one scoring function, replanning."""

from __future__ import annotations

import numpy as np
import pytest
from conftest import make_problem, random_instance

from antroute.model.evaluate import evaluate_route
from antroute.scenario.events import load_scenario
from antroute.solvers.aco import aco_params, acs, acs_solve
from antroute.solvers.brute import brute_force
from antroute.solvers.greedy import greedy
from antroute.solvers.random_route import random_route
from antroute.solvers.replan import plan_day


def small_aco(cfg, variant="acs_a", **kw):
    return aco_params(cfg, variant, {"iterations": 200, "time_limit_s": 30, **kw})


def oracle_cases(cfg, count=20, n=7):
    rng = np.random.default_rng(42)
    for _ in range(count):
        inst = random_instance(rng, n)
        yield make_problem(inst, cfg, start=float(rng.choice([480, 600, 720])),
                           budget=float(rng.choice([240, 360])))


def test_k4_acs_finds_brute_force_optimum(cfg):
    """K4 for the main method (ACS-LS). ACS-A with the docs parameters (q0 = 0.9) reaches only
    about 70% here; it is checked only to never exceed the optimum."""
    hits, runs = 0, 0
    for p in oracle_cases(cfg):
        best = brute_force(p)
        for seed in range(3):
            r = acs(p, aco_params(cfg, "acs_ls", {"iterations": 500}), seed=seed)
            a = acs(p, small_aco(cfg, "acs_a"), seed=seed)
            assert r.profit <= best.profit + 1e-9 and a.profit <= best.profit + 1e-9
            hits += r.profit >= best.profit - 1e-9
            runs += 1
    assert hits / runs >= 0.95, f"ACS-LS found the optimum in {hits}/{runs} runs"


def test_every_solver_route_is_feasible_and_profit_matches_evaluate(cfg):
    for p in oracle_cases(cfg, count=8):
        for res in (greedy(p), random_route(p, 3), acs(p, small_aco(cfg), seed=1),
                    acs(p, small_aco(cfg, "acs_ls"), seed=1),
                    acs(p, small_aco(cfg, "acs_b"), seed=1), brute_force(p)):
            rep = evaluate_route(p, res.route)
            assert rep.feasible, (res.method, rep.violation)
            assert rep.profit == pytest.approx(res.profit, abs=1e-12)


def test_acs_never_worse_than_greedy(cfg):
    for p in oracle_cases(cfg, count=8):
        assert acs(p, small_aco(cfg), seed=0).profit >= greedy(p).profit - 1e-12


def test_k7_same_seed_same_route(cfg):
    p = next(oracle_cases(cfg, count=1, n=8))
    for variant in ("acs_a", "acs_ls", "acs_b"):
        a = acs(p, small_aco(cfg, variant), seed=5)
        b = acs(p, small_aco(cfg, variant), seed=5)
        assert a.route == b.route and a.history == b.history
    assert random_route(p, 9).route == random_route(p, 9).route


def test_zero_antipheromone_has_no_effect(cfg):
    """gamma = 0 or phi = 0 gives the same run as ACS without antipheromone."""
    p = next(oracle_cases(cfg, count=1, n=8))
    no_phi = acs(p, small_aco(cfg, gamma=0.0), seed=3)
    phi_never = acs(p, small_aco(cfg, theta=10.0), seed=3)   # ants never deposit, no events
    assert no_phi.history == phi_never.history and no_phi.route == phi_never.route


def test_static_variant_is_scored_with_true_lambda(cfg):
    p = next(oracle_cases(cfg, count=1, n=8))
    r = acs(p, small_aco(cfg, "acs_static"), seed=0)
    rep = evaluate_route(p, r.route)
    lam0 = evaluate_route(p.replace(lam=0.0), r.route)
    assert r.profit == pytest.approx(lam0.profit)       # solver objective ignores crowd
    assert rep.profit <= lam0.profit + 1e-12


def test_surge_creates_event_antipheromone_and_moves_visit(cfg):
    rng = np.random.default_rng(7)
    inst = random_instance(rng, 8)
    p0 = make_problem(inst, cfg, start=600.0, budget=240.0)
    base = acs(p0, small_aco(cfg), seed=0)
    target = base.route[0]
    sc = load_scenario({"events": [{"type": "crowd_surge", "venue": f"v{target}",
                                    "window": ["09:00", "18:00"], "strength": 1.0}]})
    p1 = make_problem(inst, cfg, start=600.0, budget=240.0, scenario=sc)
    res = acs(p1, small_aco(cfg, lam=1.0), seed=0)
    hit = make_problem(inst, cfg, start=600.0, budget=240.0, scenario=sc, lam=1.0)
    rep = evaluate_route(hit, res.route)
    # with lambda = 1 and C >= 1 the venue gives no profit, so it is never worth a visit
    assert target not in res.route or rep.profits[res.route.index(target)] == 0.0


def test_replanning_keeps_committed_prefix(cfg):
    rng = np.random.default_rng(11)
    inst = random_instance(rng, 9)
    p0 = make_problem(inst, cfg, start=540.0, budget=360.0)
    params = small_aco(cfg)
    morning = acs(p0, params, seed=2)
    assert len(morning.route) >= 2
    target = morning.route[-1]
    sc = load_scenario({"events": [{"type": "closure", "venue": f"v{target}",
                                    "window": ["09:00", "23:00"], "announced": "10:00"}]})
    p = make_problem(inst, cfg, start=540.0, budget=360.0, scenario=sc)
    for warm in (False, True):
        day = plan_day(p, lambda q, st, first: acs_solve(q, st, first, params, 2), warm=warm)
        assert day.plans[0]["result"].route == morning.route     # event unknown in the morning
        assert len(day.plans) == 2
        committed = day.plans[1]["committed"]
        assert 1 <= len(committed) < len(morning.route)
        assert committed == morning.route[: len(committed)]       # D7: prefix kept as it was
        assert day.route[: len(committed)] == committed
        assert target not in committed
        assert target not in day.route                            # closed venue dropped
        rep = evaluate_route(p.with_events(None), day.route)
        assert rep.feasible, rep.violation


def test_replanning_drops_walk_to_venue_closed_during_the_walk(cfg):
    """D7 regression: the user walks to a venue that closes now -> do not go there."""
    from antroute.config import fmt_hhmm

    rng = np.random.default_rng(11)
    inst = random_instance(rng, 9)
    p0 = make_problem(inst, cfg, start=540.0, budget=360.0)
    params = small_aco(cfg)
    morning = acs(p0, params, seed=2)
    rep = evaluate_route(p0, morning.route)
    leave = rep.arrivals[0] + p0.stay[morning.route[0]]
    ta = (leave + rep.arrivals[1]) / 2                      # in the middle of the 2nd walk
    target = morning.route[1]
    sc = load_scenario({"events": [{"type": "closure", "venue": f"v{target}",
                                    "window": [fmt_hhmm(ta), "23:00"],
                                    "announced": fmt_hhmm(ta)}]})
    p = make_problem(inst, cfg, start=540.0, budget=360.0, scenario=sc)
    day = plan_day(p, lambda q, st, first: acs_solve(q, st, first, params, 2), warm=True)
    assert day.plans[1]["committed"] == morning.route[:1]
    assert day.plans[1]["start_node"] == morning.route[0]
    assert target not in day.route
    final = evaluate_route(p.with_events(None), day.route)
    assert final.feasible, final.violation


def test_cpsat_matches_brute_force(cfg):
    pytest.importorskip("ortools")
    from antroute.solvers.exact import cpsat

    for p in oracle_cases(cfg, count=4, n=6):
        best = brute_force(p)
        cp = cpsat(p, time_limit=20, workers=4)
        assert cp.info["feasible_continuous"]
        assert cp.profit == pytest.approx(best.profit, rel=0.01)


def test_event_antipheromone_for_all_event_types(cfg):
    from antroute.solvers.aco import event_antipheromone

    inst = random_instance(np.random.default_rng(3), 6)
    lat, lon = float(inst.lat[2]), float(inst.lon[2])
    sc = load_scenario({"events": [
        {"type": "crowd_surge", "venue": "v1", "window": ["10:00", "11:00"], "strength": 0.5},
        {"type": "closure", "venue": "v3", "window": ["12:00", "13:00"]},
        {"type": "traffic", "center": [lat, lon], "radius_m": 50, "window": ["14:00", "15:00"],
         "factor": 4.0}]})
    p = make_problem(inst, cfg, scenario=sc)
    phi = event_antipheromone(p, 5.0, 30.0, 96)

    def b(hour):                                      # 30-min bin that starts at a full hour
        return hour * 2

    assert phi[1, b(10)] == pytest.approx(2.5)                   # phi_max * s
    assert phi[3, b(12)] == pytest.approx(5.0) and phi[3, b(12) + 1] == pytest.approx(5.0)
    assert phi[3, b(13)] == 0.0                                   # window is [12:00, 13:00)
    assert phi[2, b(14)] == pytest.approx(5.0 * (1 - 1 / 4.0))    # venue inside the area
    assert phi[0].sum() == 0.0                                    # start node never marked
    assert phi[2, b(16)] == 0.0
    doc = event_antipheromone(p, 5.0, 30.0, 96, types=["crowd_surge"])
    assert doc[3].sum() == 0.0 and doc[2].sum() == 0.0 and doc[1, b(10)] == pytest.approx(2.5)
