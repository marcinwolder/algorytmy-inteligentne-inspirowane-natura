"""WP6: reference solution with OR-Tools CP-SAT (best_known for N = 25, docs 8.4, D10).

Model: a circuit over nodes 0..N (a self-loop = venue not visited). Times are integers in units
of 0.1 min; profit and opening are tables per whole minute of arrival. Waiting is not allowed, so
an arc (i, j) fixes A_j = A_i + s_i + t_ij.

The discrete model is close to the continuous one, but not equal (D10). The route from CP-SAT is
always scored again with evaluate_route; the gap to it can be slightly negative.
Traffic events are not supported here (best_known is needed only for E1, which has no events).
"""

from __future__ import annotations

import time

import numpy as np
from ortools.sat.python import cp_model

from antroute.model.evaluate import crowd_value, eval_route_kernel, is_open, profit_value
from antroute.solvers.result import SolverResult

TS = 10            # time units per minute
PSCALE = 100_000   # profit scale


def cpsat(problem, time_limit: float = 60.0, workers: int = 8, hint: list[int] | None = None,
          ) -> SolverResult:
    if problem.traffic.shape[0] > 0:
        raise ValueError("CP-SAT model does not support traffic events")
    if problem.start_node != 0:
        raise ValueError("CP-SAT model supports start at node 0 only")
    t_start = time.perf_counter()
    n1 = problem.n + 1
    t0 = int(round(problem.start_time))
    horizon = int(np.floor(problem.deadline)) - t0
    T = np.rint(problem.T * TS).astype(int)
    stay = np.rint(problem.stay * TS).astype(int)

    m = cp_model.CpModel()
    lit = {}
    arcs = []
    for i in range(n1):
        for j in range(n1):
            if i != j:
                lit[i, j] = m.NewBoolVar(f"x{i}_{j}")
                arcs.append((i, j, lit[i, j]))
    visit = [None] + [m.NewBoolVar(f"v{j}") for j in range(1, n1)]
    for j in range(1, n1):
        arcs.append((j, j, visit[j].Not()))
        if not problem.allowed[j]:
            m.Add(visit[j] == 0)
    m.AddCircuit(arcs)

    # redundant knapsack-like budget cut: it makes the LP bound much tighter
    m.Add(sum(x * int(T[i, j] + stay[i]) for (i, j), x in lit.items())
          <= int(np.floor((problem.deadline - problem.start_time) * TS)))

    A = [m.NewIntVar(t0 * TS, int(problem.deadline * TS), f"A{j}") for j in range(n1)]
    m.Add(A[0] == t0 * TS)
    for (i, j), x in lit.items():
        if j == 0:
            m.Add(A[i] + stay[i] + T[i, 0] <= int(np.floor(problem.deadline * TS))).OnlyEnforceIf(x)
        else:
            m.Add(A[j] == A[i] + stay[i] + T[i, j]).OnlyEnforceIf(x)

    prof_vars = []
    for j in range(1, n1):
        if not problem.allowed[j]:
            continue
        mins = np.arange(t0, t0 + horizon + 1, dtype=float)
        cr = np.array([crowd_value(problem.prof, problem.cat, problem.surge, problem.anchor, j, t)
                       for t in mins])
        ptab = [int(round(profit_value(problem.base_profit[j], problem.lam, c) * PSCALE))
                for c in cr]
        otab = [int(is_open(problem.prof, problem.cat, problem.closure, problem.anchor,
                            problem.thr, j, t, t + problem.stay[j])) for t in mins]
        minute = m.NewIntVar(t0, t0 + horizon, f"m{j}")
        m.AddDivisionEquality(minute, A[j], TS)
        idx = m.NewIntVar(0, horizon, f"i{j}")
        m.Add(idx == minute - t0)
        raw = m.NewIntVar(0, max(ptab), f"r{j}")
        m.AddElement(idx, ptab, raw)
        op = m.NewBoolVar(f"o{j}")
        m.AddElement(idx, otab, op)
        m.AddImplication(visit[j], op)
        pj = m.NewIntVar(0, max(ptab), f"p{j}")
        m.Add(pj <= raw)
        m.Add(pj == 0).OnlyEnforceIf(visit[j].Not())
        prof_vars.append(pj)
    for c in range(len(problem.categories)):
        nodes = [visit[j] for j in range(1, n1) if problem.cat[j] == c]
        if nodes:
            m.Add(sum(nodes) <= int(problem.kcap[c] - problem.kc_used[c]))
    m.Maximize(sum(prof_vars))

    if hint:
        nxt = {0: hint[0] if hint else 0}
        for a, b in zip(hint, hint[1:] + [0], strict=True):
            nxt[a] = b
        for (i, j), x in lit.items():
            m.AddHint(x, nxt.get(i) == j)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    status = solver.Solve(m)
    route: list[int] = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        cur = 0
        while True:
            nxt_j = next(j for j in range(n1) if j != cur and solver.Value(lit[cur, j]))
            if nxt_j == 0:
                break
            route.append(nxt_j)
            cur = nxt_j
    r = np.asarray(route, dtype=np.int64)
    profit, code, *_ = eval_route_kernel(problem.arrays(), r)
    return SolverResult(
        route=route, profit=float(profit), method="cpsat", time_s=time.perf_counter() - t_start,
        info={"status": solver.StatusName(status), "objective": solver.ObjectiveValue() / PSCALE,
              "bound": solver.BestObjectiveBound() / PSCALE, "feasible_continuous": code == 0})
