"""
Raw -> processed. Run: python -m src.collection.pipeline [--fx fx.json] [--today YYYY-MM-DD]

Reads every data/raw/<date>/*.jsonl, maps each row through its source adapter,
validates, de-duplicates, enriches, drops rows under the quality floor, and
writes data/processed/enriched.parquet plus data/processed/rejected.jsonl.
Appends one line per source to data/collection.log and exits non-zero if any
source's yield fell more than 50% against the previous day.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from . import quality
from .schema import Observation, adapter_for

ROOT = Path(__file__).resolve().parents[2]
YIELD_DROP_ALERT = 0.5


def read_raw(raw_dir: Path) -> tuple[pd.DataFrame, list[dict]]:
    rows, bad = [], []
    for path in sorted(raw_dir.glob("*/*.jsonl")):
        adapt = adapter_for(path.name)
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                obs = Observation(**adapt(json.loads(line)))
            except (ValidationError, KeyError, ValueError) as e:
                bad.append({"file": f"{path.parent.name}/{path.name}", "line": n,
                            "reject_reason": f"unparseable: {type(e).__name__}"})
                continue
            rows.append({**obs.model_dump(), "file_date": path.parent.name})
    return pd.DataFrame(rows), bad


def yield_by_source(df: pd.DataFrame) -> pd.DataFrame:
    """Rows per (file_date, source)."""
    return df.groupby(["file_date", "source"]).size().unstack(fill_value=0)


def yield_alerts(y: pd.DataFrame) -> list[str]:
    """Sources whose latest day is under half the previous day's rows."""
    if len(y) < 2:
        return []
    prev, last = y.iloc[-2], y.iloc[-1]
    return [f"{s}: {int(last[s])} rows on {y.index[-1]} vs {int(prev[s])} on {y.index[-2]}"
            for s in y.columns if prev[s] > 0 and last[s] < YIELD_DROP_ALERT * prev[s]]


def run(raw_dir: Path, out_dir: Path, fx: dict[str, float], today: pd.Timestamp) -> dict:
    df, unparseable = read_raw(raw_dir)
    if df.empty:
        return {"read": 0, "kept": 0, "rejected": len(unparseable), "alerts": []}
    n_read = len(df)
    df = quality.add_usd_price(df, fx)
    df, rejected = quality.validate(df, today)
    n_valid = len(df)
    if df.empty:
        low = pd.Series(dtype=bool)
    else:
        df = quality.dedupe(df)
        df = quality.enrich(df)
        low = df["data_quality_score"] < quality.MIN_QUALITY
    rejected = pd.concat([rejected, df[low].assign(reject_reason="quality_below_floor")])
    df = df[~low]
    # Yield is measured on what survived to this point, so a source going
    # quiet and a source going bad both register.
    alerts = yield_alerts(yield_by_source(df)) if not df.empty else []

    out_dir.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["file_date"]).to_parquet(out_dir / "enriched.parquet", index=False)
    with open(out_dir / "rejected.jsonl", "w") as f:
        for rec in unparseable + json.loads(rejected.to_json(orient="records", date_format="iso")):
            f.write(json.dumps(rec) + "\n")
    stats = {"read": n_read, "valid": n_valid, "deduped": int(len(df) + low.sum()),
             "kept": len(df), "rejected": len(rejected) + len(unparseable), "alerts": alerts}
    with open(ROOT / "data" / "collection.log", "a") as f:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for src, n in df.groupby("source").size().items():
            f.write(f"{stamp} source={src} rows={n}\n")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--fx", type=Path, help="JSON of local currency units per USD, e.g. {\"NGN\": 1550.3}")
    ap.add_argument("--today", default=None)
    a = ap.parse_args(argv)
    fx = json.loads(a.fx.read_text()) if a.fx else {}
    today = pd.Timestamp(a.today) if a.today else pd.Timestamp.today().normalize()
    stats = run(a.raw, a.out, fx, today)
    print(json.dumps(stats, indent=2))
    return 1 if stats["alerts"] else 0


if __name__ == "__main__":
    sys.exit(main())
