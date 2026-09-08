"""
The estimator, in one place.

`src/build_elasticity_model.py` fits the UK giftware catalogue this product
was originally built on; `src/build_reference_benchmarks.py` fits the twelve
outside markets added later. Both call `within_entity_loglog()` below, so a
benchmark from Broadway and a category from the gift catalogue mean the same
thing and can be shown on the same axis.

Method
------
Observations are grouped into entities (a SKU, a state, a Broadway show).
Within each entity, log(quantity) and log(price) are demeaned, then pooled
and regressed through the origin. Demeaning removes each entity's baseline
popularity and price level, so the slope reflects how a change in an
entity's *own* price relates to a change in its *own* volume -- not the
cross-sectional fact that expensive things sell in smaller numbers.

The slope is the price elasticity of demand. Standard errors use a
degrees-of-freedom correction of n - n_entities - 1, charging one parameter
for each entity mean absorbed by the demeaning plus one for the slope.

Nothing here is causal. Price is not randomly assigned in any of these
datasets, and every caller is expected to say so.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Revenue is flat in price at exactly this elasticity. More negative and a
# price rise loses more in units than it gains per unit.
REVENUE_BREAKEVEN = -1.0

MIN_OBSERVATIONS = 30


def interpret(beta: float) -> str:
    if beta <= REVENUE_BREAKEVEN:
        return "elastic (quantity responds more than proportionally to price)"
    if beta < 0:
        return "inelastic (quantity responds less than proportionally to price)"
    return "positive association (likely confounded — not a real demand response)"


def within_entity_loglog(
    frame: pd.DataFrame,
    entity: str,
    price: str,
    quantity: str,
    weight: str | None = None,
    min_observations: int = MIN_OBSERVATIONS,
) -> dict | None:
    """Fit a within-entity log-log demand slope.

    `weight`, when given, names a column of observation counts: a row that
    summarises 800 purchase occasions should not count the same as one that
    summarises two. Degrees of freedom still use the number of rows, not the
    sum of the weights, which keeps the interval honest about how many
    distinct price points the slope actually rests on.

    Returns None -- rather than a number nobody should trust -- when the data
    can't identify one: fewer than two periods per entity, no within-entity
    price variation, or fewer than `min_observations` rows left after both
    filters.
    """
    cols = [entity, price, quantity] + ([weight] if weight else [])
    p = frame[cols].dropna()
    p = p[(p[price] > 0) & (p[quantity] > 0)]
    if weight:
        p = p[p[weight] > 0]
    if p.empty:
        return None

    p = p.assign(_lq=np.log(p[quantity].astype(float)), _lp=np.log(p[price].astype(float)))
    p = p.assign(_w=p[weight].astype(float) if weight else 1.0)

    # An entity seen once contributes nothing after demeaning.
    counts = p.groupby(entity)["_lp"].transform("count")
    p = p[counts >= 2]
    if p.empty:
        return None

    def _entity_mean(col: str) -> pd.Series:
        if weight is None:
            # groupby.transform is markedly faster than apply, and this path
            # runs over 4,334 SKUs on every model rebuild.
            return p.groupby(entity)[col].transform("mean")
        weighted = p[col] * p["_w"]
        return (
            weighted.groupby(p[entity]).transform("sum")
            / p["_w"].groupby(p[entity]).transform("sum")
        )

    p = p.assign(_lq_dm=p["_lq"] - _entity_mean("_lq"), _lp_dm=p["_lp"] - _entity_mean("_lp"))

    # Entities whose price never moved can't identify a slope.
    spread = p.groupby(entity)["_lp_dm"].transform(lambda s: s.abs().sum())
    p = p[spread > 1e-9]
    if len(p) < min_observations:
        return None

    x = p["_lp_dm"].to_numpy()
    y = p["_lq_dm"].to_numpy()
    w = p["_w"].to_numpy()
    n = len(x)
    n_entities = int(p[entity].nunique())

    sxx = float(np.dot(w * x, x))
    if sxx < 1e-12:
        return None

    beta = float(np.dot(w * x, y) / sxx)
    resid = y - beta * x
    dof = max(n - n_entities - 1, 1)
    sigma2 = float(np.dot(w * resid, resid) / dof)
    se = float(np.sqrt(sigma2 / sxx))

    ss_tot = float(np.dot(w * y, y))
    r_squared = 1 - float(np.dot(w * resid, resid)) / ss_tot if ss_tot > 1e-12 else 0.0

    return {
        "elasticity": round(beta, 3),
        "std_error": round(se, 3),
        "ci_low": round(beta - 1.96 * se, 3),
        "ci_high": round(beta + 1.96 * se, 3),
        "r_squared": round(r_squared, 3),
        "n_observations": n,
        "n_entities": n_entities,
        "interpretation": interpret(beta),
        "pct_quantity_change_for_10pct_price_increase": round(((1.10 ** beta) - 1) * 100, 1),
    }


def pooled_loglog(frame: pd.DataFrame, price: str, quantity: str) -> dict | None:
    """Fit log(quantity) on log(price) for a single series with an intercept.

    For datasets that are one market observed over time -- California
    avocados, 1880s rail freight -- where there is no cross-section to demean
    against. Same slope interpretation, but with none of the protection
    against confounding that the within-entity transform gives you, so
    callers label these differently.
    """
    p = frame[[price, quantity]].dropna()
    p = p[(p[price] > 0) & (p[quantity] > 0)]
    if len(p) < MIN_OBSERVATIONS:
        return None

    x = np.log(p[price].to_numpy(dtype=float))
    y = np.log(p[quantity].to_numpy(dtype=float))
    n = len(x)

    xc = x - x.mean()
    sxx = float(np.dot(xc, xc))
    if sxx < 1e-12:
        return None

    beta = float(np.dot(xc, y - y.mean()) / sxx)
    resid = y - y.mean() - beta * xc
    dof = max(n - 2, 1)
    se = float(np.sqrt(float(np.dot(resid, resid)) / dof / sxx))

    ss_tot = float(np.dot(y - y.mean(), y - y.mean()))
    r_squared = 1 - float(np.dot(resid, resid)) / ss_tot if ss_tot > 1e-12 else 0.0

    return {
        "elasticity": round(beta, 3),
        "std_error": round(se, 3),
        "ci_low": round(beta - 1.96 * se, 3),
        "ci_high": round(beta + 1.96 * se, 3),
        "r_squared": round(r_squared, 3),
        "n_observations": n,
        "n_entities": 1,
        "interpretation": interpret(beta),
        "pct_quantity_change_for_10pct_price_increase": round(((1.10 ** beta) - 1) * 100, 1),
    }


MIN_OCCASIONS_PER_PRICE_POINT = 5


def choice_share_loglog(
    frame: pd.DataFrame,
    choice_column: str,
    brands: dict[str, str],
    min_occasions: int = MIN_OCCASIONS_PER_PRICE_POINT,
) -> dict | None:
    """Fit a price slope from brand-choice scanner panels.

    These datasets record one purchase occasion per row: which brand the
    shopper picked, and the shelf price of *every* competing brand at that
    moment. There is no quantity column to regress, so the quantity analogue
    is the brand's share of the purchases made while it sat at that price.

    Shelf prices in scanner data are discrete -- ketchup moves between eight
    distinct price points, not a continuum -- so the grouping here is the
    observed price itself rather than an arbitrary quantile bucket. For each
    brand and each price it was actually seen at, we take that brand's share
    of purchases, dropping price points with fewer than `min_occasions`
    behind them because a share computed from three shoppers is noise.

    The resulting (brand, price, share) rows go through the same
    within-entity transform as every other estimate, weighted by occasions,
    with the brand as the entity. The slope is again "how a brand's own price
    moves its own volume", so it lands on the same axis as the rest.

    `brands` maps brand label (as it appears in `choice_column`) to that
    brand's price column.
    """
    rows = []
    for label, price_col in brands.items():
        sub = frame[[choice_column, price_col]].dropna()
        sub = sub[sub[price_col] > 0]
        if sub.empty:
            continue
        grouped = sub.groupby(price_col, observed=True).apply(
            lambda g: pd.Series({
                "share": float((g[choice_column] == label).mean()),
                "occasions": float(len(g)),
            }),
            include_groups=False,
        ).reset_index()
        grouped = grouped[(grouped["occasions"] >= min_occasions) & (grouped["share"] > 0)]
        for _, r in grouped.iterrows():
            rows.append({"brand": label, "price": float(r[price_col]),
                         "share": r["share"], "occasions": r["occasions"]})

    if not rows:
        return None
    panel = pd.DataFrame(rows)
    if panel["brand"].nunique() < 2:
        return None

    result = within_entity_loglog(
        panel, entity="brand", price="price", quantity="share",
        weight="occasions", min_observations=12,
    )
    if result is None:
        return None
    result["n_purchase_occasions"] = int(len(frame))
    result["n_price_points"] = int(len(panel))
    return result
