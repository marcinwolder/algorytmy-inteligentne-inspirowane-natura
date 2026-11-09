"""WP2: hourly crowd profiles P_c(h) per (category, day type) and venue weights w_i.

Usage: python -m antroute.model.profiles
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from antroute.config import load_config, resolve

DAY_TYPES = ("weekday", "weekend", "all")


def smooth_cyclic(hist: np.ndarray, window: int) -> np.ndarray:
    """Cyclic moving average over 24 h (23:00 joins 0:00). ``window`` must be odd."""
    if window <= 1:
        return hist.astype(float)
    half = window // 2
    out = np.zeros(24, dtype=float)
    for k in range(-half, half + 1):
        out += np.roll(hist, -k)
    return out / window


def normalise(hist: np.ndarray) -> np.ndarray:
    m = hist.max()
    return hist / m if m > 0 else np.zeros_like(hist, dtype=float)


def _histograms(df: pd.DataFrame, categories: list[str]) -> dict[str, np.ndarray]:
    """Raw counts, shape (n_cat, 24), for each day type."""
    out = {}
    for dt in DAY_TYPES:
        sub = df if dt == "all" else df[df["weekend"] == (dt == "weekend")]
        t = (sub.groupby(["category", "hour"]).size().unstack(fill_value=0)
             .reindex(index=categories, columns=range(24), fill_value=0))
        out[dt] = t.to_numpy(dtype=float)
    return out


def compute_profiles(df: pd.DataFrame, cfg: dict) -> tuple[np.ndarray, dict]:
    """Profiles, shape (n_cat, 3, 24), indexed [category, day type, hour]; values in [0, 1].

    D5: when a (category, day type) pair has fewer than ``profile_min_checkins`` check-ins, use
    (1) the category's all-days profile, else (2) the merged fallback group for that day type,
    else (3) the merged group over all days. The chosen source is returned in ``meta``.
    """
    dcfg = cfg["data"]
    categories = list(dcfg["categories"])
    hists = _histograms(df, categories)
    min_n = dcfg["profile_min_checkins"]
    groups = dcfg.get("profile_fallback_groups", {})
    window = dcfg["smoothing_window_h"]

    prof = np.zeros((len(categories), len(DAY_TYPES), 24))
    meta: dict[str, dict] = {}
    for ci, cat in enumerate(categories):
        meta[cat] = {}
        group = [g for g in groups.get(cat, [cat]) if g in categories] or [cat]
        group_idx = [categories.index(g) for g in group]
        for di, dt in enumerate(DAY_TYPES):
            candidates = [
                (f"{cat}/{dt}", hists[dt][ci]),
                (f"{cat}/all", hists["all"][ci]),
                (f"{'+'.join(group)}/{dt}", hists[dt][group_idx].sum(axis=0)),
                (f"{'+'.join(group)}/all", hists["all"][group_idx].sum(axis=0)),
            ]
            source, hist = next(((s, h) for s, h in candidates if h.sum() >= min_n), candidates[-1])
            prof[ci, di] = normalise(smooth_cyclic(hist, window))
            meta[cat][dt] = {"source": source, "checkins": int(hist.sum()),
                             "own_checkins": int(hists[dt][ci].sum()),
                             "peak_hour": int(np.argmax(prof[ci, di]))}
    return prof, meta


def bootstrap_df(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Resample whole days with replacement (docs 8.1: data version = bootstrap of days)."""
    days = df["date"].unique()
    picked = rng.choice(days, size=len(days), replace=True)
    by_day = {d: g for d, g in df.groupby("date")}
    return pd.concat([by_day[d] for d in picked], ignore_index=True)


def venue_table(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Eligible venues (>= min check-ins) with location, category, n_i and w_i."""
    dcfg = cfg["data"]
    g = df.groupby("venue_id")
    v = pd.DataFrame({
        "category": g["category"].agg(lambda s: s.mode().iloc[0]),
        "lat": g["lat"].median(),
        "lon": g["lon"].median(),
        "n": g.size(),
    })
    v = v[v["n"] >= dcfg["min_venue_checkins"]].copy()
    logn = np.log1p(v["n"].to_numpy(dtype=float))
    v["w"] = logn / logn.max()
    v["category"] = v["category"].astype(str)
    return v.reset_index().sort_values(["category", "venue_id"]).reset_index(drop=True)


def build(cfg: dict | None = None, n_bootstrap: int = 0, seed: int = 0) -> dict:
    cfg = cfg or load_config()
    df = pd.read_parquet(resolve(cfg["paths"]["interim"]) / "checkins_manhattan.parquet")
    out_dir = resolve(cfg["paths"]["processed"])
    out_dir.mkdir(parents=True, exist_ok=True)

    prof, meta = compute_profiles(df, cfg)
    venues = venue_table(df, cfg)
    venues.to_parquet(out_dir / "venues.parquet", index=False)
    arrays = {"profiles": prof}
    rng = np.random.default_rng(seed)
    for b in range(n_bootstrap):
        arrays[f"bootstrap_{b:02d}"] = compute_profiles(bootstrap_df(df, rng), cfg)[0]
    np.savez_compressed(out_dir / "profiles.npz", **arrays)
    with open(out_dir / "profiles_meta.json", "w", encoding="utf-8") as fh:
        json.dump({"categories": list(cfg["data"]["categories"]), "day_types": DAY_TYPES,
                   "meta": meta, "n_bootstrap": n_bootstrap}, fh, indent=2)

    print(f"eligible venues: {len(venues)}")
    print(venues.groupby("category").size().to_string())
    for cat, m in meta.items():
        print(f"{cat:20s} " + "  ".join(
            f"{dt}: peak {m[dt]['peak_hour']:2d}h ({m[dt]['source']}, n={m[dt]['checkins']})"
            for dt in DAY_TYPES))
    return {"profiles": prof, "meta": meta, "venues": venues}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    build(n_bootstrap=a.bootstrap, seed=a.seed)
