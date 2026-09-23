"""
The shared estimator in src/stats_engine.py against the implementation it
was extracted from.

Every per-account number rests on the claim that it is fitted "with the
same rigor as the public benchmarks". That claim is only true if the code
is the same, so the pre-extraction versions of weekly_sku_panel and
within_sku_regression are frozen below, verbatim from
src/build_elasticity_model.py as of 2.1.0, and the new module is required
to reproduce them on panels built to hit every branch: several rows per
product-week, products with one week, products whose price never moves,
categories either side of the reporting bar, and a catch-all bucket.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.stats_engine import (
    MIN_OBS_PER_CATEGORY,
    MIN_PRODUCTS_PER_CATEGORY,
    fit_catalogue,
    run_record,
    weekly_panel,
    within_product_regression,
)


# ----------------------------------------------- the frozen 2.1.0 oracle ---

def _oracle_weekly_sku_panel(df: pd.DataFrame) -> pd.DataFrame:
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


def _oracle_within_sku_regression(panel: pd.DataFrame) -> dict | None:
    p = panel.copy()
    p["log_q"] = np.log(p["qty"])
    p["log_p"] = np.log(p["price"])

    sku_counts = p.groupby("StockCode")["log_p"].transform("count")
    p = p[sku_counts >= 2]
    if p.empty:
        return None

    p["log_q_dm"] = p["log_q"] - p.groupby("StockCode")["log_q"].transform("mean")
    p["log_p_dm"] = p["log_p"] - p.groupby("StockCode")["log_p"].transform("mean")

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
        elasticity=round(beta, 3), std_error=round(se, 3),
        ci_low=round(ci_low, 3), ci_high=round(ci_high, 3),
        r_squared=round(r_squared, 3), n_observations=n, n_skus=n_skus,
        interpretation=interpretation,
        pct_quantity_change_for_10pct_price_increase=pct_change,
    )


def _oracle_fit(panel: pd.DataFrame) -> dict:
    """The 2.1.0 main() loop over categories."""
    overall = _oracle_within_sku_regression(panel)
    by_category, excluded = [], []
    for category, group in panel.groupby("Category", observed=True):
        n_skus = group["StockCode"].nunique()
        if category == "Other/Uncategorized":
            excluded.append({"category": category, "reason": "catch-all"})
            continue
        if len(group) < 500 or n_skus < 15:
            excluded.append({
                "category": category,
                "reason": f"insufficient data ({len(group)} obs across {n_skus} SKUs; "
                          f"need >=500 obs and >=15 SKUs)",
            })
            continue
        result = _oracle_within_sku_regression(group)
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


# --------------------------------------------------------------- fixtures ---

def _transactions(seed: int, categories: dict[str, tuple[int, float]], weeks: int = 40) -> pd.DataFrame:
    """Transaction rows in the UCI column layout.

    `categories` maps name -> (number of products, true elasticity). Each
    product gets its own baseline popularity and price level, a few
    transactions per week at slightly different prices, and some products
    are deliberately degenerate (one week only, or a fixed price).
    """
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2024-01-03 10:00")
    for cat, (n_products, elasticity) in categories.items():
        for j in range(n_products):
            code = f"{cat[:3].upper()}{j:03d}"
            base_price = float(np.exp(rng.normal(1.5, 0.6)))
            base_units = float(np.exp(rng.normal(3.0, 0.8)))
            fixed_price = j % 11 == 5
            n_weeks = 1 if j % 13 == 7 else weeks
            for w in range(n_weeks):
                weekly_price = base_price * (1.0 if fixed_price else float(np.exp(rng.normal(0, 0.15))))
                for _ in range(int(rng.integers(1, 4))):
                    price = weekly_price * (1.0 if fixed_price else float(np.exp(rng.normal(0, 0.03))))
                    mu = base_units * (price / base_price) ** elasticity / 2.0
                    qty = int(max(1, rng.poisson(max(mu, 0.5))))
                    when = start + pd.Timedelta(days=7 * w + int(rng.integers(0, 7)),
                                                hours=int(rng.integers(0, 9)))
                    rows.append((code, cat, when, qty, round(price, 2)))
    return pd.DataFrame(rows, columns=["StockCode", "Category", "InvoiceDate", "Quantity", "Price"])


def _canonical(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        "StockCode": "product", "Category": "category",
        "InvoiceDate": "date", "Quantity": "quantity", "Price": "price",
    })


CASES = {
    "one big category": {"Kitchen": (40, -1.4)},
    "several, some below the bar": {
        "Kitchen": (30, -1.8), "Garden": (18, -0.6), "Toys": (9, -1.1),
        "Other/Uncategorized": (25, -1.0),
    },
    "inelastic": {"Staples": (20, -0.3), "Treats": (20, -2.4)},
}


# ------------------------------------------------------------------ tests ---

@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("case", list(CASES))
def test_weekly_rollup_matches_the_original(case, seed):
    tx = _transactions(seed, CASES[case])
    old = _oracle_weekly_sku_panel(tx).reset_index(drop=True)
    new = weekly_panel(_canonical(tx))

    assert len(new) == len(old)
    assert list(new["product"]) == list(old["StockCode"])
    assert list(new["category"]) == list(old["Category"])
    assert list(new["week"]) == list(old["Week"])
    assert np.array_equal(new["qty"].to_numpy(), old["qty"].to_numpy(dtype=float))
    np.testing.assert_allclose(new["price"].to_numpy(), old["price"].to_numpy(), rtol=1e-12)


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("case", list(CASES))
def test_published_figures_are_identical_to_the_original(case, seed):
    """Every rounded figure that reaches a page or a table row must match."""
    tx = _transactions(seed, CASES[case])
    old = _oracle_fit(_oracle_weekly_sku_panel(tx))
    new = fit_catalogue(weekly_panel(_canonical(tx)),
                        catch_all={"Other/Uncategorized": "catch-all"})
    assert new == old


def test_the_regression_body_is_unchanged_on_an_identical_panel():
    """Same panel in, bit-identical dict out: the port renamed a column and nothing else."""
    tx = _transactions(7, {"Kitchen": (25, -1.2)})
    old_panel = _oracle_weekly_sku_panel(tx)
    new_panel = old_panel.rename(columns={"StockCode": "product", "Category": "category", "Week": "week"})
    assert within_product_regression(new_panel) == _oracle_within_sku_regression(old_panel)


def test_the_estimator_recovers_a_known_elasticity():
    tx = _transactions(11, {"Kitchen": (60, -1.5)}, weeks=60)
    fit = within_product_regression(weekly_panel(_canonical(tx)))
    assert fit["ci_low"] < -1.5 < fit["ci_high"] or abs(fit["elasticity"] + 1.5) < 0.1


def test_categories_below_the_bar_are_excluded_with_a_reason():
    tx = _transactions(3, CASES["several, some below the bar"])
    fit = fit_catalogue(weekly_panel(_canonical(tx)),
                        catch_all={"Other/Uncategorized": "no category"})
    reported = {r["category"] for r in fit["by_category"]}
    excluded = {e["category"]: e["reason"] for e in fit["excluded_categories"]}
    assert "Toys" in excluded and "insufficient data" in excluded["Toys"]
    assert excluded["Other/Uncategorized"] == "no category"
    assert "Kitchen" in reported
    assert reported.isdisjoint(excluded)
    for row in fit["by_category"]:
        assert row["n_observations"] <= 40 * 30
    assert MIN_OBS_PER_CATEGORY == 500 and MIN_PRODUCTS_PER_CATEGORY == 15


def test_catch_all_rows_still_count_towards_the_overall_estimate():
    tx = _transactions(5, CASES["several, some below the bar"])
    panel = weekly_panel(_canonical(tx))
    with_catch_all = fit_catalogue(panel, catch_all={"Other/Uncategorized": "x"})["overall"]
    without = fit_catalogue(panel[panel["category"] != "Other/Uncategorized"])["overall"]
    assert with_catch_all["n_observations"] > without["n_observations"]


def test_too_little_data_returns_no_estimate_rather_than_a_guess():
    tx = _transactions(2, {"Kitchen": (2, -1.0)}, weeks=6)
    assert fit_catalogue(weekly_panel(_canonical(tx)))["overall"] is None


def test_run_record_is_exactly_the_six_field_contract():
    tx = _transactions(4, {"Kitchen": (20, -1.0)})
    fit = fit_catalogue(weekly_panel(_canonical(tx)))
    record = run_record(fit["overall"], None)
    assert set(record) == {"category", "coefficient", "ci_low", "ci_high", "r_squared", "n_observations"}
    assert record["coefficient"] == fit["overall"]["elasticity"]
    assert record["ci_low"] <= record["coefficient"] <= record["ci_high"]
