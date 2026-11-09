"""Exhaustive search over all feasible venue sequences. Test oracle for N <= 8 (WP6)."""

from __future__ import annotations

import time

import numpy as np

from antroute.model.evaluate import (
    crowd_value,
    eval_route_kernel,
    feasible_candidates,
    profit_value,
)
from antroute.solvers.result import SolverResult

MAX_N = 9


def brute_force(problem, max_n: int = MAX_N) -> SolverResult:
    """Depth-first search over every feasible route; returns an optimal route."""
    if problem.n > max_n:
        raise ValueError(f"brute force is limited to N <= {max_n}")
    t_start = time.perf_counter()
    P = problem.arrays()
    n1 = problem.n + 1
    best = {"p": 0.0, "r": []}
    count = [0]

    def dfs(cur, t, visited, kc, route, profit):
        count[0] += 1
        if profit > best["p"] + 1e-12:
            best["p"], best["r"] = profit, list(route)
        cj, carr, ctt = np.empty(n1, np.int64), np.empty(n1), np.empty(n1)
        cnt = feasible_candidates(P, cur, t, visited, kc, cj, carr, ctt)
        for q in range(cnt):
            j, arr = int(cj[q]), float(carr[q])
            s = profit_value(problem.base_profit[j], problem.lam,
                             crowd_value(problem.prof, problem.cat, problem.surge,
                                         problem.anchor, j, arr))
            visited[j] = True
            kc[problem.cat[j]] += 1
            route.append(j)
            dfs(j, arr + problem.stay[j], visited, kc, route, profit + s)
            route.pop()
            kc[problem.cat[j]] -= 1
            visited[j] = False

    dfs(problem.start_node, problem.start_time, np.zeros(n1, dtype=np.bool_),
        problem.kc_used.copy(), [], 0.0)
    r = np.asarray(best["r"], dtype=np.int64)
    return SolverResult(route=best["r"], profit=float(eval_route_kernel(P, r)[0]), method="brute",
                        time_s=time.perf_counter() - t_start, info={"nodes": count[0]})
