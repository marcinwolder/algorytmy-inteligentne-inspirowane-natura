"""WP1 / WP2: data preparation (K2) and profiles."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import needs_data

from antroute.config import ROOT, load_config, resolve
from antroute.model.profiles import compute_profiles, normalise, smooth_cyclic, venue_table

RAW = resolve(load_config()["paths"]["raw_checkins"])
needs_raw = pytest.mark.skipif(not RAW.exists(), reason="raw Foursquare file missing")


@needs_raw
def test_k2_hourly_counts_match_reference():
    """K2: local time conversion reproduces docs/data/hourly_checkins_nyc.csv exactly."""
    from antroute.data.prepare import hourly_counts, read_raw

    df = read_raw(RAW)
    assert len(df) == 227_428
    ref = pd.read_csv(ROOT / "docs" / "data" / "hourly_checkins_nyc.csv", index_col="category")
    got = hourly_counts(df, list(ref.index))
    hours = [f"h{h:02d}" for h in range(24)]
    assert (got[hours].to_numpy() == ref[hours].to_numpy()).all()
    assert (got[hours].sum(axis=1).to_numpy() == ref["total"].to_numpy()).all()
    assert (got[hours].to_numpy().argmax(axis=1) == ref["peak_hour"].to_numpy()).all()


@needs_raw
def test_manhattan_filter_keeps_only_points_in_polygon():
    from antroute.data.prepare import in_polygon, load_polygon

    poly = load_polygon(resolve(load_config()["paths"]["manhattan_polygon"]))
    pts = pd.DataFrame({"lat": [40.7580, 40.6782, 40.7794], "lon": [-73.9855, -73.9442, -73.9632]})
    assert list(in_polygon(pts, poly)) == [True, False, True]    # Brooklyn is out


def test_smoothing_is_cyclic():
    h = np.zeros(24)
    h[0] = 3.0
    s = smooth_cyclic(h, 3)
    assert s[23] == pytest.approx(1.0) and s[0] == pytest.approx(1.0) and s[1] == pytest.approx(1.0)
    assert s.sum() == pytest.approx(3.0)


def test_normalise_max_is_one():
    p = normalise(np.array([1.0, 4.0, 2.0]))
    assert p.max() == 1.0 and p.min() >= 0.0


def synthetic_checkins():
    rows = []
    for d in range(14):
        date = pd.Timestamp("2012-05-07") + pd.Timedelta(days=d)
        for h, n in [(9, 30), (13, 10)]:
            rows += [{"category": "Coffee Shop", "hour": h, "date": date,
                      "weekend": date.day_of_week >= 5, "venue_id": f"c{i % 3}",
                      "lat": 40.75, "lon": -73.99} for i in range(n)]
        rows += [{"category": "Museum", "hour": 14, "date": date, "weekend": date.day_of_week >= 5,
                  "venue_id": "m1", "lat": 40.77, "lon": -73.96}]
    return pd.DataFrame(rows)


def test_profiles_and_d5_fallback():
    cfg = load_config()
    cfg["data"]["categories"] = {"Coffee Shop": 20, "Museum": 90}
    prof, meta = compute_profiles(synthetic_checkins(), cfg)
    assert prof.shape == (2, 3, 24)
    assert prof.max(axis=2) == pytest.approx(np.ones((2, 3)))
    assert prof[0, 0, 9] == pytest.approx(1.0)          # 9:00 peak keeps the maximum
    assert meta["Coffee Shop"]["weekday"]["source"] == "Coffee Shop/weekday"
    # Museum has 14 check-ins < 100 -> falls back (all days, then the group), never crashes
    assert meta["Museum"]["weekday"]["source"].startswith("Museum")
    assert meta["Museum"]["weekday"]["checkins"] == 14


def test_venue_weights():
    cfg = load_config(override={"data": {"min_venue_checkins": 1}})
    v = venue_table(synthetic_checkins(), cfg)
    assert v["w"].max() == pytest.approx(1.0)
    assert (v["w"] > 0).all()
    n = v.set_index("venue_id")["n"]
    assert v.set_index("venue_id")["w"]["m1"] == pytest.approx(np.log1p(n["m1"]) / np.log1p(n.max()))


@needs_data
def test_processed_profiles_are_valid():
    cfg = load_config()
    with np.load(resolve(cfg["paths"]["processed"]) / "profiles.npz") as arr:
        prof = arr["profiles"]
    assert prof.shape == (len(cfg["data"]["categories"]), 3, 24)
    assert np.allclose(prof.max(axis=2), 1.0)
    assert prof.min() >= 0.0
