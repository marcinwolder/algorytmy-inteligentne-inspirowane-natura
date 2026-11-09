"""Random baseline: add random allowed venues until no venue is allowed."""

from __future__ import annotations

import time

import numpy as np

from antroute.model.evaluate import eval_route_kernel
from antroute.solvers.kernels import MODE_RANDOM, N_PRM, build_route, seed_rng
from antroute.solvers.result import SolverResult


def random_route(problem, seed: int = 0) -> SolverResult:
    t = time.perf_counter()
    seed_rng(seed)
    P = problem.arrays()
    n1 = problem.n + 1
    route = build_route(P, np.ones((1, n1, n1)), np.zeros((n1, 1)), np.zeros((n1, 1)),
                        np.ones(N_PRM), MODE_RANDOM, False)
    return SolverResult(route=route.tolist(), profit=float(eval_route_kernel(P, route)[0]),
                        method="random", time_s=time.perf_counter() - t)
