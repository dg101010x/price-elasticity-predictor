"""
The one normalised row every source is mapped onto, and the adapters that map
each raw source shape (marketplace listing, POS aggregate, price-monitoring
feed) onto it. Raw rows keep their source's field names on disk; only the
pipeline sees `Observation`.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from pydantic import BaseModel, field_validator

CHANNELS = {"online", "in-store", "wholesale", "omnichannel"}


class Observation(BaseModel):
    date: date
    country: str
    region: Optional[str] = None
    merchant: str
    category: Optional[str] = None
    product_sku: str
    product_name: Optional[str] = None
    channel: str = "online"
    price_usd: Optional[float] = None
    price_local: Optional[float] = None
    local_currency: Optional[str] = None
    units_sold: Optional[float] = None
    units_in_stock: Optional[float] = None
    merchant_type: Optional[str] = None
    source: str

    @field_validator("country")
    @classmethod
    def _iso2(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError("country must be an ISO 3166-1 alpha-2 code")
        return v

    @field_validator("channel")
    @classmethod
    def _channel(cls, v: str) -> str:
        v = v.strip().lower().replace("_", "-")
        if v not in CHANNELS:
            raise ValueError(f"channel must be one of {sorted(CHANNELS)}")
        return v


def _ecommerce(r: dict) -> dict:
    return dict(
        date=r["date"], country=r["country"], region=r.get("region"),
        merchant=r["merchant"], category=r.get("category"),
        product_sku=r["product_sku"], product_name=r.get("product_name"),
        channel=r.get("channel", "online"), price_usd=r.get("price_usd"),
        price_local=r.get("price_local"), local_currency=r.get("local_currency"),
        units_sold=r.get("units_sold_past_week"),
        units_in_stock=r.get("units_in_stock"), source=r["source"],
    )


def _pos(r: dict) -> dict:
    # POS rows carry one price in a currency named by the field suffix
    # ("avg_price_inr"); there is no separate currency column.
    key = next((k for k in r if k.startswith("avg_price_")), None)
    return dict(
        date=r["date"], country=r["country"], region=r.get("city"),
        merchant=r["merchant_id"], category=r.get("product_category"),
        product_sku=r["product_name"], product_name=r["product_name"],
        channel="in-store", merchant_type=r.get("merchant_type"),
        price_local=r[key] if key else None,
        local_currency=key.rsplit("_", 1)[1].upper() if key else None,
        units_sold=r.get("quantity_sold"), units_in_stock=r.get("units_in_stock"),
        source=r["source"],
    )


def _feed(r: dict) -> dict:
    key = next((k for k in r if k.startswith("price_") and len(k) == 9), None)
    return dict(
        date=r["date"], country=r["country"], region=r.get("city"),
        merchant=f"{r['source']}_agg", category=r.get("product_category"),
        product_sku=r["product_name"], product_name=r["product_name"],
        channel="omnichannel", merchant_type="aggregate",
        price_local=r[key] if key else None,
        local_currency=key.rsplit("_", 1)[1].upper() if key else None,
        source=r["source"],
    )


ADAPTERS: dict[str, Callable[[dict], dict]] = {
    "ecommerce": _ecommerce,
    "pos": _pos,
    "feed": _feed,
}


def adapter_for(filename: str) -> Callable[[dict], dict]:
    """Pick the adapter from the raw file's name: jumia_ng.jsonl -> ecommerce,
    pos_partner_in.jsonl -> pos, feed_za.jsonl -> feed."""
    stem = filename.split(".")[0]
    if stem.startswith("pos_"):
        return ADAPTERS["pos"]
    if stem.startswith("feed_"):
        return ADAPTERS["feed"]
    return ADAPTERS["ecommerce"]
