from __future__ import annotations

import numpy as np
import pytest

from antroute.config import load_config, resolve
from antroute.model.instance import Instance, walk_matrix
from antroute.model.problem import Problem

CATS = ["A", "B", "C"]


def make_instance(T=None, cats=None, w=None, stay=None, profiles=None, kcap=None,
                  lat=None, lon=None) -> Instance:
    """Small synthetic instance. ``profiles``: (n_cat, 24) used for every day type."""
    cats = np.asarray(cats if cats is not None else [0, 1, 2], dtype=np.int64)
    n = len(cats)
    if lat is None:
        lat = 40.75 + 0.005 * np.arange(n + 1)
        lon = -73.99 + 0.003 * np.arange(n + 1)
    if T is None:
        T = walk_matrix(lat, lon, 5.0, 1.3)
    prof = np.ones((len(CATS), 24)) * 0.5 if profiles is None else np.asarray(profiles, float)
    return Instance(
        venue_ids=["START"] + [f"v{i}" for i in range(1, n + 1)], categories=list(CATS),
        cat=np.concatenate([[-1], cats]).astype(np.int64), lat=np.asarray(lat, float),
        lon=np.asarray(lon, float),
        w=np.concatenate([[0.0], w if w is not None else np.ones(n)]).astype(float),
        checkins=np.zeros(n + 1, dtype=np.int64),
        stay=np.concatenate([[0.0], stay if stay is not None else np.full(n, 30.0)]).astype(float),
        T=np.asarray(T, float),
        kcap=np.asarray(kcap if kcap is not None else [n] * len(CATS), dtype=np.int64),
        profiles=np.repeat(prof[:, None, :], 3, axis=1))


@pytest.fixture
def cfg():
    return load_config()


def make_problem(inst, cfg, u=None, start=480.0, budget=480.0, lam=0.8, scenario=None,
                 known_at=None) -> Problem:
    persona = {c: 1.0 for c in CATS} if u is None else u
    return Problem.build(inst, cfg, persona, start, budget, day_type="weekday", lam=lam,
                         scenario=scenario, known_at=known_at)


def random_instance(rng: np.random.Generator, n: int) -> Instance:
    """Random small instance around midtown with random smooth profiles."""
    lat = 40.75 + rng.uniform(-0.02, 0.02, n + 1)
    lon = -73.99 + rng.uniform(-0.02, 0.02, n + 1)
    base = rng.uniform(0, 1, (len(CATS), 24))
    prof = (base + np.roll(base, 1, axis=1) + np.roll(base, -1, axis=1)) / 3
    prof /= prof.max(axis=1, keepdims=True)
    return make_instance(cats=rng.integers(0, len(CATS), n), w=rng.uniform(0.2, 1, n),
                         stay=rng.choice([20.0, 45.0, 60.0, 90.0], n), profiles=prof,
                         kcap=[2, 2, 2], lat=lat, lon=lon)


def has_data() -> bool:
    cfg = load_config()
    return (resolve(cfg["paths"]["processed"]) / "venues.parquet").exists()


needs_data = pytest.mark.skipif(not has_data(), reason="run the data pipeline first")
