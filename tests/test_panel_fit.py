"""
Known-answer tests for the estimators in src/panel_fit.py.

These are the numbers the benchmark comparison is built on, and they are
hand-rolled rather than borrowed from statsmodels, so each one is checked
against data where the right answer is known by construction: simulate with
a chosen coefficient, fit, and require it back.

The IV test is the one that matters most. A 2SLS implementation that is
subtly wrong still returns plausible-looking numbers -- it just returns the
biased ones -- so the test deliberately builds a dataset where OLS is known
to be wrong and asserts that OLS fails while 2SLS succeeds.
"""

import numpy as np
import pytest

from src.panel_fit import (
    conditional_logit,
    logit_own_price_elasticity,
    ols,
    summarize,
    tsls,
    within,
)


def test_ols_recovers_a_known_slope():
    rng = np.random.default_rng(0)
    x = rng.normal(size=500)
    y = 2.0 - 1.35 * x + rng.normal(scale=0.2, size=500)
    fit = ols(y, x)
    assert fit["beta"][0] == pytest.approx(2.0, abs=0.05)
    assert fit["beta"][1] == pytest.approx(-1.35, abs=0.05)
    assert fit["r_squared"] > 0.9


def test_within_removes_group_means():
    values = np.array([1.0, 3.0, 10.0, 12.0])
    groups = np.array(["a", "a", "b", "b"])
    demeaned, = within([values], [groups])
    assert demeaned == pytest.approx([-1.0, 1.0, -1.0, 1.0])


def test_two_way_within_removes_both_dimensions():
    """A balanced panel with an entity effect and a time effect and nothing
    else should demean to (almost) zero on both."""
    entities = np.repeat(np.arange(6), 5)
    times = np.tile(np.arange(5), 6)
    y = 3.0 + entities * 2.0 + times * 0.5
    demeaned, = within([y], [entities, times])
    assert np.abs(demeaned).max() < 1e-8


def test_within_regression_ignores_between_unit_variation():
    """The whole reason fixed effects are used here.

    Each unit has its own price level and its own popularity, correlated so
    that a pooled regression sees a *positive* slope. The within estimator
    should still find the negative one that operates inside each unit.
    """
    rng = np.random.default_rng(7)
    n_units, n_periods, true_beta = 40, 25, -0.8
    unit = np.repeat(np.arange(n_units), n_periods)
    level = np.repeat(rng.normal(scale=1.0, size=n_units), n_periods)

    log_p = level + rng.normal(scale=0.25, size=n_units * n_periods)
    log_q = 3.0 * level + true_beta * log_p + rng.normal(scale=0.1, size=n_units * n_periods)

    pooled = ols(log_q, log_p)
    assert pooled["beta"][1] > 0, "the pooled slope should be misleadingly positive here"

    y_d, p_d = within([log_q, log_p], [unit])
    fit = ols(y_d, p_d, cluster=unit, absorbed=n_units, add_const=False)
    assert fit["beta"][0] == pytest.approx(true_beta, abs=0.05)
    assert fit["n_clusters"] == n_units


def test_clustered_errors_exceed_classical_when_shocks_are_shared():
    """Repeated observations on one unit are not independent draws."""
    rng = np.random.default_rng(3)
    n_units, n_periods = 30, 40
    unit = np.repeat(np.arange(n_units), n_periods)
    shock = np.repeat(rng.normal(scale=1.0, size=n_units), n_periods)
    x = rng.normal(size=n_units * n_periods) + shock
    y = -0.5 * x + shock * 2 + rng.normal(scale=0.3, size=n_units * n_periods)

    classical = ols(y, x)
    clustered = ols(y, x, cluster=unit)
    assert clustered["se"][1] > classical["se"][1]


def test_tsls_beats_ols_when_price_is_endogenous():
    rng = np.random.default_rng(11)
    n, true_beta = 4000, -1.2
    instrument = rng.normal(size=n)
    confounder = rng.normal(size=n)                  # moves price and quantity both
    log_p = 0.9 * instrument + 0.8 * confounder + rng.normal(scale=0.3, size=n)
    log_q = true_beta * log_p + 1.5 * confounder + rng.normal(scale=0.3, size=n)

    biased = ols(log_q, log_p)["beta"][1]
    fit = tsls(log_q, log_p, None, instrument)

    assert abs(biased - true_beta) > 0.3, "the setup should bias OLS"
    assert fit["beta"][1] == pytest.approx(true_beta, abs=0.05)
    assert fit["first_stage_f"] > 100, "a strong instrument should report a strong first stage"


def test_tsls_reports_a_weak_first_stage_as_weak():
    rng = np.random.default_rng(13)
    n = 500
    instrument = rng.normal(size=n)
    log_p = 0.01 * instrument + rng.normal(size=n)   # barely moves price
    log_q = -1.0 * log_p + rng.normal(size=n)
    fit = tsls(log_q, log_p, None, instrument)
    assert fit["first_stage_f"] < 10, "a useless instrument should not look strong"


def test_conditional_logit_recovers_its_coefficients():
    rng = np.random.default_rng(5)
    n_obs, n_alt = 6000, 4
    true = np.array([0.4, -0.9, 0.25, -2.0])         # 3 brand constants, then price

    prices = rng.uniform(1.0, 3.0, size=(n_obs, n_alt))
    X = np.zeros((n_obs, n_alt, 4))
    for j in range(1, n_alt):
        X[:, j, j - 1] = 1.0
    X[:, :, 3] = prices

    utility = X @ true + rng.gumbel(size=(n_obs, n_alt))
    chosen = utility.argmax(axis=1)

    fit = conditional_logit(X, chosen)
    assert fit["beta"] == pytest.approx(true, abs=0.15)
    assert 0 < fit["pseudo_r_squared"] < 1
    assert fit["shares"].sum() == pytest.approx(1.0)


def test_logit_elasticity_matches_the_closed_form():
    """beta * p * (1 - s), share-weighted across alternatives."""
    beta, se = -2.0, 0.1
    prices = np.array([2.0, 4.0])
    shares = np.array([0.75, 0.25])
    value, value_se = logit_own_price_elasticity(beta, se, prices, shares)

    expected_weighted = 0.75 * (2.0 * 0.25) + 0.25 * (4.0 * 0.75)
    assert value == pytest.approx(beta * expected_weighted)
    assert value_se == pytest.approx(abs(se * expected_weighted))
    assert value < 0


def test_summarize_shape_matches_the_api_contract():
    row = summarize(-1.5, 0.25, 900, method="within")
    assert row["ci_low"] == pytest.approx(-1.99, abs=0.01)
    assert row["ci_high"] == pytest.approx(-1.01, abs=0.01)
    assert row["ci_low"] < row["elasticity"] < row["ci_high"]
    # 1.10 ** -1.5 = 0.867, so a 10% price rise costs 13.3% of units.
    assert row["pct_quantity_change_for_10pct_price_increase"] == pytest.approx(-13.3, abs=0.1)
    assert row["method"] == "within"
