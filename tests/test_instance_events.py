"""WP3 / WP5: instance building and scenario parsing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import make_instance, needs_data

from antroute.config import load_config
from antroute.model.instance import build_instance, haversine_km, stratified_counts, walk_matrix
from antroute.scenario.events import load_scenario, segment_hits_circle


def test_haversine_one_degree_latitude():
    assert haversine_km(40.0, -74.0, 41.0, -74.0) == pytest.approx(111.19, abs=0.05)


def test_walk_matrix_properties():
    lat = np.array([40.7580, 40.7359])
    lon = np.array([-73.9855, -73.9911])
    T = walk_matrix(lat, lon, 5.0, 1.3)
    assert T[0, 0] == 0 and T[1, 1] == 0
    assert T[0, 1] == pytest.approx(T[1, 0])
    d = haversine_km(lat[0], lon[0], lat[1], lon[1])
    assert T[0, 1] == pytest.approx(d * 1.3 / 5.0 * 60.0)
    assert 35 < T[0, 1] < 45          # Times Square -> Union Square ~ 2.5 km on foot


def test_stratified_counts():
    avail = pd.Series({"A": 100, "B": 10, "C": 1})
    c = stratified_counts(avail, 20, 1)
    assert sum(c.values()) == 20
    assert all(v >= 1 for v in c.values())
    assert c["C"] == 1 and c["A"] > c["B"]
    with pytest.raises(ValueError):
        stratified_counts(avail, 200, 1)


@needs_data
def test_build_instance_is_deterministic_and_stratified():
    cfg = load_config()
    a = build_instance(50, "times_square", seed=3, cfg=cfg)
    b = build_instance(50, "times_square", seed=3, cfg=cfg)
    assert a.venue_ids == b.venue_ids
    assert a.n == 50
    assert set(a.cat[1:]) == set(range(len(cfg["data"]["categories"])))   # every category
    assert np.allclose(a.T, a.T.T) and np.allclose(np.diag(a.T), 0)
    c = build_instance(50, "times_square", seed=4, cfg=cfg)
    assert c.venue_ids != a.venue_ids


@needs_data
def test_build_instance_include_and_save_load(tmp_path):
    cfg = load_config()
    a = build_instance(25, "wall_street", cfg=cfg)
    same = build_instance(25, "wall_street", cfg=cfg, include=[a.venue_ids[5]])
    assert same.venue_ids == a.venue_ids           # venue already present -> same instance
    big = build_instance(100, "wall_street", cfg=cfg)
    outside = next(v for v in big.venue_ids[1:] if v not in a.venue_ids)
    forced = build_instance(25, "wall_street", cfg=cfg, include=[outside])
    assert outside in forced.venue_ids and forced.n == 25
    a.save(tmp_path / "inst")
    from antroute.model.instance import Instance
    b = Instance.load(tmp_path / "inst")
    assert b.venue_ids == a.venue_ids and np.allclose(b.T, a.T)


def test_scenario_parsing_and_validation():
    sc = load_scenario({"name": "x", "day_type": "weekend", "events": [
        {"type": "crowd_surge", "venue": "v1", "window": ["10:00", "13:00"], "strength": 1.0,
         "decay_min": 60, "announced": "11:00"},
        {"type": "closure", "venue": "v2", "window": ["08:00", "12:00"]},
        {"type": "traffic", "center": [40.75, -73.98], "radius_m": 400,
         "window": ["12:00", "15:00"], "factor": 2.0}]})
    assert sc.day_type == "weekend"
    assert sc.events[0].window == (600.0, 780.0)
    assert sc.events[0].announced == 660.0
    assert len(sc.known(480.0)) == 2 and len(sc.known(None)) == 3
    assert sc.announcements_after(480.0) == [660.0]
    for bad in ({"type": "flood", "window": ["10:00", "11:00"]},
                {"type": "closure", "window": ["10:00", "11:00"]},
                {"type": "closure", "venue": "v", "window": ["11:00", "10:00"]},
                {"type": "traffic", "center": [0, 0], "radius_m": 1, "window": ["1:00", "2:00"],
                 "factor": 0.5},
                {"type": "closure", "venue": "v", "window": ["10:00", "11:00"], "colour": 1}):
        with pytest.raises(ValueError):
            load_scenario({"events": [bad]})


def test_scenario_resolves_selectors():
    inst = make_instance(cats=[0, 1, 1], w=[0.3, 0.4, 0.9])
    sc = load_scenario({"events": [{"type": "closure", "venue": "@top:B",
                                    "window": ["08:00", "09:00"]}]}).resolve(inst)
    assert sc.events[0].node == 3
    with pytest.raises(ValueError):
        load_scenario({"events": [{"type": "closure", "venue": "nope",
                                   "window": ["08:00", "09:00"]}]}).resolve(inst)


def test_segment_hits_circle():
    lat = np.array([40.75, 40.75, 40.80])
    lon = np.array([-74.00, -73.96, -74.00])
    m = segment_hits_circle(lat, lon, (40.75, -73.98), 300)
    assert m[0, 1] and m[1, 0]          # passes through the centre
    assert not m[0, 2]                   # far away
    assert not m[0, 0]
