"""WP8: replanning during the day (docs/04-algorytm.md 4.5, docs/05 5.2).

The morning plan uses the events known at T_0. At every later announcement t_a:

1. Take the user's true timing of the current plan (ground truth, all events).
2. D7: keep the venues the user has already reached. If the user is inside a venue at t_a,
   they finish the stay and the new start is this venue at the end of the stay. If the user is
   walking at t_a, the walk is dropped (the target may be closed now) and the new start is the
   last venue (or the start point) at t_a. This approximation ignores the part of the walk
   already done.
3. Solve the sub-problem (rest of the budget, committed venues out, events known at t_a).
4. New plan = committed part + new part.

The final route is scored on the ground-truth problem.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from antroute.model.evaluate import evaluate_route
from antroute.solvers.result import SolverResult

SolveFn = Callable[[object, object, bool], tuple[SolverResult, object]]


@dataclass
class DayResult:
    route: list[int]
    plans: list[dict] = field(default_factory=list)   # one entry per (re)planning
    time_s: float = 0.0


def plan_day(problem, solve: SolveFn, warm: bool = True) -> DayResult:
    """Plan a day with announcements. ``solve(problem, state, first)`` returns (result, state);
    ``state`` is passed back only for a warm start."""
    truth = problem.with_events(None)
    t0 = problem.start_time
    res, state = solve(problem.with_events(t0), None, True)
    route = list(res.route)
    plans = [{"t": t0, "committed": [], "result": res}]
    total_time = res.time_s
    for ta in problem.scenario.announcements_after(t0) if problem.scenario else []:
        rep = evaluate_route(truth, route)
        ends = [a + problem.stay[j] for a, j in zip(rep.arrivals, route, strict=True)]
        if not route or ends[-1] <= ta:
            plans.append({"t": ta, "committed": route, "result": None, "skipped": "day over"})
            break
        # D7: a stay in progress is finished; a walk in progress is dropped
        visited = [p for p, a in enumerate(rep.arrivals) if a <= ta]
        if visited and ends[visited[-1]] >= ta:          # at a venue: finish the stay
            k = visited[-1] + 1
            start_node, start_time = route[k - 1], ends[k - 1]
        else:                                            # walking: replan from the last venue
            k = len(visited)
            start_node = route[k - 1] if k else problem.start_node
            start_time = ta
        committed = route[:k]
        sub = problem.with_events(ta).remaining(start_node, start_time, committed)
        res, new_state = solve(sub, state if warm else None, False)
        state = new_state
        total_time += res.time_s
        route = committed + list(res.route)
        plans.append({"t": ta, "committed": committed, "result": res,
                      "start_node": start_node, "start_time": start_time})
    return DayResult(route=route, plans=plans, time_s=total_time)
