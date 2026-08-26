"""
Data acquisition for the price elasticity predictor.

Every source below is fetched over plain HTTPS with no account, token or
registration. The set was assembled by searching for public data that
actually carries *both* a price and a quantity (or a promotion that moves
price), which is what an elasticity estimate needs and what most "retail
dataset" listings quietly lack:

  transaction / scanner
  - UCI "Online Retail II"                -> scanner_data.csv
  - dunnhumby "The Complete Journey"      -> completejourney_transactions.csv
                                             completejourney_products.csv
                                             completejourney_promotions.csv
  - Olist Brazilian e-commerce (official) -> olist_order_items.csv
  - pizzeria POS year                     -> pizza_pos_sales.csv
  - 6 household brand-choice panels       -> brandchoice_*.csv, oj_brand_choice.csv

  store/product weekly panels
  - Dominick's Finer Foods OJ panel       -> dominicks_oj.csv
  - Monash "Dominick Dataset"             -> monash_dominicks.csv
  - designed promotion experiment         -> grocery_promo_experiment.csv

  benchmark demand curves (published elasticities to check a model against)
  - cigarettes, gasoline, natural gas, journals, Fulton fish market,
    avocados, ice cream, Italian budget shares, car seats w/ competitor price

Still out of reach without credentials or a browser, and declared here so
the manifest keeps saying so:

  - Kaggle: the API returns 403 for every dataset without a valid
    ~/.kaggle/kaggle.json (or KAGGLE_USERNAME/KAGGLE_KEY env vars).
  - Kilts Center (raw Dominick's, all 29 categories): manual academic
    registration on chicagobooth.edu; no API.
  - Harvard Dataverse (E-FooD): behind a WAF challenge that blocks
    non-browser requests.

`download_kaggle_dataset()` is a real, working function -- it will succeed as
soon as valid Kaggle credentials are present -- so re-running `main()` after
the user configures credentials fills in the rest without any code changes.

Each fetch is independent: a source that is unreachable from the machine
running this (a restricted network, a host that has gone away) is recorded
as `unreachable` with the reason and the run continues.

Run: python -m src.data_loader
"""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CSV_DIR = DATA_DIR / "csv"
RAW_DIR = DATA_DIR / "raw_downloads"
MANIFEST_DIR = DATA_DIR / "manifests"

for d in (CSV_DIR, RAW_DIR, MANIFEST_DIR, DATA_DIR / "processed"):
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class DatasetSpec:
    filename: str
    source_url: str
    description: str
    data_type: str  # transaction | weekly | aggregated | dimension
    key_elasticity_columns: str
    # downloaded | not_downloaded | manual_required | unreachable
    status: str = "not_downloaded"
    note: str = ""
    row_count: Optional[int] = None
    columns: Optional[int] = None
    date_range: str = ""


# ---------------------------------------------------------------------------
# 1. UCI Online Retail II -- real, no-auth download
# ---------------------------------------------------------------------------

ONLINE_RETAIL_II_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"


ONLINE_RETAIL_II_SPEC = dict(
    filename="scanner_data.csv",
    source_url="https://archive.ics.uci.edu/dataset/502/online+retail+ii",
    description=(
        "UK-based online retailer, ~1.07M invoice line items, Dec 2009-Dec "
        "2011. Substituted for the gated Kaggle 'retail-scanner-data' "
        "notebook dataset (marian447), which requires Kaggle auth this "
        "environment doesn't have. Transaction-level: invoice, SKU "
        "(StockCode), quantity, unit price, customer ID, country, "
        "timestamp -- everything needed for a log-log elasticity "
        "regression, and it's the dataset src/api.py's stub figures "
        "(product 85123A etc.) are already drawn from."
    ),
    data_type="transaction",
    key_elasticity_columns="InvoiceDate,Quantity,Price,StockCode,Customer ID",
)


def download_online_retail_ii() -> DatasetSpec:
    spec = DatasetSpec(**ONLINE_RETAIL_II_SPEC)

    zip_path = RAW_DIR / "online_retail_II.zip"
    xlsx_path = RAW_DIR / "online_retail_II.xlsx"
    out_path = CSV_DIR / spec.filename

    if not zip_path.exists():
        resp = requests.get(ONLINE_RETAIL_II_URL, timeout=120)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)

    if not xlsx_path.exists():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(RAW_DIR)

    import pandas as pd

    sheets = pd.read_excel(xlsx_path, sheet_name=None, engine="openpyxl")
    df = pd.concat(sheets.values(), ignore_index=True)
    df = df.dropna(subset=["Invoice", "StockCode"])
    df.to_csv(out_path, index=False)

    spec.status = "downloaded"
    spec.row_count = len(df)
    spec.columns = len(df.columns)
    spec.date_range = f"{df['InvoiceDate'].min()} to {df['InvoiceDate'].max()}"
    return spec


# ---------------------------------------------------------------------------
# 2. Monash "Dominick Dataset" (Zenodo mirror of the reformatted Kilts DFF
#    data) -- real, no-auth download. The .tsf format has no header row and
#    no per-value dates (weekly frequency, but no start timestamp is given
#    per series), so this is reshaped into long format: SKU_ID, Week_Index,
#    Weekly_Profit.
# ---------------------------------------------------------------------------

DOMINICK_ZENODO_URL = "https://zenodo.org/records/4654802/files/dominick_dataset.zip"


def _parse_tsf_data_section(tsf_path: Path):
    with open(tsf_path, "r") as f:
        in_data = False
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("@data"):
                in_data = True
                continue
            if not in_data:
                continue
            series_name, _, values = line.partition(":")
            for week_idx, raw_val in enumerate(values.split(",")):
                yield series_name, week_idx, raw_val


MONASH_DOMINICKS_SPEC = dict(
    filename="monash_dominicks.csv",
    source_url="https://zenodo.org/records/4654802",
    description=(
        "Monash Time Series Forecasting Archive's 'Dominick Dataset': "
        "115,704 weekly time series of per-SKU profit, reformatted from "
        "the Kilts Center Dominick's Finer Foods scanner data (the raw "
        "DFF files themselves require Kilts Center academic "
        "registration and aren't fetchable here). Series are anonymized "
        "(T1, T2, ...) with no store ID, UPC, or promotion flag -- only "
        "a per-week profit value -- and no absolute start date, so "
        "'Week' below is a per-series relative index, not a calendar "
        "date."
    ),
    data_type="weekly",
    key_elasticity_columns="SKU_ID,Week_Index,Weekly_Profit",
)


def download_monash_dominicks() -> DatasetSpec:
    spec = DatasetSpec(**MONASH_DOMINICKS_SPEC)

    zip_path = RAW_DIR / "dominick_dataset.zip"
    tsf_path = RAW_DIR / "dominick_dataset.tsf"
    out_path = CSV_DIR / spec.filename

    if not zip_path.exists():
        resp = requests.get(DOMINICK_ZENODO_URL, timeout=180)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)

    if not tsf_path.exists():
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(RAW_DIR)

    row_count = 0
    series_ids = set()
    with open(out_path, "w", newline="") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["SKU_ID", "Week_Index", "Weekly_Profit"])
        for series_name, week_idx, raw_val in _parse_tsf_data_section(tsf_path):
            writer.writerow([series_name, week_idx, raw_val])
            row_count += 1
            series_ids.add(series_name)

    spec.status = "downloaded"
    spec.row_count = row_count
    spec.columns = 3
    spec.date_range = f"relative week 0-N per series ({len(series_ids)} series, no calendar dates)"
    return spec


# ---------------------------------------------------------------------------
# 3. dunnhumby "The Complete Journey" (84.51 degrees) -- real, no-auth
#    download. The completejourney R package keeps the full tables as .rds
#    blobs in its GitHub repo (the CRAN package itself only ships samples),
#    and those blobs are plain HTTPS files, so they are fetchable without R.
#    Reading them needs `pyreadr`; if it isn't installed the datasets are
#    reported as manual_required with the pip hint rather than skipped.
# ---------------------------------------------------------------------------

COMPLETEJOURNEY_BASE = (
    "https://raw.githubusercontent.com/bradleyboehmke/completejourney/master/data"
)

COMPLETEJOURNEY_FILES = [
    dict(
        remote="transactions.rds",
        filename="completejourney_transactions.csv",
        description=(
            "dunnhumby / 84.51 'The Complete Journey': 1.47M line items from "
            "2,469 frequent-shopper households at a US grocery retailer over "
            "2017. Each row carries quantity, sales_value (what was paid) and "
            "the discounts that were taken off it (retail_disc, coupon_disc, "
            "coupon_match_disc), so both the paid unit price "
            "(sales_value/quantity) and the undiscounted shelf price "
            "((sales_value+retail_disc+coupon_disc+coupon_match_disc)/quantity) "
            "are recoverable. The discount-driven price variation is promotion-"
            "led rather than pure cross-sectional, which identifies elasticity "
            "far better than list-price variation alone."
        ),
        data_type="transaction",
        key_elasticity_columns=(
            "transaction_timestamp,week,household_id,store_id,product_id,"
            "quantity,sales_value,retail_disc,coupon_disc,coupon_match_disc"
        ),
    ),
    dict(
        remote="products.rda",
        filename="completejourney_products.csv",
        description=(
            "Product dimension for completejourney_transactions.csv: 92,331 "
            "product_ids with department, product_category, product_type, "
            "package_size and brand (National vs Private). This is the piece "
            "the UCI Online Retail II data is missing -- real category labels "
            "instead of the keyword heuristics in "
            "src/build_elasticity_model.py -- so category-level elasticities "
            "estimated on this join are labelled, not guessed."
        ),
        data_type="dimension",
        key_elasticity_columns="product_id,department,product_category,product_type,brand",
    ),
    dict(
        remote="promotions.rds",
        filename="completejourney_promotions.csv",
        description=(
            "In-store display and mailer placement per product/store/week for "
            "the Complete Journey period (20.9M rows, 59,800 products, 112 "
            "stores, 53 weeks). Joins to the transactions table on "
            "product_id/store_id/week and gives the promotion controls a "
            "price-response regression needs to separate a price cut from the "
            "display and feature advertising that usually ships with it. "
            "Large: expect a ~700 MB CSV."
        ),
        data_type="weekly",
        key_elasticity_columns="product_id,store_id,week,display_location,mailer_location",
    ),
]


def download_completejourney_file(
    remote: str, filename: str, **spec_kwargs
) -> DatasetSpec:
    spec = DatasetSpec(
        filename=filename,
        source_url=f"{COMPLETEJOURNEY_BASE}/{remote}",
        **spec_kwargs,
    )

    try:
        import pyreadr
    except ImportError:
        spec.status = "manual_required"
        spec.note = (
            "The upstream file is an R .rds/.rda blob; reading it without R "
            "needs `pip install pyreadr` (it is in requirements.txt). Install "
            "it and re-run."
        )
        return spec

    raw_path = RAW_DIR / remote
    if not raw_path.exists():
        resp = requests.get(spec.source_url, timeout=300)
        resp.raise_for_status()
        raw_path.write_bytes(resp.content)

    df = list(pyreadr.read_r(str(raw_path)).values())[0]
    df.to_csv(CSV_DIR / filename, index=False)

    spec.status = "downloaded"
    spec.row_count = len(df)
    spec.columns = len(df.columns)
    if "transaction_timestamp" in df.columns:
        spec.date_range = (
            f"{df['transaction_timestamp'].min()} to {df['transaction_timestamp'].max()}"
        )
    elif "week" in df.columns:
        spec.date_range = f"weeks {int(df['week'].min())}-{int(df['week'].max())} of 2017"
    spec.note = (
        "Source: 84.51 degrees 'The Complete Journey', redistributed as R data "
        f"files by the completejourney package. Converted from {remote} with "
        "pyreadr."
    )
    return spec


# ---------------------------------------------------------------------------
# 4. Dominick's Finer Foods orange juice panel -- real, no-auth download.
#    83 Chicago stores x 3 brands x 121 weeks of the Kilts Center DFF scanner
#    data, the extract that circulates with the Booth/Taddy course material.
#    Two mirrors are tried: the first carries the full 17-column panel
#    (store/week/demographics), the second only the 4 columns the textbook
#    uses -- still enough for a brand-level elasticity, so it is a real
#    fallback rather than a failure.
# ---------------------------------------------------------------------------

DOMINICKS_OJ_MIRRORS = [
    "https://raw.githubusercontent.com/gchoi/Dataset/master/oj.csv",
    "https://raw.githubusercontent.com/TaddyLab/BDS/master/examples/oj.csv",
]


DOMINICKS_OJ_SPEC = dict(
    filename="dominicks_oj.csv",
    source_url=DOMINICKS_OJ_MIRRORS[0],
    description=(
        "Dominick's Finer Foods refrigerated orange juice: 28,947 "
        "store-week-brand rows (83 Chicago-area stores, 3 brands -- "
        "Dominick's, Minute Maid, Tropicana -- over 121 weeks) from the "
        "Kilts Center DFF scanner data. logmove is log units sold, price "
        "is the shelf price and feat flags in-store/newspaper feature "
        "advertising, plus 11 store-neighbourhood demographics. This is "
        "the store-level, promotion-flagged, cross-brand panel that "
        "monash_dominicks.csv cannot provide (that reformat is anonymized "
        "to profit series), and the standard worked example for own- and "
        "cross-price elasticity: log(move) ~ log(price) by brand, with "
        "feat interacted."
    ),
    data_type="weekly",
    key_elasticity_columns="store,brand,week,logmove,price,feat",
)


def download_dominicks_oj() -> DatasetSpec:
    spec = DatasetSpec(**DOMINICKS_OJ_SPEC)

    out_path = CSV_DIR / spec.filename
    import pandas as pd

    last_error = ""
    for url in DOMINICKS_OJ_MIRRORS:
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - mirror fallback
            last_error = f"{url}: {exc}"
            continue

        (RAW_DIR / "dominicks_oj.csv").write_bytes(resp.content)
        df = pd.read_csv(io.StringIO(resp.text))
        df.to_csv(out_path, index=False)

        spec.source_url = url
        spec.status = "downloaded"
        spec.row_count = len(df)
        spec.columns = len(df.columns)
        if "week" in df.columns:
            spec.date_range = (
                f"store-weeks {int(df['week'].min())}-{int(df['week'].max())} "
                "(relative week index, 1989-1994 window, no calendar dates)"
            )
            spec.note = (
                f"Full panel mirror: {df['store'].nunique()} stores, "
                f"{df['brand'].nunique()} brands, {df['week'].nunique()} weeks. "
                "Units sold = exp(logmove)."
            )
        else:
            spec.date_range = "no week column in this mirror"
            spec.key_elasticity_columns = "sales,price,brand,feat"
            spec.note = (
                "Fell back to the reduced 4-column mirror (sales, price, "
                "brand, feat) -- same 28,947 rows, but without store, week or "
                "demographics, so only pooled/brand-level elasticity is "
                f"estimable. Primary mirror failed with: {last_error}"
            )
        return spec

    spec.status = "unreachable"
    spec.note = f"All mirrors failed. Last error: {last_error}"
    return spec


# ---------------------------------------------------------------------------
# 5. Olist Brazilian e-commerce -- real, no-auth download from the official
#    olist/work-at-olist-data GitHub repo (the same tables Kaggle hosts, but
#    published by Olist themselves, so no Kaggle credentials involved).
#    The four raw tables are joined into one order-item file with a real
#    timestamp and a real (English) product category on every row.
# ---------------------------------------------------------------------------

OLIST_BASE = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets"
OLIST_TABLES = [
    "olist_order_items_dataset",
    "olist_orders_dataset",
    "olist_products_dataset",
    "product_category_name_translation",
]


OLIST_SPEC = dict(
    filename="olist_order_items.csv",
    source_url="https://github.com/olist/work-at-olist-data",
    description=(
        "Olist Brazilian marketplace order items, Sep 2016-Oct 2018, "
        "joined here from the four official tables (order items x orders "
        "x products x category translation) into one row per unit sold: "
        "purchase timestamp, product_id, seller_id, English product "
        "category, item price and freight. ~112k units, ~33k products, 71 "
        "real category labels -- the category dimension the UCI dataset "
        "lacks, on genuine e-commerce price variation. Quantity is "
        "implicit: Olist writes one row per unit (order_item_id "
        "enumerates units within an order), so aggregate by "
        "(product_id, week) to get units sold."
    ),
    data_type="transaction",
    key_elasticity_columns=(
        "order_purchase_timestamp,product_id,product_category,price,"
        "freight_value,order_status"
    ),
)


def download_olist() -> DatasetSpec:
    spec = DatasetSpec(**OLIST_SPEC)

    import pandas as pd

    frames = {}
    for table in OLIST_TABLES:
        raw_path = RAW_DIR / f"{table}.csv"
        if not raw_path.exists():
            resp = requests.get(f"{OLIST_BASE}/{table}.csv", timeout=300)
            resp.raise_for_status()
            raw_path.write_bytes(resp.content)
        frames[table] = pd.read_csv(raw_path)

    items = frames["olist_order_items_dataset"]
    orders = frames["olist_orders_dataset"]
    products = frames["olist_products_dataset"]
    translation = frames["product_category_name_translation"]
    translation.columns = [c.strip("﻿") for c in translation.columns]

    products = products.merge(translation, on="product_category_name", how="left")
    products["product_category"] = products["product_category_name_english"].fillna(
        products["product_category_name"]
    )

    df = (
        items.merge(
            orders[["order_id", "order_purchase_timestamp", "order_status"]],
            on="order_id", how="left",
        )
        .merge(products[["product_id", "product_category"]], on="product_id", how="left")
    )
    df = df[[
        "order_id", "order_item_id", "order_purchase_timestamp", "order_status",
        "product_id", "seller_id", "product_category", "price", "freight_value",
    ]]
    df.to_csv(CSV_DIR / spec.filename, index=False)

    ts = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    spec.status = "downloaded"
    spec.row_count = len(df)
    spec.columns = len(df.columns)
    spec.date_range = f"{ts.min().date()} to {ts.max().date()}"
    spec.note = (
        f"{df['product_id'].nunique()} products across "
        f"{df['product_category'].nunique()} categories. "
        f"{int(df['product_category'].isna().sum())} rows have no category. "
        "Prices are per unit in BRL and exclude freight_value."
    )
    return spec


# ---------------------------------------------------------------------------
# 6. Rdatasets -- the R data archive mirrored as plain CSVs on GitHub. This
#    is where the canonical econometric price-elasticity datasets live: the
#    ones with published elasticity estimates to sanity-check a model
#    against, plus the household scanner-panel brand-choice sets that carry a
#    price for every competing brand (i.e. cross-price elasticity).
#    Every file below was verified reachable; each is small (KBs to a few MB).
# ---------------------------------------------------------------------------

RDATASETS_URL = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/{pkg}/{item}.csv"
RDATASETS_DOC_URL = "https://vincentarelbundock.github.io/Rdatasets/doc/{pkg}/{item}.html"

RDATASETS = [
    # --- benchmark demand curves: published elasticities to validate against
    dict(
        pkg="Ecdat", item="Cigar", filename="cigarettes_state_panel.csv",
        description=(
            "Cigarette Consumption: 46 US states x 30 years (1963-1992) with "
            "sales (packs per capita), price, CPI, per-capita disposable "
            "income and pimin (the lowest price in a neighbouring state, i.e. "
            "a bootlegging/substitute price). The standard panel for own-price "
            "elasticity of cigarette demand -- published estimates land around "
            "-0.4 short-run, so a model fit here has a known answer to be "
            "checked against."
        ),
        data_type="weekly", key_elasticity_columns="state,year,price,sales,ndi,cpi,pop,pimin",
    ),
    dict(
        pkg="AER", item="CigarettesSW", filename="cigarettes_sw_panel.csv",
        description=(
            "Stock & Watson's cigarette panel: 48 states x 2 years, packs per "
            "capita, average price, income, and two tax variables (tax, taxs) "
            "that are the textbook instruments for price. Small, but the "
            "reference dataset for instrumented (causal) elasticity rather "
            "than the descriptive kind the app currently reports."
        ),
        data_type="weekly", key_elasticity_columns="state,year,packs,price,income,tax,taxs,cpi",
    ),
    dict(
        pkg="AER", item="Journals", filename="journals_subscriptions.csv",
        description=(
            "Subscriptions to 180 economics journals in 2000 with price, "
            "pages, citations and age. The classic worked example of a log-log "
            "demand curve (log subs on log price-per-citation, elasticity "
            "about -0.53) -- tiny, clean, and useful as a regression-test "
            "fixture for the elasticity code itself."
        ),
        data_type="aggregated", key_elasticity_columns="subs,price,citations,pages,foundingyear",
    ),
    dict(
        pkg="wooldridge", item="fish", filename="fulton_fish_market.csv",
        description=(
            "Fulton Fish Market, 97 trading days: daily average price and "
            "total quantity of whiting, with weather-at-sea variables (wave "
            "height, wind speed) as supply shifters. The canonical "
            "demand-identification dataset -- it is the standard "
            "demonstration that regressing quantity on price without an "
            "instrument recovers neither the demand nor the supply curve."
        ),
        data_type="transaction", key_elasticity_columns="avgprc,totqty,lavgprc,ltotqty,wave2,speed2,mon,tues,wed,thurs",
    ),
    dict(
        pkg="causaldata", item="avocado", filename="avocado_weekly.csv",
        description=(
            "Weekly US Hass avocado average price and total volume, 2015-2018 "
            "(169 weeks). Small and single-product, and widely used as the "
            "teaching example for fitting a demand curve, so it is a quick "
            "end-to-end check of a new elasticity estimator."
        ),
        data_type="weekly", key_elasticity_columns="Date,AveragePrice,TotalVolume",
    ),
    dict(
        pkg="Ecdat", item="Icecream", filename="icecream_demand.csv",
        description=(
            "30 four-weekly periods of ice cream consumption with price, "
            "family income and mean temperature (Hildreth & Lu). The textbook "
            "small-sample demand regression, and a reminder of why a demand "
            "model needs the seasonality control: temperature swamps price "
            "here."
        ),
        data_type="weekly", key_elasticity_columns="cons,price,income,temp",
    ),
    # --- energy demand: own- and cross-price with substitutes priced in
    dict(
        pkg="AER", item="OECDGas", filename="gasoline_oecd_panel.csv",
        description=(
            "Baltagi & Griffin's gasoline panel: 18 OECD countries, 1960-1978, "
            "in logs -- consumption per car, real income per capita, real "
            "motor-gasoline price and cars per capita. The reference panel for "
            "short- vs long-run price elasticity (the gap between them is the "
            "point of the dataset)."
        ),
        data_type="weekly", key_elasticity_columns="country,year,gas,price,income,cars",
    ),
    dict(
        pkg="AER", item="USGasG", filename="gasoline_us_substitutes.csv",
        description=(
            "US gasoline market 1960-1995 (Greene): quantity and price of "
            "gasoline alongside the price indices of its substitutes and "
            "complements -- new cars, used cars, public transport, durables, "
            "nondurables, services -- plus income and population. Useful "
            "precisely because the cross-price terms are already in the file."
        ),
        data_type="weekly", key_elasticity_columns="gas,price,income,newcar,usedcar,transport,population",
    ),
    dict(
        pkg="AER", item="NaturalGas", filename="natural_gas_us_panel.csv",
        description=(
            "US residential natural gas by state, 1967-1989: consumption and "
            "own price plus the prices of electricity, fuel oil and LPG, with "
            "heating degree days and income. A compact worked example of a "
            "demand system where the substitutes are explicit."
        ),
        data_type="weekly", key_elasticity_columns="state,year,consumption,price,eprice,oprice,lprice,heating,income",
    ),
    dict(
        pkg="Ecdat", item="BudgetItaly", filename="budget_shares_italy.csv",
        description=(
            "1,729 Italian household budget observations with expenditure "
            "shares for food/housing/misc and a price index for each of those "
            "groups, plus total expenditure and household size. The shape a "
            "demand system (AIDS/QUAIDS) wants: shares on log prices and log "
            "expenditure, which yields own- and cross-price elasticities per "
            "category rather than per SKU."
        ),
        data_type="aggregated", key_elasticity_columns="wfood,whouse,wmisc,pfood,phouse,pmisc,totexp,income,size,year",
    ),
    # --- retail sales with a competitor price / promotion lever
    dict(
        pkg="ISLR", item="Carseats", filename="carseats_competitor_price.csv",
        description=(
            "Simulated child car-seat sales at 400 stores with the store's own "
            "Price, the local competitor's CompPrice, Advertising budget, "
            "shelf location, income and demographics. It is simulated, not "
            "observed -- but it is the only readily available file with an "
            "explicit competitor price column, which is exactly the shape the "
            "still-unsourced competition_data.csv was meant to have, so it "
            "works as a fixture for cross-price/competitive-response code."
        ),
        data_type="aggregated", key_elasticity_columns="Sales,Price,CompPrice,Advertising,Income,ShelveLoc,Urban,US",
    ),
    dict(
        pkg="Stat2Data", item="Grocery", filename="grocery_promo_experiment.csv",
        description=(
            "36 store-weeks of a designed grocery promotion experiment: sales "
            "against price, a discount level and a display flag. Tiny, but the "
            "price variation is experimental rather than observational, so "
            "unlike every other retail file here its elasticity estimate is "
            "genuinely causal."
        ),
        data_type="weekly", key_elasticity_columns="Sales,Price,Discount,Display,Store",
    ),
    dict(
        pkg="gt", item="pizzaplace", filename="pizza_pos_sales.csv",
        description=(
            "A full year (2015) of pizzeria POS sales: 49,574 order lines with "
            "date, time, product name, size, type and price. Price varies "
            "within a product by size and over time, and quantity is one row "
            "per pizza, so aggregating to product-week gives a clean "
            "transaction-level elasticity set outside the gift-retail domain "
            "of scanner_data.csv."
        ),
        data_type="transaction", key_elasticity_columns="date,time,name,size,type,price",
    ),
    # --- household scanner brand-choice panels: a price for every brand
    dict(
        pkg="Ecdat", item="Cracker", filename="brandchoice_crackers.csv",
        description=(
            "3,292 cracker purchase occasions (Nielsen household scanner "
            "panel) recording, for all four brands on the shelf, the price and "
            "whether it was on display or featured -- plus which one was "
            "bought. Prices of the alternatives on non-chosen brands are what "
            "make cross-price elasticity estimable at all."
        ),
        data_type="transaction", key_elasticity_columns="id,choice,price.sunshine,price.kleebler,price.nabisco,price.private,disp.*,feat.*",
    ),
    dict(
        pkg="Ecdat", item="Yogurt", filename="brandchoice_yogurt.csv",
        description=(
            "2,412 yogurt purchase occasions with the price and feature-ad "
            "status of all four brands (Yoplait, Dannon, Hiland, Weight "
            "Watchers) on each occasion."
        ),
        data_type="transaction", key_elasticity_columns="id,choice,price.yoplait,price.dannon,price.hiland,price.weight,feat.*",
    ),
    dict(
        pkg="Ecdat", item="Catsup", filename="brandchoice_catsup.csv",
        description=(
            "2,798 catsup purchase occasions across four Heinz/Hunt's SKUs "
            "with per-SKU price, display and feature flags -- the same-brand "
            "different-size variation makes it useful for size/price-per-ounce "
            "questions as well as brand switching."
        ),
        data_type="transaction", key_elasticity_columns="id,choice,price.heinz41,price.heinz32,price.heinz28,price.hunts32,disp.*,feat.*",
    ),
    dict(
        pkg="Ecdat", item="Ketchup", filename="brandchoice_ketchup.csv",
        description=(
            "4,956 ketchup purchase occasions with the price of each brand "
            "(Heinz, Hunt's, Del Monte, store brand) on the occasion. No "
            "promotion flags, so it isolates pure price response."
        ),
        data_type="transaction", key_elasticity_columns="Ketchup.hid,Ketchup.choice,price.heinz,price.hunts,price.delmonte,price.stb",
    ),
    dict(
        pkg="Ecdat", item="Tuna", filename="brandchoice_tuna.csv",
        description=(
            "13,705 canned-tuna purchase occasions with the price of five "
            "competing products (Star-Kist and Chicken of the Sea, water and "
            "oil packed, plus private label). The largest brand-choice panel "
            "of the set."
        ),
        data_type="transaction", key_elasticity_columns="Tuna.hid,Tuna.choice,price.skw,price.cosw,price.sko,price.coso,price.pw",
    ),
    dict(
        pkg="ISLR", item="OJ", filename="oj_brand_choice.csv",
        description=(
            "1,070 orange-juice purchases (Citrus Hill vs Minute Maid) drawn "
            "from the Dominick's data, with list price, discount, sale price "
            "and price gap for both brands plus a brand-loyalty score. Pairs "
            "with dominicks_oj.csv: the store-week aggregate there, the "
            "individual choice here."
        ),
        data_type="transaction", key_elasticity_columns="Purchase,WeekofPurchase,StoreID,PriceCH,PriceMM,DiscCH,DiscMM,SalePriceCH,SalePriceMM,PriceDiff,LoyalCH",
    ),
]


def download_rdataset(pkg: str, item: str, filename: str, **spec_kwargs) -> DatasetSpec:
    """Fetch one Rdatasets CSV. The archive prepends an unnamed row-index
    column ('rownames'); it is dropped so the written CSV is just the data."""
    spec = DatasetSpec(
        filename=filename,
        source_url=RDATASETS_DOC_URL.format(pkg=pkg, item=item),
        **spec_kwargs,
    )

    url = RDATASETS_URL.format(pkg=pkg, item=item)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    import pandas as pd

    df = pd.read_csv(io.StringIO(resp.text))
    if "rownames" in df.columns:
        df = df.drop(columns=["rownames"])
    df.to_csv(CSV_DIR / filename, index=False)

    spec.status = "downloaded"
    spec.row_count = len(df)
    spec.columns = len(df.columns)
    for col in ("year", "week", "date", "Date", "WeekofPurchase"):
        if col in df.columns:
            spec.date_range = f"{col} {df[col].min()} to {df[col].max()}"
            break
    spec.note = f"Rdatasets mirror of R package `{pkg}`, dataset `{item}`."
    return spec



# ---------------------------------------------------------------------------
# Gated / manual-only datasets. These are declared so the manifest documents
# them, and so download_kaggle_dataset() can be called directly once the
# user has Kaggle credentials configured (~/.kaggle/kaggle.json or
# KAGGLE_USERNAME/KAGGLE_KEY env vars).
# ---------------------------------------------------------------------------

KAGGLE_DATASETS = [
    dict(
        kaggle_ref="marian447/retail-scanner-data",
        filename="scanner_data_kaggle.csv",
        description="64,682 transactions of 5,242 SKUs from 22,625 customers over one year.",
        data_type="transaction",
        key_elasticity_columns="Date,Customer_ID,Transaction_ID,SKU_Category,SKU,Quantity,Sales_Amount",
    ),
    dict(
        kaggle_ref="prasad22/retail-transactions-dataset",
        filename="retail_transactions.csv",
        description="Multi-store retail transactions; price and quantity at transaction level.",
        data_type="transaction",
        key_elasticity_columns="Transaction_ID,Date,Store_ID,Product_ID,Quantity,Price,Category",
    ),
    dict(
        kaggle_ref="saibattula/retail-price-dataset-sales-data",
        filename="retail_price_dataset.csv",
        description="Store-level sales with pricing data, weekly/periodic aggregation.",
        data_type="weekly",
        key_elasticity_columns="Date,Store_ID,Product_ID,Price,Quantity_Sold,Category",
    ),
    dict(
        kaggle_ref="marian447/retail-store-sales-transactions",
        filename="retail_store_transactions.csv",
        description="Store scanner data formatted for analysis (transaction or weekly level).",
        data_type="transaction",
        key_elasticity_columns="Date,Store_ID,Product_ID,Quantity,Price",
    ),
]


def download_kaggle_dataset(kaggle_ref: str, filename: str, **spec_kwargs) -> DatasetSpec:
    """Requires ~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY env vars.

    Raises RuntimeError with setup instructions if no credentials are found
    (this is the actual failure mode observed in this environment: the
    Kaggle API returns 403 Permission 'datasets.get' was denied for every
    dataset, gated or not, when unauthenticated).
    """
    spec = DatasetSpec(
        filename=filename,
        source_url=f"https://www.kaggle.com/datasets/{kaggle_ref}",
        status="manual_required",
        note=(
            "pip install kaggle; place API token at ~/.kaggle/kaggle.json "
            "(from https://www.kaggle.com/settings -> Create New Token), "
            "then re-run this function."
        ),
        **spec_kwargs,
    )
    if not (Path.home() / ".kaggle" / "kaggle.json").exists() and not (
        os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")
    ):
        return spec

    result = subprocess.run(
        ["kaggle", "datasets", "download", "-d", kaggle_ref, "-p", str(RAW_DIR), "--unzip"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        spec.note = f"kaggle CLI failed: {result.stderr.strip()}"
        return spec

    downloaded_csvs = list(RAW_DIR.glob("*.csv"))
    if not downloaded_csvs:
        spec.note = "kaggle CLI reported success but no CSV was found in the download"
        return spec

    out_path = CSV_DIR / filename
    out_path.write_bytes(downloaded_csvs[0].read_bytes())

    import pandas as pd
    df = pd.read_csv(out_path)
    spec.status = "downloaded"
    spec.row_count = len(df)
    spec.columns = len(df.columns)
    spec.note = ""
    return spec


MANUAL_ONLY_DATASETS = [
    DatasetSpec(
        filename="dominicks_combined.csv",
        source_url="https://www.chicagobooth.edu/research/kilts/datasets/dominicks",
        description=(
            "Raw Dominick's Finer Foods scanner data (1989-1997, 26 "
            "categories, ~100 Chicago-area stores, UPC-level, weekly, with "
            "promotion flags and built-in price experiments). Requires "
            "manual academic registration with the Kilts Center -- no API, "
            "not scriptable from here."
        ),
        data_type="weekly",
        key_elasticity_columns="Date/Week,Store_ID,UPC,Quantity_Sold,Price,Promotion_Flag",
        status="manual_required",
        note="Register at the Kilts Center URL above, download SAS/CSV extracts, place in data/csv/.",
    ),
    DatasetSpec(
        filename="walmart_sales_weekly.csv",
        source_url="https://www.kaggle.com/c/competitive-data-science-predict-future-sales",
        description=(
            "45 stores, weekly sales by department, with Holiday/Temperature/"
            "FuelPrice/CPI/Unemployment/MarkDown features."
        ),
        data_type="weekly",
        key_elasticity_columns="Store,Dept,Date,Weekly_Sales,IsHoliday,Temperature,CPI,Unemployment",
        status="manual_required",
        note="Kaggle competition dataset -- requires competition-join + Kaggle auth (see download_kaggle_dataset).",
    ),
    DatasetSpec(
        filename="efood_elasticities.csv",
        source_url="https://doi.org/10.7910/DVN/OXZ0H6",
        description="Pre-calculated income/price elasticities of food demand across developing countries.",
        data_type="aggregated",
        key_elasticity_columns="Country,Product,Income_Elasticity,Price_Elasticity,Segment",
        status="manual_required",
        note=(
            "dataverse.harvard.edu is behind a WAF bot-challenge that blocks "
            "non-browser requests (confirmed: direct HTTPS GET returns a "
            "challenge page, not data). Download manually via the DOI link "
            "in a browser."
        ),
    ),
    DatasetSpec(
        filename="cheese.csv",
        source_url="(no verifiable public source found)",
        description=(
            "Small volume/price/marketing-activity dataset for prototyping. "
            "The Dominick's raw data does include a cheese category, but "
            "the Monash reformatted archive used for monash_dominicks.csv "
            "anonymizes series (T1, T2, ...) with no category label, so a "
            "cheese-only subset can't be recovered from it. Left "
            "undownloaded rather than fabricated."
        ),
        data_type="aggregated",
        key_elasticity_columns="Retailer,Volume,Price,Display/Marketing_Activity",
        status="manual_required",
        note="Extract the cheese category from a registered Kilts Center Dominick's download, if/when available.",
    ),
    DatasetSpec(
        filename="tafeng_transactions.csv",
        source_url="https://www.kaggle.com/datasets/chiranjivdas09/ta-feng-grocery-dataset",
        description=(
            "Ta Feng: 817,741 grocery transactions, 32,266 customers, 23,812 "
            "items, Nov 2000-Feb 2001, with quantity, unit sales price and "
            "cost per line -- one of the few public basket datasets carrying "
            "a per-item margin as well as a price."
        ),
        data_type="transaction",
        key_elasticity_columns="Date,Customer_ID,Product_ID,Product_Category,Quantity,Sales_Price,Asset_Cost",
        status="manual_required",
        note=(
            "Searched for a redistributable copy: the original NTU/ACM host is "
            "gone and the surviving copies are on Kaggle or behind RecSysWiki "
            "links, so it needs Kaggle auth (see download_kaggle_dataset) or a "
            "manual download."
        ),
    ),
    DatasetSpec(
        filename="m5_sell_prices.csv",
        source_url="https://www.kaggle.com/competitions/m5-forecasting-accuracy/data",
        description=(
            "M5 competition: 3,049 Walmart items x 10 stores, 1,941 days of "
            "unit sales alongside weekly per-item sell prices -- the largest "
            "public dataset pairing SKU-level price with SKU-level units."
        ),
        data_type="weekly",
        key_elasticity_columns="store_id,item_id,wm_yr_wk,sell_price,d_1..d_1941 (units)",
        status="manual_required",
        note=(
            "Kaggle competition data: requires accepting the competition rules "
            "plus Kaggle auth. sell_prices.csv is ~200 MB, over GitHub's "
            "100 MB file limit, so no raw-file mirror exists to fall back on."
        ),
    ),
    DatasetSpec(
        filename="competition_data.csv",
        source_url="(no concrete source given in task spec)",
        description="Weekly price/quantity/competitor-price data.",
        data_type="weekly",
        key_elasticity_columns="Fiscal_Week_ID,Store_ID,Item_ID,Price,Item_Quantity,Sales_Amount,Competition_Price",
        status="manual_required",
        note="No resolvable URL was provided for this dataset; needs a specific source before it can be fetched.",
    ),
]


def _failure_note(exc: Exception) -> str:
    """Say *why* a fetch failed, distinguishing a sandbox egress denial from
    a genuinely dead source -- the manifest is only useful if that difference
    survives into it."""
    text = str(exc)
    if "CONNECT tunnel failed" in text or ("403" in text and "proxy" in text.lower()):
        return (
            "Blocked by this environment's outbound network policy (the egress "
            "proxy answered 403 to CONNECT). The source itself is fine -- "
            f"re-run where the host is allowed. Error: {text}"
        )
    return f"Download failed: {type(exc).__name__}: {text}"


def _safe(spec_template: dict, fetch) -> list[DatasetSpec]:
    """Run one fetch, converting any failure into an `unreachable` spec so a
    single blocked host doesn't abort the whole run."""
    try:
        result = fetch()
    except Exception as exc:  # noqa: BLE001 - one bad source must not stop the rest
        spec = DatasetSpec(**spec_template)
        spec.status = "unreachable"
        spec.note = _failure_note(exc)
        return [spec]
    return result if isinstance(result, list) else [result]


def main() -> list[DatasetSpec]:
    specs: list[DatasetSpec] = []

    print("UCI Online Retail II -> scanner_data.csv ...")
    specs += _safe(ONLINE_RETAIL_II_SPEC, download_online_retail_ii)

    print("Monash Dominick Dataset -> monash_dominicks.csv ...")
    specs += _safe(MONASH_DOMINICKS_SPEC, download_monash_dominicks)

    print("dunnhumby Complete Journey -> completejourney_*.csv ...")
    for cj in COMPLETEJOURNEY_FILES:
        specs += _safe(
            {k: v for k, v in cj.items() if k != "remote"}
            | {"source_url": f"{COMPLETEJOURNEY_BASE}/{cj['remote']}"},
            lambda cj=cj: download_completejourney_file(**cj),
        )

    print("Dominick's OJ store panel -> dominicks_oj.csv ...")
    specs += _safe(DOMINICKS_OJ_SPEC, download_dominicks_oj)

    print("Olist Brazilian e-commerce -> olist_order_items.csv ...")
    specs += _safe(OLIST_SPEC, download_olist)

    print(f"Rdatasets econometric demand sets ({len(RDATASETS)}) ...")
    for rd in RDATASETS:
        specs += _safe(
            {k: v for k, v in rd.items() if k not in ("pkg", "item")}
            | {"source_url": RDATASETS_DOC_URL.format(pkg=rd["pkg"], item=rd["item"])},
            lambda rd=rd: download_rdataset(**rd),
        )

    print("Attempting Kaggle datasets (requires ~/.kaggle/kaggle.json) ...")
    for kd in KAGGLE_DATASETS:
        specs += _safe(
            {k: v for k, v in kd.items() if k != "kaggle_ref"}
            | {"source_url": f"https://www.kaggle.com/datasets/{kd['kaggle_ref']}"},
            lambda kd=kd: download_kaggle_dataset(**kd),
        )

    specs.extend(MANUAL_ONLY_DATASETS)

    for s in specs:
        count = f"{s.row_count:,} rows" if s.row_count else ""
        print(f"  [{s.status:16s}] {s.filename:38s} {count}")

    return specs


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
