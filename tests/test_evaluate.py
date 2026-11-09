"""WP4 / K3: every formula and constraint of docs/03-model.md, checked against hand values."""

from __future__ import annotations

import math

import numpy as np
import pytest
from conftest import make_instance, make_problem

from antroute.model.evaluate import (
    crowd_value,
    evaluate_route,
    is_open,
    profile_value,
    profit_value,
    surge_value,
    travel_time,
)
from antroute.scenario.events import load_scenario

# ---------------------------------------------------------------- P_c(t), D2


def test_profile_value_at_nodes_and_between():
    prof = np.zeros((1, 24))
    prof[0] = np.arange(24) / 23.0
    anchor = 30.0
    for h in range(24):
        assert profile_value(prof, 0, 60.0 * h + 30.0, anchor) == pytest.approx(prof[0, h])
    # 10:00 is halfway between the 9:30 and 10:30 nodes
    assert profile_value(prof, 0, 600.0, anchor) == pytest.approx((prof[0, 9] + prof[0, 10]) / 2)


def test_profile_value_is_cyclic_and_next_day():
    prof = np.zeros((1, 24))
    prof[0, 23], prof[0, 0] = 1.0, 0.0
    # 00:00 is halfway between 23:30 (day before) and 00:30
    assert profile_value(prof, 0, 0.0, 30.0) == pytest.approx(0.5)
    assert profile_value(prof, 0, 1440.0, 30.0) == pytest.approx(0.5)
    assert profile_value(prof, 0, 1440.0 + 600.0, 30.0) == pytest.approx(
        profile_value(prof, 0, 600.0, 30.0))


def test_profit_has_no_jump_at_full_hour():
    prof = np.zeros((1, 24))
    prof[0] = np.random.default_rng(0).uniform(0, 1, 24)
    for h in range(24):
        a = profile_value(prof, 0, 60.0 * h - 1e-6, 30.0)
        b = profile_value(prof, 0, 60.0 * h + 1e-6, 30.0)
        assert abs(a - b) < 1e-6


# ---------------------------------------------------------------- S_i(a_i), docs 3.2


def test_profit_formula():
    assert profit_value(0.8, 0.8, 0.5) == pytest.approx(0.8 * (1 - 0.8 * 0.5))
    assert profit_value(0.8, 0.0, 0.9) == pytest.approx(0.8)          # lambda = 0 ignores crowd
    assert profit_value(0.8, 1.0, 1.0) == pytest.approx(0.0)          # lambda = 1, peak -> 0
    assert profit_value(0.8, 0.8, 1.7) == pytest.approx(0.8 * 0.2)    # min(1, C)


def test_lambda_zero_profit_does_not_depend_on_hour(cfg):
    rng = np.random.default_rng(1)
    inst = make_instance(profiles=rng.uniform(0.1, 1, (3, 24)))
    p = make_problem(inst, cfg, lam=0.0)
    for t in (480.0, 700.0, 1000.0):
        for j in (1, 2, 3):
            c = crowd_value(p.prof, p.cat, p.surge, p.anchor, j, t)
            assert profit_value(p.base_profit[j], p.lam, c) == pytest.approx(p.base_profit[j])


def test_zero_preference_means_zero_profit_and_not_allowed(cfg):
    inst = make_instance()
    p = make_problem(inst, cfg, u={"A": 0.0, "B": 1.0, "C": 0.5})
    assert p.base_profit[1] == 0.0
    assert not p.allowed[1]
    assert p.base_profit[3] == pytest.approx(0.5)
    rep = evaluate_route(p, [1])
    assert not rep.feasible and rep.violation == "venue not allowed"


# ---------------------------------------------------------------- E_i(t), docs 5.1


def test_surge_window_and_decay():
    surge = np.array([[1, 600.0, 780.0, 0.8, 60.0]])
    assert surge_value(surge, 1, 599.0) == 0.0
    assert surge_value(surge, 1, 600.0) == pytest.approx(0.8)
    assert surge_value(surge, 1, 780.0) == pytest.approx(0.8)
    assert surge_value(surge, 1, 840.0) == pytest.approx(0.8 / math.e)
    assert surge_value(surge, 2, 700.0) == 0.0
    two = np.array([[1, 600.0, 780.0, 0.5, 60.0], [1, 700.0, 720.0, 0.3, 30.0]])
    assert surge_value(two, 1, 710.0) == pytest.approx(0.8)


# ---------------------------------------------------------------- t_ij(t), D4


def test_traffic_factor_only_in_window_and_area():
    T = np.array([[0.0, 10.0], [10.0, 0.0]])
    traffic = np.array([[720.0, 900.0, 2.0]])
    mask = np.array([[[False, True], [False, False]]])
    assert travel_time(T, traffic, mask, 0, 1, 700.0) == 10.0
    assert travel_time(T, traffic, mask, 0, 1, 720.0) == 20.0
    assert travel_time(T, traffic, mask, 0, 1, 899.0) == 20.0
    assert travel_time(T, traffic, mask, 0, 1, 900.0) == 10.0
    assert travel_time(T, traffic, mask, 1, 0, 800.0) == 10.0   # edge outside the area


# ---------------------------------------------------------------- opening, D3


def test_is_open_detects_closed_node_inside_stay():
    prof = np.ones((1, 24))
    prof[0, 10] = 0.0                      # node 10:30 closed, 10:00 and 11:00 are 0.5
    cat = np.array([-1, 0])
    no_closure = np.zeros((0, 3))
    assert profile_value(prof, 0, 600.0, 30.0) == pytest.approx(0.5)
    assert profile_value(prof, 0, 660.0, 30.0) == pytest.approx(0.5)
    assert not is_open(prof, cat, no_closure, 30.0, 0.05, 1, 600.0, 660.0)
    assert is_open(prof, cat, no_closure, 30.0, 0.05, 1, 480.0, 600.0)


def test_is_open_respects_closure_overlap():
    prof = np.ones((1, 24))
    cat = np.array([-1, 0])
    closure = np.array([[1, 480.0, 720.0]])
    assert not is_open(prof, cat, closure, 30.0, 0.05, 1, 700.0, 760.0)
    assert is_open(prof, cat, closure, 30.0, 0.05, 1, 720.0, 780.0)    # starts when it opens
    assert is_open(prof, cat, closure, 30.0, 0.05, 1, 420.0, 480.0)    # ends when it closes


# ---------------------------------------------------------------- whole route, docs 3.3


def hand_instance():
    T = np.array([[0, 10, 30, 30], [10, 0, 20, 30], [30, 20, 0, 5], [15, 30, 5, 0]], float)
    prof = np.zeros((3, 24))
    prof[0], prof[1], prof[2] = 0.25, 0.5, 1.0
    return make_instance(T=T, w=[1.0, 0.5, 0.8], stay=[30, 60, 15], profiles=prof)


def test_route_hand_computed(cfg):
    p = make_problem(hand_instance(), cfg, u={"A": 1.0, "B": 1.0, "C": 0.5})
    rep = evaluate_route(p, [1, 2, 3])
    # arrivals: 480+10 = 490; 490+30+20 = 540; 540+60+5 = 605; back 605+15+15 = 635
    assert list(rep.arrivals) == pytest.approx([490, 540, 605])
    assert rep.end_time == pytest.approx(635)
    expected = 1.0 * (1 - 0.8 * 0.25) + 0.5 * (1 - 0.8 * 0.5) + 0.5 * 0.8 * (1 - 0.8 * 1.0)
    assert rep.profit == pytest.approx(expected)
    assert rep.feasible
    assert rep.budget_use == pytest.approx((635 - 480) / 480)
    assert rep.avg_crowd == pytest.approx((0.25 + 0.5 + 1.0) / 3)


def test_budget_violation(cfg):
    p = make_problem(hand_instance(), cfg, budget=150.0)
    rep = evaluate_route(p, [1, 2, 3])          # back at 635 > 480 + 150
    assert not rep.feasible and rep.violation == "return after T_0 + T_max"
    assert evaluate_route(p, [1, 2]).feasible


def test_duplicate_and_category_limit(cfg):
    inst = hand_instance()
    p = make_problem(inst, cfg)
    assert evaluate_route(p, [1, 1]).violation == "duplicate venue"
    inst2 = make_instance(cats=[0, 0, 1], kcap=[1, 1, 1])
    p2 = make_problem(inst2, cfg)
    assert evaluate_route(p2, [1, 2]).violation == "category limit K_c"
    assert evaluate_route(p2, [1, 3]).feasible


def test_closed_venue_in_part_of_stay(cfg):
    prof = np.ones((3, 24))
    prof[0, 9] = 0.0                     # node 9:30 closed for category A
    inst = make_instance(T=np.full((4, 4), 10.0) - 10 * np.eye(4), profiles=prof)
    p = make_problem(inst, cfg, start=500.0)    # arrival at venue 1 at 8:30, stay to 9:00
    assert evaluate_route(p, [1]).feasible
    p2 = make_problem(inst, cfg, start=530.0)   # stay 9:00-9:30 touches the closed node
    rep = evaluate_route(p2, [1])
    assert not rep.feasible and rep.violation == "venue closed during stay"


def test_closure_event_makes_route_infeasible(cfg):
    inst = hand_instance()
    sc = load_scenario({"events": [{"type": "closure", "venue": "v1",
                                    "window": ["08:00", "09:00"]}]})
    p = make_problem(inst, cfg, scenario=sc)
    assert evaluate_route(p, [1]).violation == "venue closed during stay"
    assert evaluate_route(p, [2]).feasible


def test_surge_lowers_profit(cfg):
    inst = hand_instance()
    sc = load_scenario({"events": [{"type": "crowd_surge", "venue": "v1",
                                    "window": ["08:00", "09:00"], "strength": 0.5}]})
    base = evaluate_route(make_problem(inst, cfg), [1]).profit
    hit = evaluate_route(make_problem(inst, cfg, scenario=sc), [1])
    assert hit.crowds[0] == pytest.approx(0.75)
    assert hit.profit == pytest.approx(1 - 0.8 * 0.75)
    assert hit.profit < base


def test_announced_event_hidden_before_announcement(cfg):
    inst = hand_instance()
    sc = load_scenario({"events": [{"type": "closure", "venue": "v1",
                                    "window": ["08:00", "09:00"], "announced": "08:30"}]})
    morning = make_problem(inst, cfg, scenario=sc, known_at=480.0)
    truth = make_problem(inst, cfg, scenario=sc)
    assert evaluate_route(morning, [1]).feasible
    assert not evaluate_route(truth, [1]).feasible


# ---------------------------------------------------------------- numba modulo, candidates, nodes


def test_negative_time_wraps_to_previous_day():
    """Checks that the jitted modulo has Python semantics (-1 % 24 == 23)."""
    prof = np.zeros((1, 24))
    prof[0, 23] = 0.7
    assert profile_value(prof, 0, -30.0, 30.0) == pytest.approx(0.7)       # 23:30 day before
    cat = np.array([-1, 0])
    assert not is_open(prof, cat, np.zeros((0, 3)), 30.0, 0.05, 1, -90.0, 30.0)


def test_feasible_candidates_respect_budget_visited_and_limits(cfg):
    from antroute.model.evaluate import feasible_candidates

    inst = hand_instance()
    n1 = inst.n + 1
    out_j, out_a, out_t = np.empty(n1, np.int64), np.empty(n1), np.empty(n1)

    def cands(p, visited=None, kc=None):
        v = np.zeros(n1, np.bool_) if visited is None else visited
        k = p.kc_used.copy() if kc is None else kc
        cnt = feasible_candidates(p.arrays(), 0, p.start_time, v, k, out_j, out_a, out_t)
        return {int(out_j[q]): float(out_a[q]) for q in range(cnt)}

    p = make_problem(inst, cfg, budget=150.0)
    assert cands(p) == {1: 490.0, 2: 510.0, 3: 510.0}
    # deadline 530: v1 is back at 530 (allowed), v2 at 600 and v3 at 540 are late
    assert cands(make_problem(inst, cfg, budget=50.0)) == {1: 490.0}
    visited = np.zeros(n1, np.bool_)
    visited[1] = True
    assert set(cands(p, visited)) == {2, 3}
    full = np.array(inst.kcap)        # every category limit used up
    assert cands(p, kc=full) == {}


def test_invalid_node_is_reported(cfg):
    p = make_problem(hand_instance(), cfg)
    assert evaluate_route(p, [9]).violation == "invalid node"
    assert evaluate_route(p, [0]).violation == "invalid node"
