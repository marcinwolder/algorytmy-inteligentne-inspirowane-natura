"""Configuration loading. All parameters live in config/default.yaml; code has no magic numbers."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "default.yaml"


def deep_merge(base: dict, override: dict | None) -> dict:
    """Return a copy of ``base`` with ``override`` merged in recursively."""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path: str | Path | None = None, override: dict | None = None) -> dict[str, Any]:
    """Load the default config, then an optional extra YAML file, then an override dict."""
    with open(DEFAULT_CONFIG, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            cfg = deep_merge(cfg, yaml.safe_load(fh))
    return deep_merge(cfg, override)


def resolve(path: str | Path) -> Path:
    """Resolve a path from the config relative to the repository root."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def parse_hhmm(value: str | int | float) -> float:
    """Convert "HH:MM" (or minutes as a number) to minutes from midnight."""
    if isinstance(value, (int, float)):
        return float(value)
    hh, mm = str(value).split(":")
    return float(int(hh) * 60 + int(mm))


def fmt_hhmm(minutes: float) -> str:
    """Convert minutes from midnight to "HH:MM" (hours can exceed 24 for the next day)."""
    m = int(round(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"
