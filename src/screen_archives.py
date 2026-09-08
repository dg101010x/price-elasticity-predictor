"""
The search that produced the reference roster, kept so the claim is checkable.

`src/reference_data.py` says twelve datasets were chosen out of three public
archives. This is the script that did the choosing. It clones the archives,
reads every CSV in them, and reports which files carry both a usable price
column and a usable quantity column.

The screen is deliberately mechanical -- a column is a price if its name
looks like one *and* its values are numeric and positive; a quantity if its
name looks like one and its values are numeric and non-negative. Judgement
comes afterwards and by hand: every candidate it returns still has to be read
against its own documentation, which is where the three simulated datasets
were caught (ISLR/Carseats, Stat2Data/Grocery, sem/Kmenta all pass this
screen and all had to be thrown out).

Run: python -m src.screen_archives            # uses ./data/archives
     python -m src.screen_archives --skip-clone
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = ROOT / "data" / "archives"
REPORT_PATH = ROOT / "data" / "manifests" / "archive_screen.json"

ARCHIVES = {
    "Rdatasets": "https://github.com/vincentarelbundock/Rdatasets",
    "tidytuesday": "https://github.com/rfordatascience/tidytuesday",
    "plotly-datasets": "https://github.com/plotly/datasets",
}

PRICE = re.compile(r"pric|\bcost\b|\bfare\b|tariff|^p$|^lp$", re.I)
QUANTITY = re.compile(
    r"qty|quant|^units?$|volume|sales|sold|^move$|logmove|demand|consum|packs|"
    r"^amount$|purchas|^q$|turnover", re.I
)

MAX_FILE_BYTES = 300_000_000


def clone(name: str, url: str) -> Path:
    dest = ARCHIVE_DIR / name
    if dest.exists():
        print(f"  {name}: already present")
        return dest
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  {name}: cloning ...")
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        check=True, capture_output=True,
        env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"},
    )
    return dest


def screen(root: Path) -> dict:
    files, candidates = [], []
    total_rows = total_cells = 0

    for dirpath, _, filenames in os.walk(root):
        if ".git" in Path(dirpath).parts:
            continue
        for name in filenames:
            if name.lower().endswith(".csv"):
                files.append(Path(dirpath) / name)

    for path in files:
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            frame = pd.read_csv(path, low_memory=False)
        except Exception:
            continue

        total_rows += len(frame)
        total_cells += len(frame) * frame.shape[1]

        numeric = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
        prices = [
            c for c in numeric
            if PRICE.search(str(c)) and len(frame[c].dropna()) and frame[c].dropna().gt(0).mean() > 0.9
        ]
        quantities = [
            c for c in numeric
            if QUANTITY.search(str(c)) and len(frame[c].dropna()) and frame[c].dropna().ge(0).mean() > 0.9
        ]
        if prices and quantities:
            candidates.append({
                "file": str(path.relative_to(root)),
                "rows": int(len(frame)),
                "columns": int(frame.shape[1]),
                "price_columns": prices[:5],
                "quantity_columns": quantities[:5],
            })

    return {
        "files_screened": len(files),
        "rows_screened": total_rows,
        "cells_screened": total_cells,
        "candidates": sorted(candidates, key=lambda c: -c["rows"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-clone", action="store_true",
                        help="screen whatever is already in data/archives")
    args = parser.parse_args()

    report, totals = {}, {"files": 0, "rows": 0, "cells": 0, "candidates": 0}
    for name, url in ARCHIVES.items():
        path = ARCHIVE_DIR / name if args.skip_clone else clone(name, url)
        if not path.exists():
            print(f"  {name}: not present, skipping")
            continue
        result = screen(path)
        report[name] = result
        totals["files"] += result["files_screened"]
        totals["rows"] += result["rows_screened"]
        totals["cells"] += result["cells_screened"]
        totals["candidates"] += len(result["candidates"])
        print(f"  {name}: {result['files_screened']:,} files | "
              f"{result['rows_screened']:,} rows | {len(result['candidates'])} candidates")

    report["totals"] = totals
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    print(f"\nScreened {totals['files']:,} CSV files | {totals['rows']:,} rows | "
          f"{totals['cells']:,} values")
    print(f"{totals['candidates']} carried both a price and a quantity column.")
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
