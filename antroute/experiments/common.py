"""WP9: job execution shared by all experiments.

A job is a plain dict (instance, user, scenario, method, seed). :func:`run_job` builds the problem,
plans the day (with replanning when the scenario has announcements) and scores the final route
on the ground-truth problem with :func:`antroute.model.evaluate.evaluate_route`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

from antroute.config import ROOT, load_config, parse_hhmm
from antroute.model.evaluate import evaluate_route
from antroute.model.instance import build_instance
from antroute.model.problem import Problem
from antroute.scenario.events import load_scenario
from antroute.solvers.aco import aco_params, acs
from antroute.solvers.greedy import greedy
from antroute.solvers.random_route import random_route
from antroute.solvers.replan import plan_day

RESULTS = ROOT / "results"
_CFG: dict | None = None


def cfg() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = load_config()
    return _CFG


@lru_cache(maxsize=64)
def get_instance(n: int, start_point: str, include: tuple = (), profiles_key: str = "profiles",
                 seed: int | None = None):
    return build_instance(n, start_point, seed=seed, cfg=cfg(), include=list(include),
                          profiles_key=profiles_key)


def job_key(job: dict) -> str:
    """Stable id of a job (used to skip jobs that already have a result)."""
    keep = {k: v for k, v in job.items() if k not in ("extra", "record_history")}
    return hashlib.sha1(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:16]


def build_problem(job: dict) -> Problem:
    sc = load_scenario(job.get("scenario"))
    inst = get_instance(job["n"], job["start_point"], tuple(sorted(sc.venue_ids())),
                        job.get("profiles_key", "profiles"), job.get("instance_seed"))
    return Problem.build(inst, cfg(), job.get("persona", "culture"), parse_hhmm(job["t0"]),
                         float(job["budget"]), day_type=job.get("day_type"),
                         lam=job.get("lam"), scenario=sc)


def make_solver(method: str, seed: int, override: dict | None, hint=None):
    """Return solve(problem, state, first) -> (result, state) for :func:`plan_day`."""
    if method == "random":
        return lambda p, st, first: (random_route(p, seed), None)
    if method == "greedy":
        return lambda p, st, first: (greedy(p), None)
    if method == "cpsat":
        from antroute.solvers.exact import cpsat

        tl = (override or {}).get("time_limit", 120)
        workers = (override or {}).get("workers", 8)
        return lambda p, st, first: (cpsat(p, time_limit=tl, workers=workers, hint=hint), None)
    params = aco_params(cfg(), method, override)

    def solve(p, st, first):
        kw = {}
        if not first:
            kw["iterations"] = params["replan_iterations"]
            if st is not None:
                kw["tau"], kw["phi_ants"] = st.tau, st.phi_ants
        res = acs(p, params, seed=seed, **kw)
        return res, res

    return solve


def run_job(job: dict) -> dict:
    """Run one job and return one result row (+ optional histories)."""
    problem = build_problem(job)
    truth = problem.with_events(None)
    if job["method"] == "fixed":
        # the plan made without any event knowledge (acs_ls), followed without changes
        blind = problem.replace(scenario=None).with_events(None)    # no events at all
        solve0 = make_solver("acs_ls", int(job.get("seed", 0)), job.get("override"))
        day = plan_day(blind, solve0)
    else:
        hint = [problem.instance.node_of(v) for v in job.get("hint_ids") or []] or None
        solve = make_solver(job["method"], int(job.get("seed", 0)), job.get("override"), hint)
        day = plan_day(problem, solve, warm=job.get("warm", True))
    rep = evaluate_route(truth, day.route)
    theta = cfg()["aco"]["theta"]
    first = day.plans[0]["result"]
    row = {
        "key": job_key(job), "exp": job["exp"], "method": job["method"],
        "variant_label": job.get("label", job["method"]), "n": job["n"],
        "start_point": job["start_point"], "t0": job["t0"], "budget": job["budget"],
        "persona": job.get("persona_name", job.get("persona", "culture")),
        "day_type": problem.scenario.day_type if job.get("day_type") is None else job["day_type"],
        "lam": problem.lam, "profiles_key": job.get("profiles_key", "profiles"),
        "scenario": (job.get("scenario") or {}).get("name", "none"),
        "warm": job.get("warm", True), "seed": job.get("seed", 0),
        "profit": rep.profit, "solver_profit": first.profit, "feasible": rep.feasible,
        "violation": rep.violation, "n_visits": len(rep.route), "avg_crowd": rep.avg_crowd,
        "peak_visits": int((rep.crowds > theta).sum()), "budget_use": rep.budget_use,
        "time_s": day.time_s, "iterations": first.iterations,
        "route": ";".join(problem.venue_ids[j] for j in rep.route),
        "categories": ";".join(r["category"] for r in rep.rows),
        "arrivals": ";".join(f"{a:.1f}" for a in rep.arrivals),
    }
    if job["method"] == "cpsat":
        row.update({f"cpsat_{k}": v for k, v in first.info.items()})
    target = job.get("target")
    if target is not None:
        node = problem.instance.node_of(target)
        win = job.get("target_window")
        row["target_visited"] = node in rep.route
        row["target_arrival"] = (float(rep.arrivals[rep.route.index(node)])
                                 if node in rep.route else np.nan)
        if win:
            a = row["target_arrival"]
            row["target_in_window"] = bool(node in rep.route and win[0] <= a < win[1])
    if len(day.plans) > 1:
        rp = day.plans[1]
        row["replanned_at"] = rp["t"]
        row["committed"] = len(rp.get("committed", []))
        if rp.get("result") is not None:
            row["replan_profit"] = rp["result"].profit
            row["replan_greedy"] = rp["result"].info.get("greedy_profit", np.nan)
    if job.get("eval_profiles_key"):
        full = build_problem({**job, "profiles_key": job["eval_profiles_key"]}).with_events(None)
        row["profit_full_data"] = evaluate_route(full, day.route).profit
    row.update(job.get("extra", {}))
    out = {"row": row}
    if job.get("record_history"):
        if job["record_history"] != "replan":
            out["history"] = list(first.history)
        if len(day.plans) > 1 and day.plans[1].get("result") is not None:
            out["replan_history"] = list(day.plans[1]["result"].history)
    return out


def _worker_init():
    os.environ.setdefault("NUMBA_NUM_THREADS", "1")


def run_jobs(jobs: list[dict], out_csv: Path, processes: int | None = None,
             histories: Path | None = None) -> None:
    """Run jobs in parallel, append rows to ``out_csv``; skip jobs whose key is already there."""
    import multiprocessing as mp

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_csv.exists():
        with open(out_csv, newline="", encoding="utf-8") as fh:
            done = {r["key"] for r in csv.DictReader(fh)}
    todo = [j for j in jobs if job_key(j) not in done]
    print(f"{out_csv.parent.name}: {len(jobs)} jobs, {len(done)} done, {len(todo)} to run",
          flush=True)
    if not todo:
        return
    processes = processes or max(1, (os.cpu_count() or 2) - 1)
    rows_written = 0
    fieldnames: list[str] | None = None
    if out_csv.exists() and done:
        with open(out_csv, newline="", encoding="utf-8") as fh:
            fieldnames = next(csv.reader(fh))
    hist_fh = open(histories, "a", encoding="utf-8") if histories else None   # noqa: SIM115
    try:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes, initializer=_worker_init) as pool:
            for res in pool.imap_unordered(run_job, todo, chunksize=1):
                row = res["row"]
                if fieldnames is None:
                    fieldnames = list(row)
                    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
                        csv.DictWriter(fh, fieldnames=fieldnames).writeheader()
                extra = [k for k in row if k not in fieldnames]
                if extra:
                    _widen_csv(out_csv, fieldnames, extra)
                    fieldnames += extra
                with open(out_csv, "a", newline="", encoding="utf-8") as fh:
                    csv.DictWriter(fh, fieldnames=fieldnames).writerow(row)
                if hist_fh is not None:
                    for name in ("history", "replan_history"):
                        if name in res:
                            hist_fh.write(json.dumps({"key": row["key"], "kind": name,
                                                      "method": row["method"],
                                                      "label": row["variant_label"],
                                                      "seed": row["seed"], "values": res[name]})
                                          + "\n")
                rows_written += 1
                if rows_written % max(1, len(todo) // 10) == 0:
                    print(f"  {rows_written}/{len(todo)}", flush=True)
    finally:
        if hist_fh is not None:
            hist_fh.close()


def _widen_csv(path: Path, fieldnames: list[str], extra: list[str]) -> None:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames + extra)
        w.writeheader()
        w.writerows(rows)


def code_version() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
                             capture_output=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True,
                               capture_output=True, check=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
