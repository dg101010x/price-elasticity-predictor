"""
Fits the twelve reference markets in data/csv/reference/ and writes

    data/processed/reference_benchmarks.json

which the API serves at /benchmarks and the page uses to answer "is my
category unusual, or does everything behave like this?".

Each market goes through the estimator in src/panel_regression.py that best
matches its shape -- within-entity for panels, pooled for single series,
choice-share for scanner panels -- and every result carries the estimator
that produced it, so the page can show the weaker designs as weaker.

Run: python -m src.build_reference_benchmarks
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .panel_regression import choice_share_loglog, pooled_loglog, within_entity_loglog
from .reference_data import REFERENCE_DATASETS, REFERENCE_DIR, ReferenceSpec

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# How much weight the page should give each design. The within-entity panels
# compare a product against its own history; the single series can't.
CONFIDENCE = {
    "panel": "within-market comparison: each place or show measured against its own history",
    "series": "single market over time: no cross-section to compare against, so read with care",
    "choice": "scanner panel: brand share of purchases against that brand's own shelf price",
}


def fit(spec: ReferenceSpec) -> dict | None:
    path = REFERENCE_DIR / spec.filename
    if not path.exists():
        return None
    df = pd.read_csv(path, low_memory=False)

    price_col = spec.price
    if spec.deflator and spec.deflator in df.columns:
        df = df.copy()
        df["_real_price"] = df[spec.price] / df[spec.deflator]
        price_col = "_real_price"

    if spec.estimator == "panel":
        result = within_entity_loglog(df, entity=spec.entity, price=price_col, quantity=spec.quantity)
    elif spec.estimator == "series":
        result = pooled_loglog(df, price=price_col, quantity=spec.quantity)
    elif spec.estimator == "choice":
        brands = {k: v for k, v in spec.brands.items() if v in df.columns}
        if not brands:
            return None
        result = choice_share_loglog(df, choice_column=spec.choice_column, brands=brands)
    else:
        raise ValueError(f"unknown estimator {spec.estimator!r}")

    if result is None:
        return None

    result.update({
        "key": spec.key,
        "label": spec.label,
        "market": spec.market,
        "source": spec.source,
        "estimator": spec.estimator,
        "estimator_note": CONFIDENCE[spec.estimator],
        "rows_in_dataset": int(len(df)),
        "real_prices": bool(spec.deflator),
    })
    result.update(_flag(result))
    if spec.note:
        result["note"] = spec.note
    return result


def _flag(result: dict) -> dict:
    """Mark the estimates that shouldn't be read as a price response.

    Two failure modes are worth naming rather than burying. An interval that
    spans zero means the data cannot tell you the sign, let alone the size. A
    slope that is positive with an interval entirely above zero is not a
    demand curve at all -- it is a demand *shock* showing through, where
    whatever made people want the thing more also let the seller charge more.
    """
    low, high = result["ci_low"], result["ci_high"]
    if low <= 0 <= high:
        return {
            "flag": "inconclusive",
            "flag_reason": (
                "The confidence interval spans zero, so this data cannot tell you "
                "whether a price rise moves volume up, down, or not at all."
            ),
        }
    if result["elasticity"] > 0:
        return {
            "flag": "confounded",
            "flag_reason": (
                "The slope comes out positive: higher prices go with *more* sold. "
                "That is not a demand curve, it is demand shocks showing through -- "
                "whatever made people want it more also let the seller charge more. "
                "Kept here because it is the clearest illustration of why every "
                "number on this page is a pattern and not a promise."
            ),
        }
    return {"flag": None}


def main() -> None:
    benchmarks, skipped = [], []
    for spec in REFERENCE_DATASETS:
        result = fit(spec)
        if result is None:
            skipped.append({"key": spec.key, "label": spec.label,
                            "reason": "dataset missing, or the data could not identify a slope"})
            print(f"  [skipped ] {spec.label}")
            continue
        benchmarks.append(result)
        print(f"  [{result['elasticity']:>7.3f}] {spec.label:<36} "
              f"n={result['n_observations']:>6,}  ({spec.estimator})")

    benchmarks.sort(key=lambda r: r["elasticity"])

    payload = {
        "benchmarks": benchmarks,
        "skipped": skipped,
        "totals": {
            "datasets": len(benchmarks),
            "usable_benchmarks": sum(1 for b in benchmarks if not b.get("flag")),
            "rows_across_datasets": sum(b["rows_in_dataset"] for b in benchmarks),
            "observations_fitted": sum(b["n_observations"] for b in benchmarks),
        },
        "methodology": {
            "estimators": CONFIDENCE,
            "selection": (
                "Every CSV in three public archives -- Rdatasets, TidyTuesday and "
                "plotly/datasets: 5,960 files, 64,502,749 rows, 656,584,040 values -- was "
                "profiled for a positive numeric price column alongside a non-negative "
                "numeric quantity column. That screen returned 26 candidates, each of which "
                "was then read against its own documentation; three were rejected for being "
                "simulated rather than observed (ISLR/Carseats, Stat2Data/Grocery, "
                "sem/Kmenta)."
            ),
            "note": (
                "Descriptive associations from observational data, not causal effects. "
                "None of these markets ran a pricing experiment."
            ),
        },
    }

    out = OUT_DIR / "reference_benchmarks.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out} ({len(benchmarks)} benchmarks, "
          f"{payload['totals']['rows_across_datasets']:,} source rows)")


if __name__ == "__main__":
    main()
