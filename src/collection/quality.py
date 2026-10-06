"""
Validation, de-duplication and enrichment, as pandas transforms over a frame of
`Observation` rows. Thresholds are the ones in the collection plan.
"""

from __future__ import annotations

import pandas as pd

PRICE_MIN_USD, PRICE_MAX_USD = 0.10, 100_000.0
OUTLIER_MULTIPLE = 100
MAX_AGE_DAYS = 730
NEAR_DUP_TOLERANCE = 0.05
MIN_QUALITY = 0.80

# Months a category's demand peaks in, per the plan's examples. Anything not
# listed is never tagged peak rather than guessed.
PEAK_MONTHS = {"electronics": {10, 11, 12}, "fashion": {11, 12}}

EXACT_KEY = ["country", "merchant", "product_sku", "date", "channel"]


def add_usd_price(df: pd.DataFrame, fx: dict[str, float]) -> pd.DataFrame:
    """Fill price_usd from price_local where it is missing. `fx` is local
    currency units per USD; a currency not in it leaves price_usd empty (and
    the row fails the price rule below) instead of assuming a rate."""
    df = df.copy()
    rate = df["local_currency"].map(fx)
    df["exchange_rate_usd"] = rate
    derived = df["price_local"] / rate
    df["price_usd"] = df["price_usd"].astype(float).fillna(derived)
    return df


def validate(df: pd.DataFrame, today: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split into (kept, rejected); rejected gets a `reject_reason`."""
    d = pd.to_datetime(df["date"])
    reasons = pd.Series("", index=df.index)
    bad_price = df["price_usd"].isna() | ~df["price_usd"].between(PRICE_MIN_USD, PRICE_MAX_USD)
    bad_date = (d > today) | (d < today - pd.Timedelta(days=MAX_AGE_DAYS))
    bad_geo = df["region"].isna() | (df["region"].astype(str).str.strip() == "")
    for mask, why in ((bad_price, "price_out_of_range"), (bad_date, "date_out_of_range"),
                      (bad_geo, "no_region")):
        reasons = reasons.where(~mask | (reasons != ""), why)
    rejected = df[reasons != ""].assign(reject_reason=reasons[reasons != ""])
    return df[reasons == ""], rejected


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Drop exact duplicates (first wins) and flag near-duplicates: the same
    merchant, category, date and channel with prices within 5% of each other
    and different SKUs. Those are flagged, not dropped; the plan routes the
    first 100 to manual review."""
    df = df.drop_duplicates(EXACT_KEY, keep="first").copy()
    grp = ["country", "merchant", "category", "date", "channel"]
    df["possible_duplicate"] = False
    for _, g in df.groupby(grp, dropna=False):
        if len(g) < 2:
            continue
        p = g["price_usd"].to_numpy()
        for i, idx in enumerate(g.index):
            others = [x for j, x in enumerate(p) if j != i]
            if any(abs(x - p[i]) <= NEAR_DUP_TOLERANCE * p[i] for x in others):
                df.at[idx, "possible_duplicate"] = True
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Quantity outliers: more than 100x the category's median.
    med = df.groupby("category", dropna=False)["units_sold"].transform("median")
    df["quantity_outlier"] = df["units_sold"] > OUTLIER_MULTIPLE * med

    # Competition intensity, 0-10: the effective number of competitors
    # (1 / Herfindahl of unit shares) among a market's merchants, capped at 5
    # (the plan's "top 5") and rescaled. One merchant -> 2; five or more
    # evenly matched -> 10. A market with no volume data scores on count alone.
    def intensity(g: pd.DataFrame) -> float:
        v = g.groupby("merchant")["units_sold"].sum(min_count=1)
        if v.notna().sum() == 0 or v.sum() == 0:
            n = g["merchant"].nunique()
        else:
            s = v.fillna(0) / v.sum()
            n = 1 / float((s ** 2).sum())
        return round(10 * min(n, 5) / 5, 1)

    # Group on a filled copy: NaN never equals itself, so a null category
    # would otherwise miss its own score on lookup.
    market = df["country"] + "|" + df["region"] + "|" + df["category"].fillna("")
    scores = {k: intensity(g) for k, g in df.groupby(market)}
    df["competition_intensity_local"] = market.map(scores)

    month = pd.to_datetime(df["date"]).dt.month
    peaks = df["category"].str.lower().map(PEAK_MONTHS)
    df["seasonality_peak"] = [bool(p) and m in p for p, m in zip(peaks.where(peaks.notna(), None), month)]

    score = pd.Series(1.0, index=df.index)
    score -= 0.15 * df["units_sold"].isna()
    score -= 0.10 * df["category"].isna()
    score -= 0.05 * df["price_local"].isna()
    score -= 0.10 * df["possible_duplicate"]
    score -= 0.20 * df["quantity_outlier"]
    df["data_quality_score"] = score.clip(lower=0).round(2)
    return df
