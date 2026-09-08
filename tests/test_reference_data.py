"""
The estimator, the reference roster, and the manifest that documents them.

tests/test_elasticity_math.py pins the arithmetic that turns an elasticity
into a decision. This file pins the step before it: that the estimator
recovers a slope it is given, that it declines to invent one it cannot
identify, and that the twelve reference markets stay honestly described.
"""

import csv
import math

import numpy as np
import pandas as pd
import pytest

from src.build_reference_benchmarks import _flag
from src.panel_regression import (
    choice_share_loglog,
    pooled_loglog,
    within_entity_loglog,
)
from src.reference_data import REFERENCE_DATASETS


# ------------------------------------------------------------- the estimator --

def _panel(beta, n_entities=40, n_periods=12, noise=0.0, seed=0):
    """A panel with a known slope, and entity effects the fit must remove.

    Baselines and price levels differ wildly between entities, so a
    cross-sectional regression on this data would report nonsense. Only the
    within-entity transform can recover `beta`.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_entities):
        base_q = rng.uniform(50, 5000)          # popularity varies hugely
        base_p = rng.uniform(1, 100)            # so does price level
        for t in range(n_periods):
            price = base_p * math.exp(rng.normal(0, 0.25))
            qty = base_q * (price / base_p) ** beta
            if noise:
                qty *= math.exp(rng.normal(0, noise))
            rows.append({"entity": f"e{e}", "price": price, "qty": qty})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("beta", [-2.5, -1.0, -0.4])
def test_the_estimator_recovers_a_slope_it_was_given(beta):
    result = within_entity_loglog(_panel(beta), "entity", "price", "qty")
    assert result is not None
    assert result["elasticity"] == pytest.approx(beta, abs=0.01)


def test_entity_effects_are_removed_not_fitted():
    """The whole point of demeaning: baseline popularity must not leak in.

    Here big sellers are also expensive, which cross-sectionally looks like
    *upward*-sloping demand. The within transform should be unmoved.
    """
    rng = np.random.default_rng(7)
    rows = []
    for e in range(40):
        base_q = 100 * (e + 1)
        base_p = 2 * (e + 1)          # price and volume correlated across entities
        for _ in range(12):
            price = base_p * math.exp(rng.normal(0, 0.25))
            rows.append({"entity": f"e{e}", "price": price,
                         "qty": base_q * (price / base_p) ** -1.5})
    frame = pd.DataFrame(rows)

    naive = np.polyfit(np.log(frame["price"]), np.log(frame["qty"]), 1)[0]
    assert naive > 0, "the confound this test exists for is not present"

    within = within_entity_loglog(frame, "entity", "price", "qty")
    assert within["elasticity"] == pytest.approx(-1.5, abs=0.01)


def test_noise_widens_the_interval_rather_than_moving_the_estimate():
    clean = within_entity_loglog(_panel(-1.8, noise=0.0, seed=3), "entity", "price", "qty")
    noisy = within_entity_loglog(_panel(-1.8, noise=0.5, seed=3), "entity", "price", "qty")
    assert noisy["std_error"] > clean["std_error"] * 5
    assert noisy["ci_low"] < -1.8 < noisy["ci_high"]


def test_a_flat_price_returns_nothing_rather_than_a_number():
    """No within-entity price variation means no identified slope."""
    frame = pd.DataFrame([
        {"entity": f"e{e}", "price": 10.0, "qty": 100.0 + t}
        for e in range(20) for t in range(10)
    ])
    assert within_entity_loglog(frame, "entity", "price", "qty") is None


def test_entities_seen_once_cannot_contribute():
    frame = pd.DataFrame([
        {"entity": f"e{e}", "price": 5.0 + e, "qty": 100.0 - e} for e in range(60)
    ])
    assert within_entity_loglog(frame, "entity", "price", "qty") is None


def test_too_little_data_returns_nothing():
    assert within_entity_loglog(_panel(-1.0, n_entities=2, n_periods=3), "entity", "price", "qty") is None


def test_weighting_follows_the_heavier_price_points():
    """A price point behind 1,000 occasions should outweigh one behind five."""
    frame = pd.DataFrame([
        {"brand": "a", "price": 1.0, "share": 0.50, "n": 1000},
        {"brand": "a", "price": 2.0, "share": 0.25, "n": 1000},
        {"brand": "a", "price": 4.0, "share": 0.40, "n": 1},      # noisy outlier
        {"brand": "b", "price": 1.0, "share": 0.40, "n": 1000},
        {"brand": "b", "price": 2.0, "share": 0.20, "n": 1000},
        {"brand": "b", "price": 4.0, "share": 0.32, "n": 1},
    ] * 3)
    weighted = within_entity_loglog(frame, "brand", "price", "share",
                                    weight="n", min_observations=6)
    unweighted = within_entity_loglog(frame, "brand", "price", "share",
                                      min_observations=6)
    assert weighted["elasticity"] < unweighted["elasticity"], (
        "the thinly-observed outlier should pull the unweighted fit flatter")


def test_pooled_fit_recovers_a_single_series():
    rng = np.random.default_rng(11)
    price = np.exp(rng.normal(0, 0.3, 200)) * 3
    qty = 500 * (price / 3) ** -0.8
    frame = pd.DataFrame({"price": price, "qty": qty})
    assert pooled_loglog(frame, "price", "qty")["elasticity"] == pytest.approx(-0.8, abs=0.01)


def test_choice_shares_need_at_least_two_brands():
    frame = pd.DataFrame({"choice": ["a"] * 100, "price.a": [1.0] * 100})
    assert choice_share_loglog(frame, "choice", {"a": "price.a"}) is None


# ------------------------------------------------------------------- flagging --

@pytest.mark.parametrize("result,expected", [
    ({"elasticity": -1.5, "ci_low": -1.8, "ci_high": -1.2}, None),
    ({"elasticity": -0.001, "ci_low": -0.03, "ci_high": 0.028}, "inconclusive"),
    ({"elasticity": 0.074, "ci_low": 0.066, "ci_high": 0.083}, "confounded"),
])
def test_unusable_estimates_are_flagged(result, expected):
    assert _flag(result)["flag"] == expected


def test_a_flagged_estimate_always_explains_itself():
    for result in ({"elasticity": 0.5, "ci_low": 0.4, "ci_high": 0.6},
                   {"elasticity": 0.0, "ci_low": -0.1, "ci_high": 0.1}):
        assert _flag(result)["flag_reason"].strip()


# -------------------------------------------------------------- the roster --

def test_the_roster_is_twelve_markets_that_all_name_a_source():
    assert len(REFERENCE_DATASETS) == 12
    for spec in REFERENCE_DATASETS:
        assert spec.source.strip(), f"{spec.key} has no source"
        assert spec.market.strip(), f"{spec.key} does not say where or when"
        assert spec.url.startswith("https://raw.githubusercontent.com/")


def test_every_reference_key_and_filename_is_unique():
    assert len({s.key for s in REFERENCE_DATASETS}) == 12
    assert len({s.filename for s in REFERENCE_DATASETS}) == 12


def test_each_estimator_gets_the_columns_it_needs():
    for spec in REFERENCE_DATASETS:
        if spec.estimator == "panel":
            assert spec.entity and spec.price and spec.quantity, spec.key
        elif spec.estimator == "series":
            assert spec.price and spec.quantity and not spec.entity, spec.key
        elif spec.estimator == "choice":
            assert spec.choice_column and len(spec.brands) >= 2, spec.key
        else:
            pytest.fail(f"{spec.key} has an unknown estimator {spec.estimator!r}")


def test_the_simulated_datasets_stay_out():
    """Three candidates passed the column screen and were rejected by hand.

    They fit beautifully and mean nothing, which is exactly why a mechanical
    screen can't be the last word.
    """
    haystack = " ".join(s.url + s.source + s.label for s in REFERENCE_DATASETS).lower()
    for rejected in ("carseats", "kmenta", "stat2data"):
        assert rejected not in haystack


# ------------------------------------------------------------ the manifest --

def test_the_manifest_documents_every_reference_dataset():
    from src.build_manifest import MANIFEST_PATH

    with open(MANIFEST_PATH, newline="") as f:
        rows = {r["filename"]: r for r in csv.DictReader(f)}

    for spec in REFERENCE_DATASETS:
        row = rows.get(f"reference/{spec.filename}")
        assert row is not None, f"{spec.filename} is missing from the manifest"
        assert row["source_url"] == spec.url
        assert row["status"] in ("downloaded", "not_downloaded")


def test_a_blocked_dataset_keeps_its_recorded_figures():
    """The two originals sit behind an egress policy on some networks.

    They must stay in the manifest with the counts from when they were last
    profiled, rather than dropping out or reporting zero.
    """
    from src.build_manifest import MANIFEST_PATH

    with open(MANIFEST_PATH, newline="") as f:
        rows = {r["filename"]: r for r in csv.DictReader(f)}

    for name in ("scanner_data.csv", "monash_dominicks.csv"):
        row = rows[name]
        assert row["status"] in ("downloaded", "previously_profiled")
        assert int(row["row_count"]) > 0
        if row["status"] == "previously_profiled":
            assert "carried forward" in row["note"]
            assert row["note"].count("Figures carried forward") == 1, (
                "rebuilds must be idempotent, not append the note again")
