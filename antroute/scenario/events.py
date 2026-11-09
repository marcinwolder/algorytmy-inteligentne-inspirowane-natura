"""WP5: simulated events (docs/05-zdarzenia-i-scenariusze.md).

Event types: ``crowd_surge``, ``closure``, ``traffic``. Every event has a window [t_s, t_e] and an
announcement time ``announced`` (missing = known from the start of the day).

A venue can be given as a Foursquare Venue ID or as a selector resolved on the instance:
``"@top:<Category>"`` = the venue with the highest w_i of that category.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import yaml

from antroute.config import parse_hhmm

TYPES = ("crowd_surge", "closure", "traffic")
REQUIRED = {"crowd_surge": ("venue", "window"), "closure": ("venue", "window"),
            "traffic": ("center", "radius_m", "window", "factor")}
KNOWN_FIELDS = {"type", "venue", "window", "strength", "decay_min", "center", "radius_m",
                "factor", "announced"}


@dataclass(frozen=True)
class Event:
    type: str
    window: tuple[float, float]
    venue: str | None = None
    node: int | None = None              # resolved venue node in the instance
    strength: float = 1.0
    decay_min: float = 60.0
    center: tuple[float, float] | None = None
    radius_m: float = 0.0
    factor: float = 1.0
    announced: float | None = None        # None = known at the start of the day

    def known_at(self, t: float) -> bool:
        return self.announced is None or self.announced <= t


@dataclass
class Scenario:
    name: str = "none"
    day_type: str = "weekday"
    events: list[Event] = field(default_factory=list)

    def known(self, t: float | None) -> list[Event]:
        """Events visible to the planner at time t (None = all events, the ground truth)."""
        return list(self.events) if t is None else [e for e in self.events if e.known_at(t)]

    def announcements_after(self, t0: float) -> list[float]:
        return sorted({e.announced for e in self.events
                       if e.announced is not None and e.announced > t0})

    def resolve(self, instance) -> Scenario:
        """Return a copy with every venue reference mapped to an instance node."""
        out = []
        for e in self.events:
            if e.venue is None:
                out.append(e)
                continue
            if e.venue.startswith("@top:"):
                node = instance.top_venue(e.venue[5:])
            elif e.venue in instance.venue_ids:
                node = instance.node_of(e.venue)
            else:
                raise ValueError(f"event venue {e.venue!r} is not in the instance")
            out.append(replace(e, node=node))
        return Scenario(self.name, self.day_type, out)

    def venue_ids(self) -> list[str]:
        return [e.venue for e in self.events if e.venue and not e.venue.startswith("@")]


def parse_event(d: dict) -> Event:
    if d.get("type") not in TYPES:
        raise ValueError(f"unknown event type: {d.get('type')!r}")
    unknown = set(d) - KNOWN_FIELDS
    if unknown:
        raise ValueError(f"unknown event fields: {sorted(unknown)}")
    missing = [f for f in REQUIRED[d["type"]] if f not in d]
    if missing:
        raise ValueError(f"{d['type']}: missing fields {missing}")
    ts, te = (parse_hhmm(x) for x in d["window"])
    if te <= ts:
        raise ValueError(f"empty window {d['window']}")
    ev = Event(type=d["type"], window=(ts, te), venue=d.get("venue"),
               strength=float(d.get("strength", 1.0)), decay_min=float(d.get("decay_min", 60.0)),
               center=tuple(d["center"]) if "center" in d else None,
               radius_m=float(d.get("radius_m", 0.0)), factor=float(d.get("factor", 1.0)),
               announced=parse_hhmm(d["announced"]) if "announced" in d else None)
    if not 0.0 <= ev.strength <= 1.0:
        raise ValueError("strength must be in [0, 1]")
    if ev.type == "traffic" and ev.factor <= 1.0:
        raise ValueError("traffic factor must be > 1")
    if ev.decay_min <= 0:
        raise ValueError("decay_min must be > 0")
    return ev


def load_scenario(src: str | Path | dict | None) -> Scenario:
    """Load a scenario from a YAML path, a dict, or None (no events)."""
    if src is None:
        return Scenario()
    if isinstance(src, (str, Path)):
        with open(src, encoding="utf-8") as fh:
            src = yaml.safe_load(fh)
    return Scenario(name=src.get("name", "scenario"), day_type=src.get("day_type", "weekday"),
                    events=[parse_event(e) for e in src.get("events") or []])


# ---------------------------------------------------------------- arrays for the kernels

def segment_hits_circle(lat, lon, center, radius_m) -> np.ndarray:
    """(n, n) mask: the straight segment i-j passes within radius_m of center (D4)."""
    lat0, lon0 = center
    kx = 111_320.0 * np.cos(np.radians(lat0))
    ky = 110_540.0
    x = (np.asarray(lon) - lon0) * kx
    y = (np.asarray(lat) - lat0) * ky
    ax, ay = x[:, None], y[:, None]
    bx, by = x[None, :], y[None, :]
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    with np.errstate(invalid="ignore", divide="ignore"):
        u = np.where(seg2 > 0, -(ax * dx + ay * dy) / seg2, 0.0)
    u = np.clip(u, 0.0, 1.0)
    px, py = ax + u * dx, ay + u * dy
    mask = px * px + py * py <= radius_m * radius_m
    np.fill_diagonal(mask, False)
    return mask


def venues_in_circle(lat, lon, center, radius_m) -> np.ndarray:
    """(n,) mask: the venue lies within radius_m of center (node 0 = start is never marked)."""
    lat0, lon0 = center
    x = (np.asarray(lon) - lon0) * 111_320.0 * np.cos(np.radians(lat0))
    y = (np.asarray(lat) - lat0) * 110_540.0
    mask = x * x + y * y <= radius_m * radius_m
    mask[0] = False
    return mask


def event_arrays(events: list[Event], instance) -> dict[str, np.ndarray]:
    n1 = instance.n + 1
    surge = [(e.node, *e.window, e.strength, e.decay_min) for e in events if e.type == "crowd_surge"]
    closure = [(e.node, *e.window) for e in events if e.type == "closure"]
    traffic = [e for e in events if e.type == "traffic"]
    return {
        "surge": np.array(surge, dtype=np.float64).reshape(-1, 5),
        "closure": np.array(closure, dtype=np.float64).reshape(-1, 3),
        "traffic": np.array([(*e.window, e.factor) for e in traffic], dtype=np.float64).reshape(-1, 3),
        "tmask": (np.stack([segment_hits_circle(instance.lat, instance.lon, e.center, e.radius_m)
                            for e in traffic]) if traffic else np.zeros((0, n1, n1), dtype=np.bool_)),
        "tnode": (np.stack([venues_in_circle(instance.lat, instance.lon, e.center, e.radius_m)
                            for e in traffic]) if traffic else np.zeros((0, n1), dtype=np.bool_)),
    }
