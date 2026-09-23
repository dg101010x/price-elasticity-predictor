"""
Synthetic sales histories with a known price elasticity, for tests and demos.

Each product has its own baseline popularity and price level; its weekly
price moves (small promotions, occasional list-price changes) and weekly
units respond with the chosen elasticity plus noise. Because the answer is
known in advance, a test can check that an upload came back near *its own*
number -- and a different upload came back near a different one -- rather
than just checking that some number appeared.

    python -m tests.synthetic_sales            # writes examples/*.csv
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def make_sales_csv(
    categories: dict[str, tuple[int, float]],
    weeks: int = 52,
    seed: int = 0,
    start: date = date(2024, 1, 1),
    headers: tuple[str, ...] = ("Week", "SKU", "Product Name", "Category", "Unit Price", "Units Sold"),
    daily: bool = False,
    date_format: str = "%Y-%m-%d",
) -> bytes:
    """`categories` maps a category name to (products, true elasticity).

    With daily=True each product-week is split over a few days at the same
    price, to exercise the weekly rollup; otherwise one row per product-week.
    """
    rng = np.random.default_rng(seed)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for cat, (n_products, elasticity) in categories.items():
        prefix = "".join(w[0] for w in cat.split()).upper()[:3] or "P"
        for j in range(n_products):
            sku = f"{prefix}-{j + 1:03d}"
            base_price = float(np.round(np.exp(rng.normal(2.6, 0.5)), 2))
            base_units = float(np.exp(rng.normal(3.6, 0.6)))
            list_price = base_price
            for w in range(weeks):
                if rng.random() < 0.04:                        # an occasional list-price change
                    list_price = round(list_price * float(np.exp(rng.normal(0.03, 0.08))), 2)
                promo = rng.random() < 0.18                   # a promotion week
                price = round(list_price * (float(rng.uniform(0.7, 0.9)) if promo else 1.0), 2)
                mu = base_units * (price / base_price) ** elasticity * float(np.exp(rng.normal(0, 0.12)))
                units = int(rng.poisson(max(mu, 0.2)))
                if units <= 0:
                    continue
                week_start = start + timedelta(weeks=w)
                if daily:
                    split = np.array_split(np.arange(units), int(rng.integers(1, 4)))
                    for d, chunk in enumerate(split):
                        if len(chunk):
                            day = week_start + timedelta(days=int(d * 2))
                            writer.writerow([day.strftime(date_format), sku, f"{cat} item {j + 1}", cat,
                                             f"{price:.2f}", len(chunk)])
                else:
                    writer.writerow([week_start.strftime(date_format), sku, f"{cat} item {j + 1}", cat,
                                     f"{price:.2f}", units])
    return out.getvalue().encode()


# Two businesses that should come back with clearly different answers.
GIFT_SHOP = {"Candles": (22, -2.2), "Mugs": (20, -1.6), "Greeting Cards": (8, -1.0)}
COFFEE_ROASTER = {"Single Origin": (18, -0.45), "Blends": (17, -0.6)}


def main() -> None:
    out = ROOT / "examples"
    out.mkdir(exist_ok=True)
    (out / "sample_gift_shop_weekly.csv").write_bytes(make_sales_csv(GIFT_SHOP, seed=1))
    (out / "sample_coffee_roaster_daily.csv").write_bytes(
        make_sales_csv(COFFEE_ROASTER, seed=2, daily=True,
                       headers=("Date", "Item Code", "Item Name", "Department", "Price", "Qty")))
    print(f"wrote {sorted(p.name for p in out.glob('*.csv'))}")


if __name__ == "__main__":
    main()
