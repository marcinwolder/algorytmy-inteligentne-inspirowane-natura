"""WP9: experiment runner. Config YAML -> list of jobs -> parallel runs -> results/<E>/results.csv.

Usage:
  python -m antroute.experiments.run E1 E2 E4 E5 E6 E7 E8 E10 E11 E12 [--processes 9]
  python -m antroute.experiments.run E1 --seeds 3 --out results_quick     # smoke run

E3 (ACS-A vs ACS-B) and E9 (crowd avoidance) are analyses of E1; E13 (antipheromone) is an
analysis of E10-E12. All of them are produced by antroute.report.summary.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from antroute.config import ROOT, fmt_hhmm, parse_hhmm
from antroute.experiments import common
from antroute.experiments.common import cfg, get_instance, run_jobs
from antroute.model.evaluate import evaluate_route
from antroute.model.problem import Problem
from antroute.solvers.aco import aco_params, acs

CONFIGS = Path(__file__).parent / "configs"
MUSEUMS = ("Museum", "Art Museum")


def load(name: str) -> dict:
    with open(CONFIGS / f"{name}.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def seeds_of(n: int, args) -> range:
    return range(args.seeds if args.seeds else n)


# ---------------------------------------------------------------- E1 (+E3, E9)

def jobs_e1(c: dict, args) -> list[dict]:
    jobs = []
    g = c["grid"]
    for sp, t0, b, n in itertools.product(g["start_point"], g["t0"], g["budget"], g["n"]):
        base = {"exp": "E1", "n": n, "start_point": sp, "t0": t0, "budget": b,
                "persona": c["persona"], "day_type": c["day_type"]}
        for m in c["methods"]:
            seeds = [0] if m in c.get("deterministic", []) else seeds_of(c["seeds"], args)
            jobs += [{**base, "method": m, "seed": s} for s in seeds]
    return jobs


def jobs_e1_cpsat(c: dict, out: Path) -> list[dict]:
    """CP-SAT for N in cpsat.n with a hint = best acs_ls route of E1 (best_known, D10)."""
    df = pd.read_csv(out / "E1" / "results.csv")
    jobs = []
    for (sp, t0, b, n), grp in df[df["method"] == "acs_ls"].groupby(
            ["start_point", "t0", "budget", "n"]):
        if n not in c["cpsat"]["n"]:
            continue
        best = grp.loc[grp["profit"].idxmax()]
        hint = [] if pd.isna(best["route"]) else str(best["route"]).split(";")
        jobs.append({"exp": "E1", "n": int(n), "start_point": sp, "t0": t0, "budget": int(b),
                     "persona": c["persona"], "day_type": c["day_type"], "method": "cpsat",
                     "seed": 0, "hint_ids": hint,
                     "override": {"time_limit": c["cpsat"]["time_limit"],
                                  "workers": c["cpsat"]["workers"]}})
    return jobs


# ---------------------------------------------------------------- E2, E4

def jobs_e2(c: dict, args) -> list[dict]:
    jobs = []
    for inst in c["instances"]:
        for label, spec in c["methods"].items():
            ov = {"iterations": c["iterations"], "time_limit_s": 600, **spec.get("override", {})}
            jobs += [{"exp": "E2", **inst, "persona": c["persona"], "day_type": c["day_type"],
                      "method": spec["variant"], "label": label, "override": ov, "seed": s,
                      "record_history": True} for s in seeds_of(c["seeds"], args)]
    return jobs


def jobs_e4(c: dict, args) -> list[dict]:
    jobs = []
    g, d = c["grid"], c["design"]
    for inst in c["instances"]:
        base = {"exp": "E4", **inst, "persona": c["persona"], "day_type": c["day_type"],
                "method": "acs_a"}
        for beta, q0, m, lam in itertools.product(g["beta"], g["q0"], g["m"], g["lam"]):
            jobs += [{**base, "label": "grid", "lam": lam,
                      "override": {"beta": beta, "q0": q0, "m": m}, "seed": s,
                      "extra": {"beta": beta, "q0": q0, "m": m}}
                     for s in seeds_of(c["seeds"], args)]
        for tm, ls, q0 in itertools.product(d["tau0_mode"], d["local_search"], d["q0"]):
            jobs += [{**base, "label": "design",
                      "override": {"tau0_mode": tm, "local_search": ls, "q0": q0}, "seed": s,
                      "extra": {"tau0_mode": tm, "local_search": ls, "q0": q0}}
                     for s in seeds_of(c["seeds"], args)]
    return jobs


# ---------------------------------------------------------------- E5-E8

def jobs_e5_e8(c: dict, which: str, args) -> list[dict]:
    e, dt = c[which], c["day_type"]
    jobs = []
    if which == "E5":
        for t0 in e["t0"]:
            jobs += [{"exp": "E5", "n": e["n"], "start_point": e["start_point"], "t0": t0,
                      "budget": e["budget"], "persona": e["persona"], "day_type": dt,
                      "method": e["method"], "seed": s} for s in seeds_of(e["seeds"], args)]
    elif which == "E6":
        base = {"exp": "E6", "n": e["n"], "start_point": e["start_point"], "t0": e["t0"],
                "budget": e["budget"], "day_type": dt, "method": e["method"]}
        for p in e["personas"]:
            jobs += [{**base, "persona": p, "seed": s}
                     for s in seeds_of(e["seeds_named"], args)]
        rng = np.random.default_rng(0)
        cats = list(cfg()["data"]["categories"])
        for k in range(e["random_personas"] if not args.seeds else 5):
            u = {c_: round(float(x), 4) for c_, x in zip(cats, rng.uniform(0, 1, len(cats)),
                                                         strict=True)}
            jobs += [{**base, "persona": u, "persona_name": f"random_{k:03d}", "seed": s}
                     for s in seeds_of(e["seeds_random"], args)]
    elif which == "E7":
        for sp in e["start_points"]:
            jobs += [{"exp": "E7", "n": e["n"], "start_point": sp, "t0": e["t0"],
                      "budget": e["budget"], "persona": e["persona"], "day_type": dt,
                      "method": e["method"], "seed": s} for s in seeds_of(e["seeds"], args)]
    elif which == "E8":
        keys = ["profiles"] + [f"bootstrap_{b:02d}" for b in range(e["bootstrap"])]
        for key in keys:
            jobs += [{"exp": "E8", "n": e["n"], "start_point": e["start_point"], "t0": e["t0"],
                      "budget": e["budget"], "persona": e["persona"], "day_type": dt,
                      "method": e["method"], "profiles_key": key, "eval_profiles_key": "profiles",
                      "seed": s} for s in seeds_of(e["seeds"], args)]
    return jobs


# ---------------------------------------------------------------- E10-E12 (+E13)

def baseline_routes(cm: dict, t0: str, seeds=range(5)):
    inst = get_instance(cm["n"], cm["start_point"])
    p = Problem.build(inst, cfg(), cm["persona"], parse_hhmm(t0), float(cm["budget"]),
                      day_type=cm["day_type"])
    out = []
    for s in seeds:
        r = acs(p, aco_params(cfg(), "acs_ls"), seed=s)
        out.append(evaluate_route(p, r.route))
    return inst, out


def pick_planned_after(cm: dict, t0: str, after: float, before: float) -> tuple[str, float]:
    """Event target (E10, E11): a venue that the no-event plan (acs_ls, seed 0) visits in
    [after, before); museums first, then the earliest visit in the window."""
    _, reps = baseline_routes(cm, t0, seeds=[0])
    rows = reps[0].rows
    inside = [r for r in rows if after <= r["arrival"] < before]
    pool = ([r for r in inside if r["category"] in MUSEUMS] or inside
            or [r for r in rows if r["arrival"] >= after])
    if not pool:
        raise RuntimeError("the morning plan has no visit after the announcement")
    return pool[0]["venue_id"], pool[0]["arrival"]


def event_jobs(exp: str, cm: dict, t0: str, scenario: dict | None, methods: list[str], args,
               target: str | None = None, window=None, extra=None, warm_modes=(True,),
               record_history=False) -> list[dict]:
    base = {"exp": exp, "n": cm["n"], "start_point": cm["start_point"], "t0": t0,
            "budget": cm["budget"], "persona": cm["persona"], "day_type": cm["day_type"],
            "scenario": scenario, "target": target, "target_window": window,
            "extra": extra or {}, "record_history": record_history}
    jobs = []
    for m in methods:
        warms = warm_modes if m.startswith("acs") else (True,)
        for w in warms:
            label = m if len(warms) == 1 else f"{m}_{'warm' if w else 'cold'}"
            seeds = [0] if m == "greedy" else seeds_of(cm["seeds"], args)
            jobs += [{**base, "method": m, "label": label, "warm": w, "seed": s} for s in seeds]
    return jobs


def jobs_events(c: dict, which: str, args, info: dict) -> list[dict]:
    cm = c["common"]
    e = c[which]
    jobs = []
    if which == "E10":
        win = [parse_hhmm(x) for x in e["window"]]
        info["E10_target"] = {}
        for t0 in e["t0"]:
            # the venue that the no-event plan visits inside the event window (museums first)
            museum, arr = pick_planned_after(cm, t0, max(win[0], parse_hhmm(t0)), win[1])
            info["E10_target"][t0] = {"venue": museum, "planned_arrival": fmt_hhmm(arr)}
            jobs += event_jobs("E10", cm, t0, {"name": "none", "events": []}, ["acs_ls"], args,
                               museum, win, {"decay_min": 0})
            for td in e["decay_min"]:
                sc = {"name": f"free_museum_td{td}", "events": [
                    {"type": "crowd_surge", "venue": museum, "window": e["window"],
                     "strength": e["strength"], "decay_min": td}]}
                jobs += event_jobs("E10", cm, t0, sc, e["methods"], args, museum, win,
                                   {"decay_min": td})
    elif which == "E11":
        ann = parse_hhmm(e["announced"])
        target, arr = pick_planned_after(cm, e["t0"], ann, parse_hhmm(e["window"][1]))
        info["E11_target"] = {"venue": target, "planned_arrival": fmt_hhmm(arr)}
        win = [parse_hhmm(x) for x in e["window"]]
        ev = {"type": "crowd_surge", "venue": target, "window": e["window"],
              "strength": e["strength"], "decay_min": e["decay_min"]}
        jobs += event_jobs("E11", cm, e["t0"], {"name": "none", "events": []}, ["acs_ls"], args,
                           target, win)
        jobs += event_jobs("E11", cm, e["t0"], {"name": "surge_known", "events": [ev]},
                           ["acs_ls"], args, target, win)
        jobs += event_jobs("E11", cm, e["t0"],
                           {"name": "surge_announced",
                            "events": [{**ev, "announced": e["announced"]}]},
                           e["methods"], args, target, win, warm_modes=(True, False),
                           record_history=True)
    elif which == "E13b":
        cm = {**cm, "n": e["n"]}
        ann = parse_hhmm(e["announced"])
        inst, reps = baseline_routes(cm, e["t0"], seeds=[0])
        rep = reps[0]
        nodes = [0] + rep.route + [0]
        deps = [parse_hhmm(e["t0"])] + [r["arrival"] + r["stay"] for r in rep.rows]
        k = next(i for i, d in enumerate(deps) if d > ann and nodes[i + 1] != 0)
        a, b = nodes[k], nodes[k + 1]
        center = [float((inst.lat[a] + inst.lat[b]) / 2), float((inst.lon[a] + inst.lon[b]) / 2)]
        venue = inst.venue_ids[b]
        info["E13b_target"] = {"walk_from": inst.venue_ids[a], "venue": venue,
                               "planned_departure": fmt_hhmm(deps[k]), "center": center}
        base_ev = {"window": e["window"], "announced": e["announced"]}
        scenarios = {
            "accident": {"type": "traffic", "center": center, **e["accident"], **base_ev},
            "closure": {"type": "closure", "venue": venue, **base_ev},
            "surge": {"type": "crowd_surge", "venue": venue, **e["surge"], **base_ev},
        }
        for name, ev in scenarios.items():
            for label, spec in e["methods"].items():
                for iters in e["replan_iterations"]:
                    for warm in e["warm"]:
                        lab = f"{label}_it{iters}_{'warm' if warm else 'cold'}"
                        ov = {**spec.get("override", {}), "replan_iterations": iters}
                        jobs += [{"exp": "E13b", "n": cm["n"], "start_point": cm["start_point"],
                                  "t0": e["t0"], "budget": cm["budget"], "persona": cm["persona"],
                                  "day_type": cm["day_type"],
                                  "scenario": {"name": name, "events": [ev]},
                                  "method": spec["variant"], "label": lab, "override": ov,
                                  "warm": warm, "seed": s, "target": venue,
                                  "record_history": "replan",
                                  "extra": {"group": label, "replan_it": iters}}
                                 for s in seeds_of(cm["seeds"], args)]
    elif which == "E12":
        _, reps = baseline_routes(cm, e["t0"], seeds=[0])
        first = reps[0].rows[0]["venue_id"]
        info["E12_closed_venue"] = first
        closure = {"type": "closure", "venue": first, "window": e["closure_window"]}
        parade = {"type": "traffic", **e["parade"]}
        for name, evs in (("none", []), ("closure", [closure]), ("parade", [parade]),
                          ("closure+parade", [closure, parade])):
            methods = ["acs_ls"] if name == "none" else e["methods"]
            jobs += event_jobs("E12", cm, e["t0"], {"name": name, "events": evs}, methods, args,
                               first)
    return jobs


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("experiments", nargs="+")
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--seeds", type=int, default=None, help="override the number of seeds")
    ap.add_argument("--out", default="results")
    ap.add_argument("--no-cpsat", action="store_true")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    info_path = out / "experiment_info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    info["code_version"] = common.code_version()

    for e in args.experiments:
        hist = None
        if e == "E1":
            c = load("E1")
            jobs = jobs_e1(c, args)
        elif e == "E2":
            c = load("E2")
            jobs = jobs_e2(c, args)
            hist = out / "E2" / "histories.jsonl"
        elif e == "E4":
            jobs = jobs_e4(load("E4"), args)
        elif e in ("E5", "E6", "E7", "E8"):
            jobs = jobs_e5_e8(load("E5_E8"), e, args)
        elif e in ("E10", "E11", "E12", "E13b"):
            jobs = jobs_events(load("E10_E13"), e, args, info)
            if e in ("E11", "E13b"):
                hist = out / e / "histories.jsonl"
        else:
            raise SystemExit(f"unknown experiment {e}")
        if hist is not None:
            hist.parent.mkdir(parents=True, exist_ok=True)
        run_jobs(jobs, out / e / "results.csv", args.processes, hist)
        if e == "E1" and not args.no_cpsat:
            run_jobs(jobs_e1_cpsat(c, out), out / "E1" / "results.csv", processes=1)
        info_path.write_text(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
