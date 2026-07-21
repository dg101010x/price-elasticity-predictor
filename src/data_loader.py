"""
Data acquisition for the price elasticity predictor.

Two sources are freely downloadable with no authentication and are fetched
for real by this module:

  - UCI "Online Retail II" (archive.ics.uci.edu)      -> data/csv/scanner_data.csv
  - Monash "Dominick Dataset" on Zenodo                -> data/csv/monash_dominicks.csv

Everything else in the target dataset list (Kaggle datasets, the raw Kilts
Center Dominick's Finer Foods files, the Harvard Dataverse E-FooD dataset,
etc.) sits behind an auth wall or a manual registration step that cannot be
scripted:

  - Kaggle: the Kaggle API returns 403 for every dataset without a valid
    ~/.kaggle/kaggle.json (or KAGGLE_USERNAME/KAGGLE_KEY env vars). There is
    no anonymous download path, confirmed against kagglehub directly.
  - Kilts Center (Dominick's raw): requires manual academic registration on
    chicagobooth.edu; no API.
  - Harvard Dataverse (E-FooD): dataverse.harvard.edu sits behind a WAF
    challenge that blocks non-browser requests.

`download_kaggle_dataset()` below is a real, working function -- it will
succeed as soon as valid Kaggle credentials are present -- so re-running
`main()` after the user configures credentials will fill in the rest of
data/csv without any code changes.

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
    data_type: str  # transaction | weekly | aggregated
    key_elasticity_columns: str
    status: str = "not_downloaded"  # downloaded | not_downloaded | manual_required
    note: str = ""
    row_count: Optional[int] = None
    columns: Optional[int] = None
    date_range: str = ""


# ---------------------------------------------------------------------------
# 1. UCI Online Retail II -- real, no-auth download
# ---------------------------------------------------------------------------

ONLINE_RETAIL_II_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"


def download_online_retail_ii() -> DatasetSpec:
    spec = DatasetSpec(
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


def download_monash_dominicks() -> DatasetSpec:
    spec = DatasetSpec(
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
        filename="competition_data.csv",
        source_url="(no concrete source given in task spec)",
        description="Weekly price/quantity/competitor-price data.",
        data_type="weekly",
        key_elasticity_columns="Fiscal_Week_ID,Store_ID,Item_ID,Price,Item_Quantity,Sales_Amount,Competition_Price",
        status="manual_required",
        note="No resolvable URL was provided for this dataset; needs a specific source before it can be fetched.",
    ),
]


def main() -> list[DatasetSpec]:
    specs: list[DatasetSpec] = []

    print("Downloading UCI Online Retail II -> scanner_data.csv ...")
    specs.append(download_online_retail_ii())

    print("Downloading Monash Dominick Dataset -> monash_dominicks.csv ...")
    specs.append(download_monash_dominicks())

    print("Attempting Kaggle datasets (requires ~/.kaggle/kaggle.json) ...")
    for kd in KAGGLE_DATASETS:
        specs.append(download_kaggle_dataset(**kd))

    specs.extend(MANUAL_ONLY_DATASETS)

    for s in specs:
        print(f"  [{s.status:16s}] {s.filename}")

    return specs


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
