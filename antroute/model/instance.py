"""WP3: a TDOP instance - N venues + start node 0, walking-time matrix, stay times, limits K_c.

The instance does not depend on the persona, the start hour or the scenario, so every method and
every experiment uses the same venues for a given (N, seed, start point).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from antroute.config import load_config, resolve

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def walk_matrix(lat, lon, speed_kmh: float, street_factor: float) -> np.ndarray:
    """Walking minutes: haversine * street factor / speed (docs 2.3 step 9)."""
    lat, lon = np.asarray(lat), np.asarray(lon)
    d = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    return d * street_factor / speed_kmh * 60.0


def stratified_counts(available: pd.Series, n: int, min_per_cat: int) -> dict[str, int]:
    """D6: at least ``min_per_cat`` per category, the rest proportional (largest remainder)."""
    avail = available.to_dict()
    take = {c: min(min_per_cat, a) for c, a in avail.items()}
    rest = n - sum(take.values())
    if rest < 0:
        raise ValueError(f"N={n} is smaller than the per-category minimum")
    while rest > 0:
        room = {c: avail[c] - take[c] for c in avail if avail[c] > take[c]}
        if not room:
            raise ValueError(f"only {sum(take.values())} venues available, N={n}")
        total = sum(avail[c] for c in room)
        quota = {c: rest * avail[c] / total for c in room}
        add = {c: min(int(np.floor(q)), room[c]) for c, q in quota.items()}
        if sum(add.values()) == 0:   # distribute the remainder one by one
            for c in sorted(room, key=lambda c: (quota[c] - np.floor(quota[c]), avail[c]),
                            reverse=True)[:rest]:
                add[c] = 1
        for c, a in add.items():
            take[c] += a
        rest = n - sum(take.values())
    return take


@dataclass
class Instance:
    venue_ids: list[str]          # index 0 = "START"
    categories: list[str]         # all categories (index = category id)
    cat: np.ndarray               # (n+1,) category id, -1 for node 0
    lat: np.ndarray
    lon: np.ndarray
    w: np.ndarray                 # (n+1,) value weight w_i, 0 for node 0
    checkins: np.ndarray          # (n+1,) n_i
    stay: np.ndarray              # (n+1,) s_i [min]
    T: np.ndarray                 # (n+1, n+1) walking minutes
    kcap: np.ndarray              # (n_cat,) K_c
    profiles: np.ndarray          # (n_cat, 3, 24) [category, weekday/weekend/all, hour]
    start_name: str = "custom"
    seed: int = 0

    @property
    def n(self) -> int:
        return len(self.venue_ids) - 1

    def node_of(self, venue_id: str) -> int:
        return self.venue_ids.index(venue_id)

    def top_venue(self, category: str) -> int:
        """Node of the venue with the highest w_i in ``category``."""
        c = self.categories.index(category)
        nodes = np.flatnonzero(self.cat == c)
        if len(nodes) == 0:
            raise ValueError(f"no venue of category {category!r} in the instance")
        return int(nodes[np.argmax(self.w[nodes])])

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path.with_suffix(".npz"), cat=self.cat, lat=self.lat, lon=self.lon,
                            w=self.w, checkins=self.checkins, stay=self.stay, T=self.T,
                            kcap=self.kcap, profiles=self.profiles)
        with open(path.with_suffix(".json"), "w", encoding="utf-8") as fh:
            json.dump({"venue_ids": self.venue_ids, "categories": self.categories,
                       "start_name": self.start_name, "seed": self.seed}, fh, indent=1)

    @classmethod
    def load(cls, path: str | Path) -> Instance:
        path = Path(path)
        arr = np.load(path.with_suffix(".npz"))
        with open(path.with_suffix(".json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        return cls(**meta, **{k: arr[k] for k in arr.files})


def load_profiles(cfg: dict, key: str = "profiles") -> np.ndarray:
    with np.load(resolve(cfg["paths"]["processed"]) / "profiles.npz") as arr:
        return arr[key]


def load_venues(cfg: dict) -> pd.DataFrame:
    return pd.read_parquet(resolve(cfg["paths"]["processed"]) / "venues.parquet")


def build_instance(n: int, start: str | tuple[float, float] = "times_square", seed: int | None = None,
                   cfg: dict | None = None, include: list[str] | None = None,
                   profiles_key: str = "profiles", venues: pd.DataFrame | None = None) -> Instance:
    """Select N venues (D6: stratified by category, fixed seed) and build the matrices."""
    cfg = cfg or load_config()
    icfg, dcfg = cfg["instance"], cfg["data"]
    seed = icfg["seed"] if seed is None else seed
    categories = list(dcfg["categories"])
    venues = load_venues(cfg) if venues is None else venues
    venues = venues[venues["category"].isin(categories)]
    if include:
        default = build_instance(n, start, seed, cfg, None, profiles_key, venues)
        if set(include) <= set(default.venue_ids):
            return default            # same venues as without ``include``
    rng = np.random.default_rng(seed)

    forced = venues[venues["venue_id"].isin(include or [])]
    if len(forced) != len(set(include or [])):
        missing = set(include or []) - set(forced["venue_id"])
        raise ValueError(f"venues not eligible: {sorted(missing)}")
    pool = venues[~venues["venue_id"].isin(forced["venue_id"])]
    avail = pool.groupby("category").size().reindex(categories, fill_value=0)
    counts = stratified_counts(avail, n - len(forced), icfg["min_per_category"])
    chosen = [forced]
    for c in categories:
        sub = pool[pool["category"] == c]
        if counts.get(c, 0):
            idx = rng.choice(len(sub), size=counts[c], replace=False)
            chosen.append(sub.iloc[np.sort(idx)])
    sel = pd.concat(chosen).sort_values(["category", "venue_id"]).reset_index(drop=True)

    if isinstance(start, str):
        start_name, (slat, slon) = start, cfg["start_points"][start]
    else:
        start_name, (slat, slon) = "custom", start
    lat = np.concatenate([[slat], sel["lat"].to_numpy()])
    lon = np.concatenate([[slon], sel["lon"].to_numpy()])
    cat = np.concatenate([[-1], [categories.index(c) for c in sel["category"]]]).astype(np.int64)
    stay = np.concatenate([[0.0], [float(dcfg["categories"][c]) for c in sel["category"]]])
    kmax = icfg.get("max_per_category", {})
    kcap = np.array([kmax.get(c, icfg["default_k"]) for c in categories], dtype=np.int64)
    return Instance(
        venue_ids=["START"] + sel["venue_id"].tolist(), categories=categories, cat=cat,
        lat=lat, lon=lon, w=np.concatenate([[0.0], sel["w"].to_numpy()]),
        checkins=np.concatenate([[0], sel["n"].to_numpy()]).astype(np.int64), stay=stay,
        T=walk_matrix(lat, lon, dcfg["walk_speed_kmh"], dcfg["street_factor"]),
        kcap=kcap, profiles=load_profiles(cfg, profiles_key), start_name=start_name, seed=seed)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build and save an instance")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--start", default="times_square")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    inst = build_instance(a.n, a.start, a.seed)
    out = a.out or resolve(load_config()["paths"]["processed"]) / f"instance_n{a.n}_{a.start}"
    inst.save(out)
    print(f"instance N={inst.n} start={inst.start_name} saved to {out}.json/.npz")
    print(pd.Series([inst.categories[c] for c in inst.cat[1:]]).value_counts().to_string())
