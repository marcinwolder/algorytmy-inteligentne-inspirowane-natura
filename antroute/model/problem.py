"""Problem = instance + user (persona, start, budget, day type) + the events known to the planner.

A Problem is what a solver sees. The ground-truth problem (``known_at=None``) has every event of
the scenario and is the one used to score final routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from antroute.model.instance import Instance
from antroute.model.profiles import DAY_TYPES
from antroute.scenario.events import Scenario, event_arrays


@dataclass
class Problem:
    instance: Instance
    T: np.ndarray
    cat: np.ndarray
    stay: np.ndarray
    base_profit: np.ndarray       # u_c(i) * w_i
    kcap: np.ndarray
    prof: np.ndarray              # (n_cat, 24) for the day type
    lam: float
    thr: float
    anchor: float
    surge: np.ndarray
    closure: np.ndarray
    traffic: np.ndarray
    tmask: np.ndarray
    tnode: np.ndarray             # (k, n+1) venues inside each traffic area (antipheromone only)
    start_node: int
    start_time: float
    deadline: float
    allowed: np.ndarray           # (n+1,) venues the planner may add
    kc_used: np.ndarray           # (n_cat,) category counts already used (replanning)
    u: np.ndarray = field(default_factory=lambda: np.zeros(0))
    scenario: Scenario | None = None
    known_at: float | None = None

    @property
    def n(self) -> int:
        return self.T.shape[0] - 1

    @property
    def venue_ids(self) -> list[str]:
        return self.instance.venue_ids

    @property
    def categories(self) -> list[str]:
        return self.instance.categories

    def arrays(self) -> tuple:
        return (self.T, self.cat, self.stay, self.base_profit, self.kcap, self.prof,
                float(self.lam), float(self.thr), float(self.anchor), self.surge, self.closure,
                self.traffic, self.tmask, int(self.start_node), float(self.start_time),
                float(self.deadline), self.allowed, self.kc_used)

    def replace(self, **kw) -> Problem:
        return replace(self, **kw)

    def with_events(self, known_at: float | None) -> Problem:
        """Same problem with the events the planner knows at ``known_at`` (None = all)."""
        events = self.scenario.known(known_at) if self.scenario else []
        return replace(self, known_at=known_at, **event_arrays(events, self.instance))

    def remaining(self, start_node: int, start_time: float, done: list[int]) -> Problem:
        """Sub-problem for replanning (docs 4.5): new start, rest of the budget, visited venues out."""
        allowed = self.allowed.copy()
        kc = self.kc_used.copy()
        for j in done:
            allowed[j] = False
            kc[self.cat[j]] += 1
        return replace(self, start_node=int(start_node), start_time=float(start_time),
                       allowed=allowed, kc_used=kc)

    @classmethod
    def build(cls, instance: Instance, cfg: dict, persona: str | dict = "culture",
              start_time: float = 480.0, budget: float = 480.0, day_type: str | None = None,
              lam: float | None = None, scenario: Scenario | None = None,
              known_at: float | None = None) -> Problem:
        dcfg = cfg["data"]
        u_map = cfg["personas"][persona] if isinstance(persona, str) else persona
        u = np.array([float(u_map.get(c, 0.0)) for c in instance.categories])
        scenario = scenario.resolve(instance) if scenario is not None else Scenario()
        day_type = day_type or scenario.day_type
        prof = instance.profiles[:, DAY_TYPES.index(day_type), :].copy()
        base = np.zeros(instance.n + 1)
        base[1:] = u[instance.cat[1:]] * instance.w[1:]
        allowed = base > 0
        allowed[0] = False
        p = cls(instance=instance, T=instance.T, cat=instance.cat, stay=instance.stay,
                base_profit=base, kcap=instance.kcap, prof=prof,
                lam=cfg["model"]["lam"] if lam is None else lam, thr=dcfg["closed_threshold"],
                anchor=float(dcfg["profile_anchor_minute"]),
                surge=np.zeros((0, 5)), closure=np.zeros((0, 3)), traffic=np.zeros((0, 3)),
                tmask=np.zeros((0, instance.n + 1, instance.n + 1), dtype=np.bool_),
                tnode=np.zeros((0, instance.n + 1), dtype=np.bool_), start_node=0,
                start_time=float(start_time),
                deadline=float(start_time + budget), allowed=allowed,
                kc_used=np.zeros(len(instance.categories), dtype=np.int64), u=u,
                scenario=scenario)
        return p.with_events(known_at)
