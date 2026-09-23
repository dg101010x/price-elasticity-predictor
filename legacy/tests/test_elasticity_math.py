"""
Pins the scenario arithmetic against values worked out by hand.

src/web/app.js carries a JavaScript mirror of this module so the slider can
recompute without a round-trip; tests/test_frontend.py asserts the browser
produces the same numbers these tests pin, so the two can't drift apart.
"""

import math

import pytest

from src.elasticity_math import (
    REVENUE_BREAKEVEN_ELASTICITY,
    build_scenario,
    evidence_summary,
    profit_ratio,
    quantity_ratio,
    revenue_advice,
    revenue_ratio,
)


# ---------------------------------------------------------------- ratios ----

def test_quantity_ratio_matches_closed_form():
    # 1.1 ** -1.902 worked out independently: exp(-1.902 * ln 1.1)
    expected = math.exp(-1.902 * math.log(1.1))
    assert quantity_ratio(-1.902, 1.10) == pytest.approx(expected)
    assert quantity_ratio(-1.902, 1.10) == pytest.approx(0.8342018, abs=1e-6)


def test_revenue_ratio_is_price_times_quantity():
    for elasticity in (-2.4, -1.902, -1.0, -0.5):
        for multiplier in (0.6, 0.9, 1.0, 1.1, 1.4):
            assert revenue_ratio(elasticity, multiplier) == pytest.approx(
                multiplier * quantity_ratio(elasticity, multiplier)
            )


def test_revenue_is_flat_exactly_at_the_breakeven_elasticity():
    for multiplier in (0.6, 0.8, 1.0, 1.25, 1.5):
        assert revenue_ratio(REVENUE_BREAKEVEN_ELASTICITY, multiplier) == pytest.approx(1.0)


def test_revenue_moves_the_expected_way_either_side_of_breakeven():
    # More elastic than -1: raising the price loses revenue, cutting it gains.
    assert revenue_ratio(-1.9, 1.10) < 1.0
    assert revenue_ratio(-1.9, 0.90) > 1.0
    # Less elastic than -1: the other way round.
    assert revenue_ratio(-0.5, 1.10) > 1.0
    assert revenue_ratio(-0.5, 0.90) < 1.0


def test_profit_ratio_rejects_selling_at_or_below_cost():
    with pytest.raises(ValueError):
        profit_ratio(-1.9, 1.1, price=5.0, unit_cost=5.0)
    with pytest.raises(ValueError):
        profit_ratio(-1.9, 1.1, price=5.0, unit_cost=6.0)


# -------------------------------------------------------------- scenarios ----

def test_ten_percent_rise_matches_the_precomputed_headline():
    """The dataset's own overall figure is -16.6% units for +10% price."""
    s = build_scenario(elasticity=-1.902, pct_price_change=10, price=10.0)
    assert s.pct_quantity_change == pytest.approx(-16.58, abs=0.01)
    assert s.pct_revenue_change == pytest.approx(-8.24, abs=0.01)
    assert s.new_price == pytest.approx(11.0)
    assert s.direction == "revenue down"


def test_price_cut_grows_revenue_for_an_elastic_product():
    s = build_scenario(elasticity=-1.902, pct_price_change=-10, price=10.0)
    assert s.pct_quantity_change > 0
    assert s.pct_revenue_change > 0
    assert s.new_price == pytest.approx(9.0)
    assert s.direction == "revenue up"


def test_zero_change_is_a_no_op():
    s = build_scenario(elasticity=-1.902, pct_price_change=0, price=7.5)
    assert s.pct_quantity_change == 0
    assert s.pct_revenue_change == 0
    assert s.new_price == pytest.approx(7.5)
    assert s.direction == "revenue roughly flat"


def test_confidence_interval_maps_onto_a_revenue_range():
    s = build_scenario(elasticity=-1.902, pct_price_change=10, price=10.0,
                       ci_low=-1.916, ci_high=-1.887)
    assert s.pct_revenue_change_low <= s.pct_revenue_change <= s.pct_revenue_change_high
    assert s.pct_revenue_change_low == pytest.approx(-8.36, abs=0.02)
    assert s.pct_revenue_change_high == pytest.approx(-8.11, abs=0.02)


def test_revenue_range_stays_ordered_when_the_price_is_cut():
    """min/max, not endpoint order: which CI end is 'better' flips with the sign."""
    s = build_scenario(elasticity=-1.902, pct_price_change=-20, price=10.0,
                       ci_low=-2.5, ci_high=-1.2)
    assert s.pct_revenue_change_low < s.pct_revenue_change_high


def test_profit_can_move_opposite_to_revenue():
    """The case the UI exists to warn about: a discount that grows revenue
    while shrinking the money actually kept."""
    s = build_scenario(elasticity=-1.902, pct_price_change=-20, price=10.0, unit_cost=6.0)
    assert s.pct_revenue_change > 0
    assert s.pct_profit_change < 0


def test_profit_is_omitted_without_a_usable_cost():
    assert build_scenario(-1.9, 10, price=10.0).pct_profit_change is None
    assert build_scenario(-1.9, 10, price=10.0, unit_cost=10.0).pct_profit_change is None
    assert build_scenario(-1.9, 10, unit_cost=4.0).pct_profit_change is None


def test_scenario_without_a_price_still_answers_in_percentages():
    s = build_scenario(elasticity=-1.5, pct_price_change=25)
    assert s.price is None and s.new_price is None
    assert s.pct_quantity_change < 0


def test_a_total_price_cut_is_rejected():
    with pytest.raises(ValueError):
        build_scenario(elasticity=-1.9, pct_price_change=-100)


# ----------------------------------------------------------------- advice ----

def test_elastic_product_is_told_to_discount():
    advice = revenue_advice(-1.902, -1.916, -1.887)
    assert advice["certain"] is True
    assert advice["raising_price"] == "loses revenue"
    assert "Cutting the price" in advice["headline"]


def test_inelastic_product_is_told_to_raise():
    advice = revenue_advice(-0.5, -0.6, -0.4)
    assert advice["certain"] is True
    assert advice["raising_price"] == "gains revenue"
    assert "Raising the price" in advice["headline"]


def test_interval_straddling_breakeven_refuses_to_pick_a_side():
    """The honest answer when the data can't tell you which way revenue goes."""
    advice = revenue_advice(-1.05, -1.4, -0.7)
    assert advice["certain"] is False
    assert advice["raising_price"] == "unclear"
    assert "Too close to call" in advice["headline"]


def test_advice_is_uncertain_even_when_the_point_estimate_looks_decisive():
    advice = revenue_advice(-1.9, -2.9, -0.9)
    assert advice["certain"] is False


# --------------------------------------------------------------- evidence ----

def _estimate(**kw):
    base = {
        "elasticity": -1.902, "ci_low": -1.916, "ci_high": -1.887,
        "r_squared": 0.253, "n_observations": 194489, "n_skus": 4334,
    }
    base.update(kw)
    return base


def test_evidence_reads_the_real_overall_estimate_as_strong_and_precise():
    ev = evidence_summary(_estimate())
    assert ev["precision"] == "very precise"
    assert ev["sample"] == "very strong"
    assert ev["fit"] == "a moderate amount"
    assert "194,489" in ev["sample_detail"]


def test_evidence_flags_a_thin_wide_estimate():
    ev = evidence_summary(_estimate(ci_low=-3.0, ci_high=-0.8, n_observations=400, r_squared=0.02))
    assert ev["precision"] == "very rough"
    assert ev["sample"] == "thin"
    assert ev["fit"] == "very little"


def test_evidence_bands_move_monotonically_with_sample_size():
    order = ["thin", "moderate", "strong", "very strong"]
    seen = [evidence_summary(_estimate(n_observations=n))["sample"]
            for n in (500, 5_000, 50_000, 500_000)]
    assert seen == order
