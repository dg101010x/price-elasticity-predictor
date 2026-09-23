"""
The elasticity estimator, shared by the public build and by per-account runs.

src/build_elasticity_model.py used to carry this code inline. It lives here
now so the number a business gets from its own upload is fitted by the same
lines of code as the public UCI estimate the site has always shown -- not a
re-implementation that could drift from it. The public build imports these
functions; so does src/account/ingest.py. tests/test_stats_engine.py pins
the port against the original implementation.

Method (unchanged)
------------------
Rows are rolled up to one observation per product per week: units summed,
price the quantity-weighted average. log(units) and log(price) are demeaned
within each product, and the pooled slope of one on the other is the
elasticity. Classical standard error with the product means charged to the
degrees of freedom; 95% interval = slope +/- 1.96 SE; R^2 is the within R^2.

A category is only reported once it clears MIN_OBS_PER_CATEGORY weekly
observations across MIN_PRODUCTS_PER_CATEGORY products. A catch-all bucket
(the public build's "Other/Uncategorized", an upload's rows with no category)
is never reported as a category of its own, and the reason is recorded
rather than the bucket being silently dropped.

Only numpy and pandas: this module is imported by the Vercel function, so it
must not pull in anything the deployment doesn't already ship.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Two-sided 95% normal critical value -- the same constant src/panel_fit.py
# uses for the benchmarks, so every interval on the site means the same thing.
Z95 = 1.96

MIN_OBS_PER_CATEGORY = 500  # product-weeks in the category's panel
MIN_PRODUCTS_PER_CATEGORY = 15

# The canonical panel columns. Callers rename their own columns to these.
PANEL_COLUMNS = ("product", "category", "week", "qty", "price")


def weekly_panel(rows: pd.DataFrame) -> pd.DataFrame:
    """Roll transaction- or day-level rows up to one row per product-week.

    `rows` needs columns product, category, date (datetime64), quantity and
    price, already cleaned of non-positive quantities and prices. Weeks are
    pandas' default weekly periods (Monday start), as in the original build.

    Units are summed; price is the quantity-weighted average price, i.e.
    sum(price * quantity) / sum(quantity) -- identical to the original's
    np.average(price, weights=quantity), computed with one grouped sum
    instead of a Python lambda per group (a 5,000-product upload took
    seconds the old way).
    """
    frame = pd.DataFrame({
        "product": rows["product"].to_numpy(),
        "category": rows["category"].to_numpy(),
        "week": rows["date"].dt.to_period("W").dt.start_time.to_numpy(),
        "qty": rows["quantity"].to_numpy(dtype=float),
    })
    frame["revenue"] = frame["qty"] * rows["price"].to_numpy(dtype=float)

    grouped = (
        frame.groupby(["product", "category", "week"], observed=True, sort=True)[["qty", "revenue"]]
        .sum()
        .reset_index()
    )
    grouped["price"] = grouped["revenue"] / grouped["qty"]
    grouped = grouped[(grouped["qty"] > 0) & (grouped["price"] > 0)]
    return grouped[list(PANEL_COLUMNS)].reset_index(drop=True)


def within_product_regression(panel: pd.DataFrame) -> dict | None:
    """Log-log fixed-effects (within-product demeaned) OLS, single regressor,
    no intercept needed post-demeaning. Requires >=2 distinct weeks and
    price variation within at least some products to identify beta.

    This is the original src/build_elasticity_model.py:within_sku_regression,
    moved here unchanged except that the product column is called `product`.
    """
    p = panel.copy()
    p["log_q"] = np.log(p["qty"])
    p["log_p"] = np.log(p["price"])

    sku_counts = p.groupby("product")["log_p"].transform("count")
    p = p[sku_counts >= 2]
    if p.empty:
        return None

    p["log_q_dm"] = p["log_q"] - p.groupby("product")["log_q"].transform("mean")
    p["log_p_dm"] = p["log_p"] - p.groupby("product")["log_p"].transform("mean")

    # Drop products with zero within-product price variance -- they can't identify beta.
    price_var = p.groupby("product")["log_p_dm"].transform(lambda s: s.abs().sum())
    p = p[price_var > 1e-9]
    if len(p) < 30:
        return None

    x = p["log_p_dm"].to_numpy()
    y = p["log_q_dm"].to_numpy()
    n = len(x)
    n_skus = p["product"].nunique()

    sxx = float(np.dot(x, x))
    if sxx < 1e-12:
        return None
    beta = float(np.dot(x, y) / sxx)
    resid = y - beta * x
    # k=1 slope param; product fixed effects already removed by demeaning, so
    # dof correction uses n - n_skus - 1 (product means + the slope).
    dof = max(n - n_skus - 1, 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    se = float(np.sqrt(sigma2 / sxx))
    ci_low, ci_high = beta - Z95 * se, beta + Z95 * se

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


def fit_catalogue(panel: pd.DataFrame, catch_all: dict[str, str] | None = None) -> dict:
    """The overall estimate plus one per category that clears the bar.

    `catch_all` maps bucket names that must never be reported as a category
    (they are a residue, not a group of similar products) to the reason
    shown for excluding them. Their rows still count towards the overall
    estimate, exactly as "Other/Uncategorized" always has.

    Returns {"overall": dict | None, "by_category": [...], "excluded_categories": [...]}.
    `overall` is None when even the whole catalogue can't identify a slope.
    """
    catch_all = catch_all or {}
    overall = within_product_regression(panel)

    by_category: list[dict] = []
    excluded: list[dict] = []
    for category, group in panel.groupby("category", observed=True):
        n_skus = group["product"].nunique()
        if category in catch_all:
            excluded.append({"category": category, "reason": catch_all[category]})
            continue
        if len(group) < MIN_OBS_PER_CATEGORY or n_skus < MIN_PRODUCTS_PER_CATEGORY:
            excluded.append({
                "category": category,
                "reason": f"insufficient data ({len(group)} obs across {n_skus} SKUs; "
                          f"need >={MIN_OBS_PER_CATEGORY} obs and >={MIN_PRODUCTS_PER_CATEGORY} SKUs)",
            })
            continue
        result = within_product_regression(group)
        if result is None:
            excluded.append({
                "category": category,
                "reason": "regression could not identify beta (no within-SKU price variation)",
            })
            continue
        result["category"] = category
        by_category.append(result)

    by_category.sort(key=lambda r: r["elasticity"])
    return {"overall": overall, "by_category": by_category, "excluded_categories": excluded}


def run_record(result: dict, category: str | None) -> dict:
    """The plain per-run JSON object: what elasticity_runs stores, and the
    only thing the insights engine is ever shown.

    `category` is None for the whole-catalogue run.
    """
    return {
        "category": category,
        "coefficient": result["elasticity"],
        "ci_low": result["ci_low"],
        "ci_high": result["ci_high"],
        "r_squared": result["r_squared"],
        "n_observations": int(result["n_observations"]),
    }
