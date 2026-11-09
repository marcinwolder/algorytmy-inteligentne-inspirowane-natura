"""Common solver result."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class SolverResult:
    route: list[int]
    profit: float                       # profit on the problem the solver saw (solver objective)
    method: str
    time_s: float = 0.0
    iterations: int = 0
    history: list[float] = field(default_factory=list)   # best profit after each iteration
    tau: np.ndarray | None = None
    phi_ants: np.ndarray | None = None
    tau0: float = 0.0
    info: dict = field(default_factory=dict)
