"""WP4: the single source of truth for the model (docs/03-model.md, docs/05 5.1).

Every solver uses these kernels to compute travel times, crowd, profit and feasibility, and every
route is finally scored by :func:`evaluate_route`. A bug here changes every result, so each formula
has a unit test in tests/test_evaluate.py.

Time is in minutes from midnight of the planning day (values above 1440 mean the next day).

The kernels take a tuple ``P`` built by :meth:`antroute.model.problem.Problem.arrays`:

    P = (T, cat, stay, base_profit, kcap, prof, lam, thr, anchor,
         surge, closure, traffic, tmask, start_node, start_time, deadline, allowed, kc_used)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numba import njit

# feasibility codes returned by eval_route_kernel
OK, DUPLICATE, NOT_ALLOWED, CATEGORY_LIMIT, CLOSED, OVER_BUDGET, BAD_NODE = range(7)
CODE_NAMES = {OK: "ok", DUPLICATE: "duplicate venue", NOT_ALLOWED: "venue not allowed",
              CATEGORY_LIMIT: "category limit K_c", CLOSED: "venue closed during stay",
              OVER_BUDGET: "return after T_0 + T_max", BAD_NODE: "invalid node"}
EPS = 1e-9


# ---------------------------------------------------------------- crowd and profit (docs 3.2)

@njit(cache=True)
def profile_value(prof, c, t, anchor):
    """P_c(t): linear interpolation between hourly nodes placed at h:anchor (D2), cyclic 24 h."""
    x = (t - anchor) / 60.0
    f = np.floor(x)
    h0 = int(f) % 24                      # Python semantics in numba: always 0..23
    h1 = (h0 + 1) % 24
    fr = x - f
    return (1.0 - fr) * prof[c, h0] + fr * prof[c, h1]


@njit(cache=True)
def surge_value(surge, j, t):
    """E_j(t): sum of crowd surges at venue j; constant s in [t_s, t_e], then s*exp(-(t-t_e)/T_d)."""
    e = 0.0
    for k in range(surge.shape[0]):
        if int(surge[k, 0]) != j:
            continue
        ts, te, s, td = surge[k, 1], surge[k, 2], surge[k, 3], surge[k, 4]
        if t < ts:
            continue
        if t <= te:
            e += s
        else:
            e += s * np.exp(-(t - te) / td)
    return e


@njit(cache=True)
def crowd_value(prof, cat, surge, anchor, j, t):
    """C_j(t) = P_c(j)(t) + E_j(t)."""
    return profile_value(prof, cat[j], t, anchor) + surge_value(surge, j, t)


@njit(cache=True)
def profit_value(base_profit, lam, crowd):
    """S = u_c * w_i * (1 - lambda * min(1, C)); base_profit already holds u_c * w_i."""
    return base_profit * (1.0 - lam * min(1.0, crowd))


# ---------------------------------------------------------------- travel and opening (docs 3.3, 5.1)

@njit(cache=True)
def travel_time(T, traffic, tmask, i, j, t):
    """t_ij(t): base walk time times the largest active traffic factor (departure in window, D4)."""
    f = 1.0
    for k in range(traffic.shape[0]):
        if tmask[k, i, j] and traffic[k, 0] <= t < traffic[k, 1]:
            if traffic[k, 2] > f:
                f = traffic[k, 2]
    return T[i, j] * f


@njit(cache=True)
def is_open(prof, cat, closure, anchor, thr, j, a, b):
    """True when venue j is open during the whole stay [a, b] (D3: exact for a piecewise-linear P).

    P_c is linear between nodes, so its minimum on [a, b] is at a, at b or at a node inside.
    A closure event blocks the venue when its window overlaps the stay.
    """
    c = cat[j]
    if profile_value(prof, c, a, anchor) < thr or profile_value(prof, c, b, anchor) < thr:
        return False
    k = int(np.ceil((a - anchor) / 60.0))
    while 60.0 * k + anchor < b:
        if prof[c, k % 24] < thr:
            return False
        k += 1
    for q in range(closure.shape[0]):
        if int(closure[q, 0]) == j and a < closure[q, 2] and b > closure[q, 1]:
            return False
    return True


# ---------------------------------------------------------------- route evaluation

@njit(cache=True)
def eval_route_kernel(P, route):
    """Score a route (venues after the start node; the return to node 0 is implicit).

    Returns (profit, code, arrivals, crowds, profits, end_time). ``code`` is OK or the first
    violated constraint; the arrays hold values for the visited prefix.
    """
    (T, cat, stay, base_profit, kcap, prof, lam, thr, anchor,
     surge, closure, traffic, tmask, start_node, start_time, deadline, allowed, kc_used) = P
    n = T.shape[0]
    k = route.shape[0]
    arrivals = np.zeros(k)
    crowds = np.zeros(k)
    profits = np.zeros(k)
    seen = np.zeros(n, dtype=np.bool_)
    kc = kc_used.copy()
    cur = start_node
    t = start_time
    total = 0.0
    code = OK
    for p in range(k):
        j = route[p]
        if j <= 0 or j >= n:
            return total, BAD_NODE, arrivals, crowds, profits, t
        if seen[j]:
            code = DUPLICATE
        elif not allowed[j]:
            code = NOT_ALLOWED
        seen[j] = True
        c = cat[j]
        kc[c] += 1
        if code == OK and kc[c] > kcap[c]:
            code = CATEGORY_LIMIT
        arr = t + travel_time(T, traffic, tmask, cur, j, t)
        end = arr + stay[j]
        if code == OK and not is_open(prof, cat, closure, anchor, thr, j, arr, end):
            code = CLOSED
        cr = crowd_value(prof, cat, surge, anchor, j, arr)
        s = profit_value(base_profit[j], lam, cr)
        arrivals[p] = arr
        crowds[p] = cr
        profits[p] = s
        total += s
        cur = j
        t = end
    t_end = t + travel_time(T, traffic, tmask, cur, 0, t)
    if code == OK and t_end > deadline + EPS:
        code = OVER_BUDGET
    return total, code, arrivals, crowds, profits, t_end


@njit(cache=True)
def feasible_candidates(P, cur, t, visited, kc, out_j, out_arr, out_tt):
    """Fill out_* with every venue j allowed from (cur, t) (docs 4.1 step 2). Returns the count."""
    (T, cat, stay, base_profit, kcap, prof, lam, thr, anchor,
     surge, closure, traffic, tmask, start_node, start_time, deadline, allowed, kc_used) = P
    n = T.shape[0]
    cnt = 0
    for j in range(1, n):
        if visited[j] or not allowed[j]:
            continue
        if kc[cat[j]] >= kcap[cat[j]]:
            continue
        tt = travel_time(T, traffic, tmask, cur, j, t)
        arr = t + tt
        end = arr + stay[j]
        if not is_open(prof, cat, closure, anchor, thr, j, arr, end):
            continue
        if end + travel_time(T, traffic, tmask, j, 0, end) > deadline + EPS:
            continue
        out_j[cnt] = j
        out_arr[cnt] = arr
        out_tt[cnt] = tt
        cnt += 1
    return cnt


# ---------------------------------------------------------------- python API

@dataclass
class RouteReport:
    route: list[int]
    profit: float
    feasible: bool
    violation: str
    arrivals: np.ndarray
    crowds: np.ndarray
    profits: np.ndarray
    end_time: float
    avg_crowd: float
    budget_use: float
    rows: list[dict] = field(default_factory=list)


def evaluate_route(problem, route) -> RouteReport:
    """Score ``route`` on ``problem`` (use the ground-truth problem with all events for results)."""
    r = np.asarray(list(route), dtype=np.int64)
    profit, code, arr, cr, pr, t_end = eval_route_kernel(problem.arrays(), r)
    used = (t_end - problem.start_time) / max(problem.deadline - problem.start_time, EPS)
    rows = []
    for p, j in enumerate(r.tolist() if code != BAD_NODE else []):
        rows.append({"node": j, "venue_id": problem.venue_ids[j],
                     "category": problem.categories[problem.cat[j]],
                     "arrival": float(arr[p]), "stay": float(problem.stay[j]),
                     "crowd": float(cr[p]), "profit": float(pr[p])})
    return RouteReport(route=r.tolist(), profit=float(profit), feasible=code == OK,
                       violation=CODE_NAMES[int(code)], arrivals=arr, crowds=cr, profits=pr,
                       end_time=float(t_end), avg_crowd=float(cr.mean()) if len(r) else 0.0,
                       budget_use=float(used), rows=rows)
