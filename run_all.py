"""K1: the whole pipeline with one command.

    uv run python run_all.py                 # data -> profiles -> experiments -> SUMMARY.md
    uv run python run_all.py --seeds 3 --out runs/quick --no-cpsat   # fast check

The raw file data/raw/dataset_TSMC2014_NYC.txt and data/raw/manhattan.geojson must exist
(see README.md, section "Dane").
"""

from __future__ import annotations

import argparse
import subprocess
import sys

EXPERIMENTS = ["E1", "E2", "E4", "E5", "E6", "E7", "E8", "E10", "E11", "E12", "E13b"]


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-data", action="store_true", help="reuse data/interim and processed")
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--out", default="results")
    ap.add_argument("--no-cpsat", action="store_true")
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--experiments", nargs="*", default=EXPERIMENTS)
    a = ap.parse_args()
    if not a.skip_data:
        run("-m", "antroute.data.prepare")
        run("-m", "antroute.model.profiles", "--bootstrap", "20")
    exp_args = ["-m", "antroute.experiments.run", *a.experiments, "--out", a.out]
    if a.seeds:
        exp_args += ["--seeds", str(a.seeds)]
    if a.no_cpsat:
        exp_args.append("--no-cpsat")
    if a.processes:
        exp_args += ["--processes", str(a.processes)]
    run(*exp_args)
    run("-m", "antroute.report.summary", "--results", a.out)


if __name__ == "__main__":
    main()
