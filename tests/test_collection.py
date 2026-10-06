"""The intake pipeline: adapters, the plan's validation rules, dedup, enrichment."""

import json

import pandas as pd
import pytest

from src.collection import pipeline, quality
from src.collection.schema import Observation, adapter_for

TODAY = pd.Timestamp("2026-10-06")
FX = {"NGN": 1550.0, "INR": 83.0}


def jumia(**kw):
    row = dict(date="2026-10-05", country="NG", region="Lagos", merchant="m1",
               category="Electronics", product_sku="a15", product_name="A15",
               price_local=155000, local_currency="NGN", units_sold_past_week=10,
               channel="online", source="jumia_api")
    row.update(kw)
    return row


def write(tmp_path, day, name, rows):
    d = tmp_path / "raw" / day
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text("\n".join(json.dumps(r) for r in rows))


def run(tmp_path, today=TODAY):
    return pipeline.run(tmp_path / "raw", tmp_path / "out", FX, today)


def test_adapters_map_each_source_shape():
    pos = {"date": "2026-10-05", "country": "IN", "city": "Bangalore", "merchant_id": "k42",
           "merchant_type": "neighborhood_grocery", "product_category": "Packaged_Foods",
           "product_name": "Maggi", "quantity_sold": 45, "avg_price_inr": 28, "source": "pos"}
    o = Observation(**adapter_for("pos_partner_in.jsonl")(pos))
    assert (o.region, o.channel, o.local_currency, o.units_sold) == ("Bangalore", "in-store", "INR", 45)
    feed = {"date": "2026-10-05", "country": "ZA", "city": "Johannesburg",
            "product_category": "Beverages", "product_name": "Coke", "price_zar": 14.99, "source": "feed"}
    o = Observation(**adapter_for("feed_za.jsonl")(feed))
    assert (o.local_currency, o.channel) == ("ZAR", "omnichannel")


def test_usd_price_is_derived_from_the_rate_and_unknown_currency_is_not_guessed(tmp_path):
    write(tmp_path, "2026-10-05", "jumia_ng.jsonl",
          [jumia(), jumia(product_sku="b", local_currency="XXX")])
    stats = run(tmp_path)
    assert stats["kept"] == 1
    out = pd.read_parquet(tmp_path / "out" / "enriched.parquet")
    assert out["price_usd"].iloc[0] == pytest.approx(100.0)
    rej = [json.loads(l) for l in (tmp_path / "out" / "rejected.jsonl").read_text().splitlines()]
    assert rej[0]["reject_reason"] == "price_out_of_range"


@pytest.mark.parametrize("kw,reason", [
    (dict(price_local=100), "price_out_of_range"),                  # $0.06
    (dict(price_local=2e9), "price_out_of_range"),
    (dict(date="2026-10-20"), "date_out_of_range"),                 # future
    (dict(date="2024-01-01"), "date_out_of_range"),                 # > 2 years
    (dict(region=None), "no_region"),
])
def test_validation_rules(tmp_path, kw, reason):
    write(tmp_path, "2026-10-05", "jumia_ng.jsonl", [jumia(**kw)])
    run(tmp_path)
    rej = [json.loads(l) for l in (tmp_path / "out" / "rejected.jsonl").read_text().splitlines()]
    assert [r["reject_reason"] for r in rej] == [reason]


def test_exact_duplicates_keep_first_and_near_duplicates_are_flagged_not_dropped():
    df = pd.DataFrame([
        dict(country="NG", merchant="m", product_sku="a", date="d", channel="online", category="c", price_usd=100.0),
        dict(country="NG", merchant="m", product_sku="a", date="d", channel="online", category="c", price_usd=999.0),
        dict(country="NG", merchant="m", product_sku="b", date="d", channel="online", category="c", price_usd=103.0),
        dict(country="NG", merchant="m", product_sku="c", date="d", channel="online", category="c", price_usd=500.0),
    ])
    out = quality.dedupe(df)
    assert list(out["product_sku"]) == ["a", "b", "c"]
    assert out["price_usd"].iloc[0] == 100.0
    assert list(out["possible_duplicate"]) == [True, True, False]


def test_competition_intensity_and_seasonality(tmp_path):
    rows = [jumia(merchant=f"m{i}", product_sku=f"s{i}", price_local=155000 * (1 + i), units_sold_past_week=10)
            for i in range(5)]
    rows.append(jumia(region="Abuja", merchant="solo", date="2026-09-05"))
    write(tmp_path, "2026-10-05", "jumia_ng.jsonl", rows)
    run(tmp_path)
    out = pd.read_parquet(tmp_path / "out" / "enriched.parquet")
    assert out[out.region == "Lagos"]["competition_intensity_local"].iloc[0] == 10.0
    assert out[out.region == "Abuja"]["competition_intensity_local"].iloc[0] == 2.0
    assert out[out.region == "Lagos"]["seasonality_peak"].all()      # October, electronics
    assert not out[out.region == "Abuja"]["seasonality_peak"].any()  # September


def test_low_quality_rows_are_dropped_and_say_so(tmp_path):
    write(tmp_path, "2026-10-05", "jumia_ng.jsonl",
          [jumia(units_sold_past_week=None, category=None)])  # -0.15 -0.10 -> 0.75
    stats = run(tmp_path)
    assert stats["kept"] == 0
    rej = (tmp_path / "out" / "rejected.jsonl").read_text()
    assert "quality_below_floor" in rej


def test_unparseable_lines_are_rejected_not_fatal(tmp_path):
    write(tmp_path, "2026-10-05", "jumia_ng.jsonl", [jumia(), {"country": "NG"}, jumia(country="Nigeria", product_sku="z")])
    stats = run(tmp_path)
    assert stats["kept"] == 1 and stats["rejected"] == 2


def test_a_source_losing_half_its_rows_raises_an_alert(tmp_path):
    day1 = [jumia(product_sku=f"s{i}", merchant=f"m{i}") for i in range(4)]
    day2 = [jumia(product_sku="s0", date="2026-10-06")]
    write(tmp_path, "2026-10-05", "jumia_ng.jsonl", day1)
    write(tmp_path, "2026-10-06", "jumia_ng.jsonl", day2)
    assert run(tmp_path)["alerts"] == ["jumia_api: 1 rows on 2026-10-06 vs 4 on 2026-10-05"]
