"""
Canonical price-scenario math, shared by the API (/scenario) and mirrored in
src/web/app.js so the slider can recompute without a round-trip.

tests/test_elasticity_math.py pins these values, and tests/test_frontend.py
cross-checks the JS mirror against the same expectations, so the two
implementations can't silently drift.

Model
-----
Constant-elasticity demand, which is what a log-log regression fits:

    Q(P) = A * P^e

For a price multiplier m (m = 1.10 for "+10%"):

    quantity ratio = m^e
    revenue  ratio = m^(1+e)        since revenue = P*Q = A * P^(1+e)
    profit   ratio = ((P*m - C) / (P - C)) * m^e     when a unit cost C is given

The revenue line is the decision-relevant one: revenue is flat in price exactly
at e = -1, rises with price when e > -1, and falls with price when e < -1. That
threshold is the whole reason a business user cares about elasticity, so it is
named REVENUE_BREAKEVEN_ELASTICITY here and drawn as a labelled threshold in
the UI rather than left for the reader to infer.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

# Revenue is unchanged by a price move exactly at this elasticity. More negative
# => raising price loses revenue. Less negative => raising price gains revenue.
REVENUE_BREAKEVEN_ELASTICITY = -1.0

# Bands for turning a confidence-interval width into plain language. Expressed
# as the CI half-width as a fraction of the estimate's own magnitude.
_PRECISION_BANDS = (
    (0.05, "very precise", "The range around this estimate is tight."),
    (0.15, "precise", "The range around this estimate is fairly tight."),
    (0.35, "rough", "The range around this estimate is wide — treat the headline number as a ballpark."),
)
_PRECISION_FALLBACK = (
    "very rough",
    "The range around this estimate is very wide — it barely narrows down the answer.",
)

# Bands for n_observations (SKU-weeks behind the fit).
_SAMPLE_BANDS = (
    (1_000, "thin"),
    (10_000, "moderate"),
    (100_000, "strong"),
)
_SAMPLE_FALLBACK = "very strong"

# Bands for R-squared. Retail demand is noisy, so these are calibrated to what
# is normal for scanner data, not to a textbook 0.7-is-good rule of thumb.
_FIT_BANDS = (
    (0.05, "very little"),
    (0.15, "a little"),
    (0.35, "a moderate amount"),
)
_FIT_FALLBACK = "a lot"


@dataclass(frozen=True)
class Scenario:
    """One 'what if I move the price by X%' answer."""

    pct_price_change: float
    price: Optional[float]
    new_price: Optional[float]
    pct_quantity_change: float
    pct_revenue_change: float
    pct_revenue_change_low: Optional[float]
    pct_revenue_change_high: Optional[float]
    pct_profit_change: Optional[float]
    unit_cost: Optional[float]
    direction: str  # "revenue up" | "revenue down" | "revenue roughly flat"

    def to_dict(self) -> dict:
        return asdict(self)


def _pct(ratio: float) -> float:
    return round((ratio - 1.0) * 100.0, 2)


def quantity_ratio(elasticity: float, multiplier: float) -> float:
    """Units sold after the price move, as a ratio of units sold now."""
    return multiplier ** elasticity


def revenue_ratio(elasticity: float, multiplier: float) -> float:
    """Revenue after the price move, as a ratio of revenue now."""
    return multiplier ** (1.0 + elasticity)


def profit_ratio(elasticity: float, multiplier: float, price: float, unit_cost: float) -> float:
    """Gross profit after the price move, as a ratio of gross profit now.

    Undefined when the product is sold at or below cost, since there is no
    positive baseline profit to compare against.
    """
    margin_now = price - unit_cost
    if margin_now <= 0:
        raise ValueError("unit_cost must be below price")
    margin_after = price * multiplier - unit_cost
    return (margin_after / margin_now) * quantity_ratio(elasticity, multiplier)


def build_scenario(
    elasticity: float,
    pct_price_change: float,
    price: Optional[float] = None,
    unit_cost: Optional[float] = None,
    ci_low: Optional[float] = None,
    ci_high: Optional[float] = None,
) -> Scenario:
    """Full answer to 'what happens if I move this price by pct_price_change%'."""
    if pct_price_change <= -100:
        raise ValueError("pct_price_change must be greater than -100")

    multiplier = 1.0 + pct_price_change / 100.0

    pct_qty = _pct(quantity_ratio(elasticity, multiplier))
    pct_rev = _pct(revenue_ratio(elasticity, multiplier))

    # The CI on elasticity maps straight onto a CI on the revenue outcome. Which
    # endpoint gives the better revenue outcome flips with the sign of the price
    # move, so take the min/max rather than assuming an order.
    pct_rev_low = pct_rev_high = None
    if ci_low is not None and ci_high is not None:
        ends = [_pct(revenue_ratio(ci_low, multiplier)), _pct(revenue_ratio(ci_high, multiplier))]
        pct_rev_low, pct_rev_high = min(ends), max(ends)

    pct_profit = None
    if price is not None and unit_cost is not None and price > unit_cost:
        pct_profit = _pct(profit_ratio(elasticity, multiplier, price, unit_cost))

    if abs(pct_rev) < 0.5:
        direction = "revenue roughly flat"
    elif pct_rev > 0:
        direction = "revenue up"
    else:
        direction = "revenue down"

    return Scenario(
        pct_price_change=round(pct_price_change, 4),
        price=price,
        new_price=round(price * multiplier, 4) if price is not None else None,
        pct_quantity_change=pct_qty,
        pct_revenue_change=pct_rev,
        pct_revenue_change_low=pct_rev_low,
        pct_revenue_change_high=pct_rev_high,
        pct_profit_change=pct_profit,
        unit_cost=unit_cost,
        direction=direction,
    )


def _band(value: float, bands, fallback):
    for threshold, *rest in bands:
        if value < threshold:
            return rest[0] if len(rest) == 1 else tuple(rest)
    return fallback


def revenue_advice(elasticity: float, ci_low: float, ci_high: float) -> dict:
    """The headline pricing verdict, in the terms a price-setter thinks in.

    `certain` is False when the confidence interval straddles the -1 revenue
    threshold: the estimate then genuinely does not tell you which way revenue
    moves, and the UI has to say so instead of showing a confident arrow.
    """
    breakeven = REVENUE_BREAKEVEN_ELASTICITY
    straddles = ci_low < breakeven < ci_high

    if straddles:
        return {
            "raising_price": "unclear",
            "certain": False,
            "headline": "Too close to call which way revenue moves.",
            "detail": (
                "The likely range for this estimate sits on both sides of the break-even "
                "point, so the data can't say whether a price rise would grow or shrink "
                "revenue here."
            ),
        }

    if elasticity < breakeven:
        return {
            "raising_price": "loses revenue",
            "certain": True,
            "headline": "Cutting the price tends to grow revenue here.",
            "detail": (
                "Shoppers react strongly enough that a price rise loses more in units "
                "than it gains per unit. Discounts tend to pay for themselves in revenue "
                "terms — though not necessarily in profit terms."
            ),
        }

    return {
        "raising_price": "gains revenue",
        "certain": True,
        "headline": "Raising the price tends to grow revenue here.",
        "detail": (
            "Shoppers barely change what they buy when the price moves, so a price rise "
            "keeps more revenue per unit than it loses in units. Discounting here tends "
            "to give away margin without buying much extra volume."
        ),
    }


def evidence_summary(estimate: dict) -> dict:
    """Turn std errors, R-squared and sample counts into plain-language quality flags."""
    elasticity = estimate["elasticity"]
    ci_low, ci_high = estimate["ci_low"], estimate["ci_high"]

    half_width = (ci_high - ci_low) / 2.0
    relative = half_width / abs(elasticity) if elasticity else float("inf")
    precision_label, precision_detail = _band(relative, _PRECISION_BANDS, _PRECISION_FALLBACK)

    n_obs = estimate["n_observations"]
    sample_label = _band(n_obs, _SAMPLE_BANDS, _SAMPLE_FALLBACK)

    r_squared = estimate["r_squared"]
    fit_label = _band(r_squared, _FIT_BANDS, _FIT_FALLBACK)

    return {
        "precision": precision_label,
        "precision_detail": precision_detail,
        "ci_half_width": round(half_width, 4),
        "sample": sample_label,
        "n_observations": n_obs,
        "n_skus": estimate.get("n_skus"),
        "fit": fit_label,
        "r_squared": r_squared,
        "fit_detail": (
            f"Price movements explain {fit_label} of the week-to-week swing in units sold. "
            "The rest is season, promotion, stock and everything else — which is normal "
            "for retail data, not a sign the estimate is broken."
        ),
        "sample_detail": (
            f"Built from {n_obs:,} weekly price-and-units observations"
            + (f" across {estimate['n_skus']:,} products." if estimate.get("n_skus") else ".")
        ),
    }
