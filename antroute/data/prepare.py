"""WP1: raw Foursquare TSV -> check-ins with local time, Manhattan filter, selected categories.

Usage: python -m antroute.data.prepare
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

from antroute.config import load_config, resolve

COLUMNS = ["user_id", "venue_id", "category_id", "category", "lat", "lon", "tz_offset", "utc_time"]


def read_raw(path: str | Path) -> pd.DataFrame:
    """Read the raw TSV (no header, ISO-8859-1) and add local time columns."""
    df = pd.read_csv(
        path, sep="\t", header=None, names=COLUMNS, encoding="ISO-8859-1",
        dtype={"user_id": "int32", "venue_id": "string", "category_id": "string",
               "category": "string", "lat": "float64", "lon": "float64", "tz_offset": "int32",
               "utc_time": "string"},
    )
    utc = pd.to_datetime(df["utc_time"], format="%a %b %d %H:%M:%S %z %Y", utc=True)
    local = utc.dt.tz_localize(None) + pd.to_timedelta(df["tz_offset"], unit="min")
    df["local_time"] = local
    df["hour"] = local.dt.hour.astype("int8")
    df["date"] = local.dt.normalize()
    df["weekend"] = local.dt.day_of_week >= 5
    return df.drop(columns=["utc_time"])


def load_polygon(path: str | Path):
    """Load the Manhattan (multi)polygon from GeoJSON."""
    with open(path, encoding="utf-8") as fh:
        gj = json.load(fh)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    return unary_union([shape(f["geometry"]) for f in feats])


def in_polygon(df: pd.DataFrame, polygon) -> np.ndarray:
    """Vectorised point-in-polygon test (GeoJSON order is lon, lat)."""
    shapely.prepare(polygon)
    return shapely.contains_xy(polygon, df["lon"].to_numpy(), df["lat"].to_numpy())


def hourly_counts(df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    """Check-ins per (category, local hour) - same layout as docs/data/hourly_checkins_nyc.csv."""
    sub = df[df["category"].isin(categories)]
    table = (sub.groupby(["category", "hour"]).size().unstack(fill_value=0)
             .reindex(index=categories, columns=range(24), fill_value=0))
    table.columns = [f"h{h:02d}" for h in range(24)]
    return table


def prepare(cfg: dict | None = None) -> dict[str, Path]:
    cfg = cfg or load_config()
    paths = cfg["paths"]
    interim = resolve(paths["interim"])
    interim.mkdir(parents=True, exist_ok=True)

    df = read_raw(resolve(paths["raw_checkins"]))
    nyc_path = interim / "checkins_nyc.parquet"
    df.to_parquet(nyc_path, index=False)

    categories = list(cfg["data"]["categories"])
    polygon = load_polygon(resolve(paths["manhattan_polygon"]))
    man = df[df["category"].isin(categories)].copy()
    man = man[in_polygon(man, polygon)]
    man_path = interim / "checkins_manhattan.parquet"
    man.to_parquet(man_path, index=False)

    report = (man.groupby("category")
              .agg(checkins=("venue_id", "size"), venues=("venue_id", "nunique"))
              .reindex(categories))
    report["weekday_checkins"] = man[~man["weekend"]].groupby("category").size().reindex(categories)
    report["weekend_checkins"] = man[man["weekend"]].groupby("category").size().reindex(categories)
    report_path = interim / "manhattan_report.csv"
    report.to_csv(report_path)
    print(f"NYC check-ins: {len(df)}; Manhattan, selected categories: {len(man)}")
    print(report.to_string())
    return {"nyc": nyc_path, "manhattan": man_path, "report": report_path}


if __name__ == "__main__":
    prepare()
