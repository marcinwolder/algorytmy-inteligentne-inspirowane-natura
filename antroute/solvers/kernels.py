"""Numba kernels shared by the solvers: route construction, pheromone update, local search.

All feasibility and profit values come from antroute.model.evaluate.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from antroute.model.evaluate import (
    OK,
    crowd_value,
    eval_route_kernel,
    feasible_candidates,
    profit_value,
    travel_time,
)

# indices in the float parameter vector ``prm``
BETA, Q0, PSI, TAU0, GAMMA, DPHI, THETA, BIN_MIN = range(8)
N_PRM = 8

MODE_ACS, MODE_GREEDY, MODE_RANDOM = 0, 1, 2


@njit(cache=True)
def seed_rng(seed):
    np.random.seed(seed)


@njit(cache=True)
def tau_bin(t, nb):
    """Pheromone time bin: 0 for ACS-A; for ACS-B one of ``nb`` equal bins of the day (docs 4.6)."""
    if nb == 1:
        return 0
    b = int((t % 1440.0) // (1440.0 / nb))
    return min(max(b, 0), nb - 1)


@njit(cache=True)
def phi_bin(t, bin_min, nbins):
    b = int(t // bin_min)
    return min(max(b, 0), nbins - 1)


@njit(cache=True)
def build_route(P, tau, phi_ev, phi_ants, prm, mode, update):
    """Build one route (docs 4.1).

    mode = MODE_ACS: pseudo-random proportional rule with antipheromone (docs 4.2);
    mode = MODE_GREEDY: largest eta = profit per minute; mode = MODE_RANDOM: uniform choice.
    ``update`` applies the local pheromone update and the ants' antipheromone deposit.
    """
    (T, cat, stay, base_profit, kcap, prof, lam, thr, anchor,
     surge, closure, traffic, tmask, start_node, start_time, deadline, allowed, kc_used) = P
    n = T.shape[0]
    nb = tau.shape[0]
    nbins = phi_ev.shape[1]
    beta, q0, psi, tau0 = prm[BETA], prm[Q0], prm[PSI], prm[TAU0]
    gamma, dphi, theta, bin_min = prm[GAMMA], prm[DPHI], prm[THETA], prm[BIN_MIN]

    visited = np.zeros(n, dtype=np.bool_)
    kc = kc_used.copy()
    route = np.empty(n, dtype=np.int64)
    cj = np.empty(n, dtype=np.int64)
    carr = np.empty(n)
    ctt = np.empty(n)
    wgt = np.empty(n)
    k = 0
    cur = start_node
    t = start_time
    while True:
        cnt = feasible_candidates(P, cur, t, visited, kc, cj, carr, ctt)
        if cnt == 0:
            break
        tb = tau_bin(t, nb)
        total = 0.0
        for q in range(cnt):
            j = cj[q]
            if mode == MODE_RANDOM:
                wgt[q] = 1.0
            else:
                s = profit_value(base_profit[j], lam,
                                 crowd_value(prof, cat, surge, anchor, j, carr[q]))
                eta = s / (ctt[q] + stay[j])
                if mode == MODE_GREEDY:
                    wgt[q] = eta
                else:
                    b = phi_bin(carr[q], bin_min, nbins)
                    phi = phi_ev[j, b] + phi_ants[j, b]
                    wgt[q] = tau[tb, cur, j] * eta ** beta * (1.0 + phi) ** (-gamma)
            total += wgt[q]
        if total <= 0.0:
            break   # every remaining venue gives zero profit
        if mode == MODE_GREEDY or (mode == MODE_ACS and np.random.random() < q0):
            pick = 0
            for q in range(1, cnt):
                if wgt[q] > wgt[pick]:
                    pick = q
        else:
            r = np.random.random() * total
            acc = 0.0
            pick = cnt - 1
            for q in range(cnt):
                acc += wgt[q]
                if acc >= r and wgt[q] > 0.0:
                    pick = q
                    break
        j = cj[pick]
        arr = carr[pick]
        if update:
            tau[tb, cur, j] = (1.0 - psi) * tau[tb, cur, j] + psi * tau0
            c = crowd_value(prof, cat, surge, anchor, j, arr)
            if c > theta:
                phi_ants[j, phi_bin(arr, bin_min, nbins)] += dphi * c
        route[k] = j
        k += 1
        visited[j] = True
        kc[cat[j]] += 1
        t = arr + stay[j]
        cur = j
    return route[:k].copy()


@njit(cache=True)
def run_ants(P, tau, phi_ev, phi_ants, prm, m):
    """One ACS iteration: m ants build routes in turn. Returns (routes padded with -1, lengths,
    profits)."""
    n = P[0].shape[0]
    routes = -np.ones((m, n), dtype=np.int64)
    lens = np.zeros(m, dtype=np.int64)
    profits = np.zeros(m)
    for a in range(m):
        r = build_route(P, tau, phi_ev, phi_ants, prm, MODE_ACS, True)
        routes[a, :r.shape[0]] = r
        lens[a] = r.shape[0]
        profits[a] = eval_route_kernel(P, r)[0]
    return routes, lens, profits


@njit(cache=True)
def global_update(P, tau, route, profit, rho):
    """tau_ij <- (1 - rho) tau_ij + rho * Profit_best on the best route, incl. the return edge."""
    (T, cat, stay, base_profit, kcap, prof, lam, thr, anchor,
     surge, closure, traffic, tmask, start_node, start_time, deadline, allowed, kc_used) = P
    nb = tau.shape[0]
    cur = start_node
    t = start_time
    for p in range(route.shape[0]):
        j = route[p]
        tb = tau_bin(t, nb)
        tau[tb, cur, j] = (1.0 - rho) * tau[tb, cur, j] + rho * profit
        t = t + travel_time(T, traffic, tmask, cur, j, t) + stay[j]
        cur = j
    tb = tau_bin(t, nb)
    tau[tb, cur, 0] = (1.0 - rho) * tau[tb, cur, 0] + rho * profit


@njit(cache=True)
def _try(P, cand, best):
    p, code, _, _, _, _ = eval_route_kernel(P, cand)
    return code == OK and p > best + 1e-12, p


@njit(cache=True)
def local_search(P, route, max_rounds):
    """D9: first-improvement local search with insert, replace, relocate and swap moves.

    Every candidate route is scored by eval_route_kernel, so the result is always feasible
    when the input is feasible.
    """
    n = P[0].shape[0]
    allowed = P[16]
    best_r = route.copy()
    best_p, code, _, _, _, _ = eval_route_kernel(P, best_r)
    if code != OK:
        return best_r, best_p
    for _ in range(max_rounds):
        improved = False
        k = best_r.shape[0]
        inr = np.zeros(n, dtype=np.bool_)
        for p in range(k):
            inr[best_r[p]] = True
        # insert an unused venue
        for j in range(1, n):
            if improved:
                break
            if inr[j] or not allowed[j]:
                continue
            for pos in range(k + 1):
                cand = np.empty(k + 1, dtype=np.int64)
                cand[:pos] = best_r[:pos]
                cand[pos] = j
                cand[pos + 1:] = best_r[pos:]
                ok, pv = _try(P, cand, best_p)
                if ok:
                    best_r, best_p, improved = cand, pv, True
                    break
        # replace a venue with an unused one
        if not improved:
            for pos in range(k):
                if improved:
                    break
                for j in range(1, n):
                    if inr[j] or not allowed[j]:
                        continue
                    cand = best_r.copy()
                    cand[pos] = j
                    ok, pv = _try(P, cand, best_p)
                    if ok:
                        best_r, best_p, improved = cand, pv, True
                        break
        # relocate one venue
        if not improved:
            for a in range(k):
                if improved:
                    break
                for b in range(k):
                    if a == b:
                        continue
                    tmp = np.empty(k - 1, dtype=np.int64)
                    tmp[:a] = best_r[:a]
                    tmp[a:] = best_r[a + 1:]
                    cand = np.empty(k, dtype=np.int64)
                    cand[:b] = tmp[:b]
                    cand[b] = best_r[a]
                    cand[b + 1:] = tmp[b:]
                    ok, pv = _try(P, cand, best_p)
                    if ok:
                        best_r, best_p, improved = cand, pv, True
                        break
        # swap two venues
        if not improved:
            for a in range(k):
                if improved:
                    break
                for b in range(a + 1, k):
                    cand = best_r.copy()
                    cand[a], cand[b] = best_r[b], best_r[a]
                    ok, pv = _try(P, cand, best_p)
                    if ok:
                        best_r, best_p, improved = cand, pv, True
                        break
        if not improved:
            break
    return best_r, best_p
