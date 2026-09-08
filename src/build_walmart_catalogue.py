"""
Turns the M5 Walmart files into the second catalogue the API serves.

Writes:
  data/processed/walmart_results.json    overall + by_category + by_department + by_state
  data/processed/walmart_products.json   per-item directory for the product picker

Shape of the work
-----------------
M5 ships daily units in a wide matrix (30,490 store-item series across 1,941
day columns) and shelf prices weekly (6,841,121 rows keyed on store, item and
Walmart week). Prices are the coarser of the two, so units are rolled up to
the same weekly grain rather than prices being interpolated down to daily.
That also matches how the UK catalogue is fitted, which is what lets the two
sit on one axis.

The day columns are already in date order and each Walmart week is a
contiguous run of them, so the rollup is a single reduceat over the matrix
rather than a melt of 59 million rows followed by a groupby.

An item that a store had not started carrying yet has no price row for that
week, so the join drops it. Weeks where a stocked item sold nothing are real
zeros and cannot go through a log, so they drop too. Both are stated in the
output.

Run: python -m src.build_walmart_catalogue
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .panel_regression import within_entity_loglog
from .walmart_data import CANONICAL_SOURCE, WALMART_DIR

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Same bar as the UK catalogue: a group is only reported when it has enough
# behind it to mean something.
MIN_OBSERVATIONS = 500
MIN_SERIES = 15

CATEGORY_LABELS = {"FOODS": "Foods", "HOBBIES": "Hobbies", "HOUSEHOLD": "Household"}
STATE_LABELS = {"CA": "California", "TX": "Texas", "WI": "Wisconsin"}


def _department_label(dept_id: str) -> str:
    """FOODS_3 -> 'Foods, aisle 3'.

    M5 published the department numbers but not what they contain, so the
    label says aisle rather than inventing a name for it.
    """
    head, _, number = dept_id.rpartition("_")
    return f"{CATEGORY_LABELS.get(head, head.title())}, aisle {number}"


def weekly_panel() -> pd.DataFrame:
    """Roll the daily matrix up to store-item-week and attach shelf prices."""
    calendar = pd.read_csv(WALMART_DIR / "calendar.csv", usecols=["d", "wm_yr_wk", "date"])

    print("  reading the daily sales matrix ...")
    sales = pd.read_csv(WALMART_DIR / "sales_train_evaluation.csv")
    id_cols = ["item_id", "dept_id", "cat_id", "store_id", "state_id"]
    day_cols = [c for c in sales.columns if c.startswith("d_")]

    # calendar is in day order; line the weeks up with the columns we have
    cal = calendar.set_index("d").loc[day_cols]
    weeks = cal["wm_yr_wk"].to_numpy()
    starts = np.flatnonzero(np.r_[True, weeks[1:] != weeks[:-1]])
    week_ids = weeks[starts]

    units = sales[day_cols].to_numpy(dtype=np.int32)
    print(f"  {units.shape[0]:,} series x {units.shape[1]:,} days "
          f"= {units.size:,} daily records")

    weekly = np.add.reduceat(units, starts, axis=1)
    del units
    print(f"  rolled up to {weekly.shape[0]:,} series x {weekly.shape[1]:,} weeks")

    panel = pd.DataFrame(weekly, columns=week_ids)
    del weekly
    for col in id_cols:
        panel[col] = sales[col].to_numpy()
    del sales

    panel = panel.melt(id_vars=id_cols, var_name="wm_yr_wk", value_name="units")
    panel["wm_yr_wk"] = panel["wm_yr_wk"].astype(np.int32)
    print(f"  {len(panel):,} store-item-weeks before prices are joined")

    prices = pd.read_csv(WALMART_DIR / "sell_prices.csv")
    panel = panel.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="inner")
    print(f"  {len(panel):,} left once weeks the item was not yet stocked are dropped")

    panel["series"] = panel["item_id"] + "|" + panel["store_id"]
    return panel


def fit(frame: pd.DataFrame, label: str) -> dict | None:
    result = within_entity_loglog(frame, entity="series", price="sell_price", quantity="units")
    if result is None:
        return None
    result["category"] = label
    result["n_skus"] = result.pop("n_entities")
    return result


def _group(panel: pd.DataFrame, column: str, labeller) -> tuple[list, list]:
    reported, excluded = [], []
    for key, group in panel.groupby(column, observed=True):
        label = labeller(key)
        series = group["series"].nunique()
        if len(group) < MIN_OBSERVATIONS or series < MIN_SERIES:
            excluded.append({"category": label,
                             "reason": f"insufficient data ({len(group)} weeks across {series} lines)"})
            continue
        result = fit(group, label)
        if result is None:
            excluded.append({"category": label,
                             "reason": "no within-line price variation, so no slope is identified"})
            continue
        reported.append(result)
    reported.sort(key=lambda r: r["elasticity"])
    return reported, excluded


def main() -> None:
    panel = weekly_panel()

    sold = panel[panel["units"] > 0]
    print(f"  {len(sold):,} of those weeks had at least one sale\n")

    overall = fit(sold, "Whole range")
    if overall is None:
        raise SystemExit("Overall regression could not identify a slope.")
    print(f"  overall: {overall['elasticity']:+.3f}  (n={overall['n_observations']:,})")

    by_category, excluded_c = _group(sold, "cat_id", lambda k: CATEGORY_LABELS.get(k, k.title()))
    by_department, excluded_d = _group(sold, "dept_id", _department_label)
    by_state, excluded_s = _group(sold, "state_id", lambda k: STATE_LABELS.get(k, k))

    for row in by_category + by_department + by_state:
        print(f"  {row['elasticity']:+.3f}  {row['category']:<22} n={row['n_observations']:>9,}")

    results = {
        "market": {
            "key": "walmart",
            "label": "US Walmart, food and household",
            "short_label": "Walmart",
            "currency": "USD",
            "period": "January 2011 to June 2016",
            "where": "10 Walmart stores across California, Texas and Wisconsin",
        },
        "overall": overall,
        "by_category": by_category,
        "by_department": by_department,
        "by_state": by_state,
        "excluded_categories": excluded_c + excluded_d + excluded_s,
        "scale": {
            "daily_records": 59_181_090,
            "store_item_weeks": int(len(panel)),
            "weeks_with_a_sale": int(len(sold)),
            "price_observations": 6_841_121,
            "items": int(panel["item_id"].nunique()),
            "stores": int(panel["store_id"].nunique()),
            "series": int(panel["series"].nunique()),
        },
        "methodology": {
            "method": "within-line (fixed-effects) log-log panel regression, weekly",
            "source_dataset": f"M5 Forecasting Accuracy, M Open Forecasting Center ({CANONICAL_SOURCE})",
            "category_assignment": "the retailer's own hierarchy: 3 categories, 7 departments. Not inferred.",
            "cleaning": (
                "Units are rolled up from daily to the Walmart week that shelf prices "
                "are quoted in. Weeks before a store carried an item have no price row "
                "and are dropped by the join. Weeks where a stocked item sold nothing "
                "are real zeros and cannot go through a log, so they are dropped too, "
                "which means these estimates describe weeks the item was actually moving."
            ),
            "exclusion_thresholds": f">= {MIN_OBSERVATIONS} weeks and >= {MIN_SERIES} store-item lines",
            "note": (
                "Descriptive association from observational data, not a causal effect. "
                "Walmart set these prices for its own reasons, and those reasons moved "
                "sales as well."
            ),
        },
    }

    out = OUT_DIR / "walmart_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out} ({len(by_category)} categories, {len(by_department)} departments, "
          f"{len(by_state)} states)")

    products = (
        panel.groupby("item_id", observed=True)
        .agg(category=("cat_id", "first"), department=("dept_id", "first"),
             typical_price=("sell_price", "median"))
        .reset_index().rename(columns={"item_id": "product_id"})
    )
    products["product_name"] = products["product_id"].str.replace("_", " ").str.title()
    products["category"] = products["category"].map(lambda k: CATEGORY_LABELS.get(k, k.title()))
    products["department"] = products["department"].map(_department_label)
    products["currency"] = "USD"
    products["typical_price"] = products["typical_price"].round(2)
    products = products[["product_id", "product_name", "category", "department",
                         "currency", "typical_price"]]

    out_p = OUT_DIR / "walmart_products.json"
    out_p.write_text(json.dumps(products.to_dict(orient="records"), indent=2))
    print(f"Wrote {out_p} ({len(products):,} items)")


if __name__ == "__main__":
    main()
