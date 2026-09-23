"""
Fits real log-log price-elasticity estimates from data/csv/scanner_data.csv
(UCI Online Retail II) and writes the artifacts src/api.py loads at startup:

  - data/processed/elasticity_results.json  (overall + by_category + excluded)
  - data/processed/products.json            (per-SKU directory for /products)

Methodology
-----------
The UCI dataset has no category field, only a free-text Description, so
categories are assigned with keyword rules (see CATEGORY_RULES) -- a
heuristic, not ground truth. That's disclosed in the output's `methodology`
block and in /methodology.

Elasticity is estimated with a within (fixed-effects) log-log regression:
for each SKU, transactions are aggregated to weekly (quantity, quantity-
weighted average price), then both log(quantity) and log(price) are
demeaned within SKU. This removes each product's baseline popularity/price
level so the pooled slope reflects how *changes* in a SKU's own price
relate to changes in its own quantity, not just "expensive SKUs sell less"
cross-sectional variation. It's still descriptive/observational, not causal
-- price isn't randomly assigned here -- which is why every API response
carries that caveat.

Run: python -m src.build_elasticity_model
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "csv" / "scanner_data.csv"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

NON_PRODUCT_CODES = {
    "POST", "DOT", "M", "C2", "D", "S", "B", "BANK CHARGES", "ADJUST",
    "ADJUST2", "AMAZONFEE", "CRUK", "TEST001", "PADS",
}

JUNK_DESCRIPTION_RE = re.compile(
    r"\b(ebay|update|amazon|damag|fault|missing|crushed|thrown away|"
    r"wrong code|lost|check\??|sold as set|smashed|\?\?|adjustment|"
    r"barcode|mixed up|found|showroom|sample|display|manual)\b",
    re.IGNORECASE,
)

# Checked in order; first match wins. Heuristic keyword categorization --
# the UCI dataset ships no official category field.
CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("Christmas & Seasonal", re.compile(r"CHRISTMAS|XMAS|ADVENT|EASTER|HALLOWE'?EN|VALENTINE", re.I)),
    ("Home Decor & Lighting", re.compile(r"LIGHT|LANTERN|CANDLE|T-?LIGHT|ORNAMENT|HANGING|DECORATION|MIRROR|\bCLOCK\b|FRAME", re.I)),
    ("Kitchen & Dining", re.compile(r"CAKE|\bMUG\b|PLATE|\bBOWL\b|\bJAR\b|\bTIN\b|TEAPOT|CUTLERY|KITCHEN|LUNCH BAG|BAKING|\bSPOON\b|\bFORK\b|\bKNIFE\b|APRON", re.I)),
    ("Stationery & Cards", re.compile(r"\bCARD\b|\bPAPER\b|\bPEN\b|PENCIL|NOTEBOOK|ENVELOPE|STICKER|GIFT ?WRAP|RIBBON|\bTAPE\b", re.I)),
    ("Toys & Games", re.compile(r"\bTOY\b|\bGAME\b|PUZZLE|\bDOLL\b|TEDDY|BALLOON", re.I)),
    ("Jewelry & Accessories", re.compile(r"NECKLACE|BRACELET|\bRING\b|EARRING|BROOCH|HAIR ?CLIP|HAIR ?BAND", re.I)),
    ("Bath & Body", re.compile(r"\bSOAP\b|\bTOWEL\b|\bBATH\b|SPONGE", re.I)),
    ("Garden & Outdoor", re.compile(r"GARDEN|PLANT POT|OUTDOOR|WATERING", re.I)),
    ("Textiles & Bedding", re.compile(r"CUSHION|BLANKET|\bTHROW\b|CURTAIN|DOORMAT|\bRUG\b", re.I)),
    ("Signs & Wall Art", re.compile(r"\bSIGN\b|WALL ART|PLAQUE|POSTER", re.I)),
    ("Bags & Storage", re.compile(r"\bBAG\b|BASKET|\bBOX\b|STORAGE|POUCH", re.I)),
]

MIN_OBS_PER_CATEGORY = 500  # SKU-weeks, after fixed-effects transform
MIN_SKUS_PER_CATEGORY = 15


def categorize(description: str) -> str:
    if not isinstance(description, str):
        return "Other/Uncategorized"
    for name, pattern in CATEGORY_RULES:
        if pattern.search(description):
            return name
    return "Other/Uncategorized"


def load_clean() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["InvoiceDate"])
    df = df[~df["Invoice"].astype(str).str.startswith("C")]  # cancellations
    df = df[~df["StockCode"].astype(str).str.upper().isin(NON_PRODUCT_CODES)]
    df = df[~df["StockCode"].astype(str).str.startswith("gift_", na=False)]
    df = df[df["Quantity"] > 0]
    df = df[(df["Price"] > 0.01) & (df["Price"] < 500)]
    df = df.dropna(subset=["Description"])
    df = df[~df["Description"].str.match(JUNK_DESCRIPTION_RE)]
    df["Category"] = df["Description"].map(categorize)
    return df


def weekly_sku_panel(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Week"] = df["InvoiceDate"].dt.to_period("W").dt.start_time
    grouped = df.groupby(["StockCode", "Category", "Week"], observed=True).apply(
        lambda g: pd.Series({
            "qty": g["Quantity"].sum(),
            "price": np.average(g["Price"], weights=g["Quantity"]),
        }),
        include_groups=False,
    ).reset_index()
    return grouped[(grouped["qty"] > 0) & (grouped["price"] > 0)]


def within_sku_regression(panel: pd.DataFrame) -> dict | None:
    """Log-log fixed-effects (within-SKU demeaned) OLS, single regressor,
    no intercept needed post-demeaning. Requires >=2 distinct weeks and
    price variation within at least some SKUs to identify beta."""
    p = panel.copy()
    p["log_q"] = np.log(p["qty"])
    p["log_p"] = np.log(p["price"])

    sku_counts = p.groupby("StockCode")["log_p"].transform("count")
    p = p[sku_counts >= 2]
    if p.empty:
        return None

    p["log_q_dm"] = p["log_q"] - p.groupby("StockCode")["log_q"].transform("mean")
    p["log_p_dm"] = p["log_p"] - p.groupby("StockCode")["log_p"].transform("mean")

    # Drop SKUs with zero within-SKU price variance -- they can't identify beta.
    price_var = p.groupby("StockCode")["log_p_dm"].transform(lambda s: s.abs().sum())
    p = p[price_var > 1e-9]
    if len(p) < 30:
        return None

    x = p["log_p_dm"].to_numpy()
    y = p["log_q_dm"].to_numpy()
    n = len(x)
    n_skus = p["StockCode"].nunique()

    sxx = float(np.dot(x, x))
    if sxx < 1e-12:
        return None
    beta = float(np.dot(x, y) / sxx)
    resid = y - beta * x
    # k=1 slope param; SKU fixed effects already removed by demeaning, so
    # dof correction uses n - n_skus - 1 (SKU means + the slope).
    dof = max(n - n_skus - 1, 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    se = float(np.sqrt(sigma2 / sxx))
    ci_low, ci_high = beta - 1.96 * se, beta + 1.96 * se

    ss_tot = float(np.dot(y, y))
    r_squared = 1 - float(np.dot(resid, resid)) / ss_tot if ss_tot > 1e-12 else 0.0

    pct_change = round(((1.10 ** beta) - 1) * 100, 1)
    interpretation = (
        "elastic (quantity responds more than proportionally to price)"
        if beta <= -1 else
        "inelastic (quantity responds less than proportionally to price)"
        if beta < 0 else
        "positive association (likely confounded -- not a real demand response)"
    )

    return dict(
        elasticity=round(beta, 3),
        std_error=round(se, 3),
        ci_low=round(ci_low, 3),
        ci_high=round(ci_high, 3),
        r_squared=round(r_squared, 3),
        n_observations=n,
        n_skus=n_skus,
        interpretation=interpretation,
        pct_quantity_change_for_10pct_price_increase=pct_change,
    )


def build_products_directory(df: pd.DataFrame) -> list[dict]:
    agg = df.groupby("StockCode").agg(
        product_name=("Description", lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0]),
        category=("Category", lambda s: s.mode().iat[0] if not s.mode().empty else s.iloc[0]),
        typical_price=("Price", "median"),
    ).reset_index().rename(columns={"StockCode": "product_id"})
    agg["currency"] = "GBP"
    agg["typical_price"] = agg["typical_price"].round(2)
    return agg.to_dict(orient="records")


def main() -> None:
    print(f"Loading {CSV_PATH} ...")
    df = load_clean()
    print(f"  {len(df):,} clean transaction rows after filtering")

    panel = weekly_sku_panel(df)
    print(f"  {len(panel):,} SKU-week observations across {panel['StockCode'].nunique():,} SKUs")

    overall = within_sku_regression(panel)
    if overall is None:
        raise SystemExit("Overall regression failed to identify beta -- insufficient price variation.")

    by_category = []
    excluded_categories = []
    for category, group in panel.groupby("Category", observed=True):
        n_skus = group["StockCode"].nunique()
        if category == "Other/Uncategorized":
            excluded_categories.append({
                "category": category,
                "reason": "catch-all bucket for descriptions that matched none of the keyword "
                          "rules -- too heterogeneous to report as a single category",
            })
            continue
        if len(group) < MIN_OBS_PER_CATEGORY or n_skus < MIN_SKUS_PER_CATEGORY:
            excluded_categories.append({
                "category": category,
                "reason": f"insufficient data ({len(group)} obs across {n_skus} SKUs; "
                          f"need >={MIN_OBS_PER_CATEGORY} obs and >={MIN_SKUS_PER_CATEGORY} SKUs)",
            })
            continue
        result = within_sku_regression(group)
        if result is None:
            excluded_categories.append({
                "category": category,
                "reason": "regression could not identify beta (no within-SKU price variation)",
            })
            continue
        result["category"] = category
        by_category.append(result)

    by_category.sort(key=lambda r: r["elasticity"])

    results = {
        "overall": overall,
        "by_category": by_category,
        "excluded_categories": excluded_categories,
        "methodology": {
            "method": "within-SKU (fixed-effects) log-log panel regression, weekly aggregation",
            "source_dataset": "UCI Online Retail II (archive.ics.uci.edu/dataset/502)",
            "category_assignment": "keyword rules on free-text Description (dataset has no official category field) -- see CATEGORY_RULES in src/build_elasticity_model.py",
            "cleaning": "dropped cancelled invoices (Invoice starting 'C'), non-product StockCodes (postage/fees/adjustments/gift vouchers), Quantity<=0, Price outside (0.01, 500), and junk/damage-note Descriptions",
            "exclusion_thresholds": f">= {MIN_OBS_PER_CATEGORY} SKU-week observations and >= {MIN_SKUS_PER_CATEGORY} distinct SKUs required to report a category",
            "note": "Descriptive association from observational data, not a causal effect -- price is not randomly assigned in the underlying dataset.",
        },
    }

    (OUT_DIR / "elasticity_results.json").write_text(json.dumps(results, indent=2))
    print(f"Wrote {OUT_DIR / 'elasticity_results.json'} "
          f"({len(by_category)} reported categories, {len(excluded_categories)} excluded)")

    products = build_products_directory(df)
    (OUT_DIR / "products.json").write_text(json.dumps(products, indent=2))
    print(f"Wrote {OUT_DIR / 'products.json'} ({len(products)} SKUs)")


if __name__ == "__main__":
    main()
