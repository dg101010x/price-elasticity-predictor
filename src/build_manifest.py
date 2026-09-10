"""
Profiles data/csv/*.csv and (re)writes:
  - data/manifests/data_manifest.csv
  - data/manifests/validation_report.txt

Covers four groups: the originally-scoped datasets that can be fetched
without an account, the ones that are gated and stay undownloaded, the M5
Walmart release (see src/walmart_data.py), and the twelve reference markets
(see src/reference_data.py).

A dataset that has been profiled before but is not on disk now keeps the
figures already recorded in the manifest, marked `previously_profiled`,
rather than either crashing the build or silently reporting zero. That case
is real: this project's own CI runs behind an egress policy that reaches
GitHub but not archive.ics.uci.edu or zenodo.org, so a checkout there can
rebuild the reference roster but not the two originals.

Run after src/data_loader.py: python -m src.build_manifest
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .data_loader import CSV_DIR, MANIFEST_DIR, KAGGLE_DATASETS, MANUAL_ONLY_DATASETS, DatasetSpec
from .reference_data import REFERENCE_DATASETS, REFERENCE_DIR
from .walmart_data import CANONICAL_SOURCE, MIRROR_REPO, WALMART_DIR

MANIFEST_PATH = MANIFEST_DIR / "data_manifest.csv"
REPORT_PATH = MANIFEST_DIR / "validation_report.txt"

MANIFEST_FIELDS = [
    "filename", "source_url", "description", "row_count", "columns",
    "date_range", "data_type", "key_elasticity_columns", "status", "note",
]

CARRIED_MARKER = ("Figures carried forward from an earlier run; the file is not in "
                  "data/csv/ right now.")

REFETCH_NOTE = {
    "scanner_data.csv": "Re-fetch with `python -m src.data_loader` from a network that can reach archive.ics.uci.edu.",
    "monash_dominicks.csv": "Re-fetch with `python -m src.data_loader` from a network that can reach zenodo.org.",
    "usda_elasticities.csv": "Re-fetch with `python -m src.data_loader` from a network that can reach ers.usda.gov.",
    "fish_prices.csv": "Re-fetch with `python -m src.data_loader` after `pip install wooldridge`.",
    "smoking_prices.csv": "Re-fetch with `python -m src.data_loader` after `pip install wooldridge`.",
}


def _previously_recorded() -> dict[str, dict]:
    """What the last successful profiling run wrote, keyed by filename."""
    if not MANIFEST_PATH.exists():
        return {}
    with open(MANIFEST_PATH, newline="") as f:
        return {row["filename"]: row for row in csv.DictReader(f)}


def _carry_forward(filename: str, fallback: DatasetSpec) -> DatasetSpec:
    """Preserve a previous profile of a file that isn't on disk right now."""
    recorded = _previously_recorded().get(filename)
    if not recorded:
        fallback.status = "not_downloaded"
        fallback.note = REFETCH_NOTE.get(filename, "Not present locally; re-run src/data_loader.py.")
        return fallback

    fallback.row_count = int(recorded["row_count"]) if recorded["row_count"] else None
    fallback.columns = int(recorded["columns"]) if recorded["columns"] else None
    fallback.date_range = recorded["date_range"]
    fallback.status = "previously_profiled"
    # Rebuilds are idempotent: strip any carry-forward text this function
    # appended on a previous run before appending it again.
    original = recorded["note"].split(CARRIED_MARKER)[0].strip()
    fallback.note = " ".join(filter(None, [
        original, CARRIED_MARKER, REFETCH_NOTE.get(filename, ""),
    ]))
    return fallback


def profile_scanner_data() -> DatasetSpec:
    path = CSV_DIR / "scanner_data.csv"
    if not path.exists():
        return _carry_forward("scanner_data.csv", DatasetSpec(
            filename="scanner_data.csv",
            source_url="https://archive.ics.uci.edu/dataset/502/online+retail+ii",
            description="UK online retailer transactions, Dec 2009-Dec 2011.",
            data_type="transaction",
            key_elasticity_columns="InvoiceDate,Quantity,Price,StockCode,Customer ID",
        ))
    df = pd.read_csv(path, parse_dates=["InvoiceDate"])
    return DatasetSpec(
        filename="scanner_data.csv",
        source_url="https://archive.ics.uci.edu/dataset/502/online+retail+ii",
        description=(
            "UK online retailer transactions, Dec 2009-Dec 2011. Substituted "
            "for the gated Kaggle 'retail-scanner-data' notebook dataset "
            "(marian447), which itself appears to derive from this same UCI "
            "source (5,305 SKUs here vs. the Kaggle listing's stated "
            "5,242). Transaction-level, real invoice/quantity/price/customer "
            "data -- suitable directly for log-log elasticity regression."
        ),
        row_count=len(df),
        columns=len(df.columns),
        date_range=f"{df['InvoiceDate'].min().date()} to {df['InvoiceDate'].max().date()}",
        data_type="transaction",
        key_elasticity_columns="InvoiceDate,Quantity,Price,StockCode,Customer ID",
        status="downloaded",
        note=(
            f"{df['StockCode'].nunique()} unique SKUs, {df['Customer ID'].nunique()} "
            f"unique customers, {df['Country'].nunique()} countries. "
            f"{int((df['Price'] <= 0).sum())} rows with Price<=0 and "
            f"{int((df['Quantity'] < 0).sum())} rows with negative Quantity "
            "(returns) -- filter both before fitting elasticity."
        ),
    )


def profile_monash_dominicks() -> DatasetSpec:
    path = CSV_DIR / "monash_dominicks.csv"
    if not path.exists():
        return _carry_forward("monash_dominicks.csv", DatasetSpec(
            filename="monash_dominicks.csv",
            source_url="https://zenodo.org/records/4654802",
            description="Monash Time Series Forecasting Archive's 'Dominick Dataset'.",
            data_type="weekly",
            key_elasticity_columns="SKU_ID,Week_Index,Weekly_Profit",
        ))
    df = pd.read_csv(
        path,
        dtype={"SKU_ID": "category", "Week_Index": "int32", "Weekly_Profit": "float32"},
    )
    return DatasetSpec(
        filename="monash_dominicks.csv",
        source_url="https://zenodo.org/records/4654802",
        description=(
            "Monash Time Series Forecasting Archive's 'Dominick Dataset': "
            "weekly per-SKU profit, reformatted from Kilts Center Dominick's "
            "Finer Foods scanner data. No store ID, UPC, category label, or "
            "calendar date -- series are anonymized (T1..T115704) and "
            "'Week_Index' is a per-series relative index, not a date. Useful "
            "for time-series elasticity modeling, not for category-level "
            "breakdowns (see cheese.csv / dominicks_combined.csv, both "
            "manual_required)."
        ),
        row_count=len(df),
        columns=len(df.columns),
        date_range=f"relative week 0-{df['Week_Index'].max()} per series, no calendar dates",
        data_type="weekly",
        key_elasticity_columns="SKU_ID,Week_Index,Weekly_Profit",
        status="downloaded",
        note=(
            f"{df['SKU_ID'].nunique()} unique series. "
            f"{int((df['Weekly_Profit'] == 0).sum())} of {len(df)} rows are "
            "zero-profit weeks (no sale that week, not missing data)."
        ),
    )


def profile_reference_datasets() -> list[DatasetSpec]:
    """The twelve markets added in 2.1, profiled from data/csv/reference/."""
    specs = []
    for ref in REFERENCE_DATASETS:
        path = REFERENCE_DIR / ref.filename
        spec = DatasetSpec(
            filename=f"reference/{ref.filename}",
            source_url=ref.url,
            description=f"{ref.label}. {ref.market}. Source: {ref.source}.",
            data_type={"panel": "panel", "series": "weekly", "choice": "scanner-choice"}[ref.estimator],
            key_elasticity_columns=(
                ",".join(filter(None, [ref.entity, ref.price, ref.quantity, ref.deflator]))
                if ref.estimator != "choice"
                else ",".join([ref.choice_column] + list(ref.brands.values()))
            ),
        )
        if not path.exists():
            spec.status = "not_downloaded"
            spec.note = "Re-fetch with `python -m src.reference_data`."
            specs.append(spec)
            continue

        df = pd.read_csv(path, low_memory=False)
        spec.status = "downloaded"
        spec.row_count = len(df)
        spec.columns = df.shape[1]
        spec.date_range = ref.market
        spec.note = ref.note or ""
        specs.append(spec)
    return specs


WALMART_FILES = [
    ("sales_train_evaluation.csv", "panel",
     "30,490 store-item series across 1,941 days: 59,181,090 daily unit-sales records.",
     "id,item_id,dept_id,cat_id,store_id,state_id,d_1..d_1941"),
    ("sell_prices.csv", "weekly",
     "6,841,121 weekly shelf prices, one per store, item and Walmart week.",
     "store_id,item_id,wm_yr_wk,sell_price"),
    ("calendar.csv", "reference",
     "1,969 days, 2011-01-29 to 2016-06-19, mapping each day to its Walmart week.",
     "date,wm_yr_wk,d,snap_CA,snap_TX,snap_WI"),
]


def profile_walmart() -> list[DatasetSpec]:
    """The M5 release: the second catalogue, five years more recent than the first."""
    specs = []
    for filename, data_type, description, columns in WALMART_FILES:
        path = WALMART_DIR / filename
        spec = DatasetSpec(
            filename=f"walmart/{filename}",
            source_url=CANONICAL_SOURCE,
            description=(
                f"M5 Forecasting Accuracy, M Open Forecasting Center. {description} "
                f"Real Walmart point-of-sale across 10 stores in CA, TX and WI, with the "
                f"retailer's own category hierarchy. Fetched from the public mirror "
                f"{MIRROR_REPO} and checked against the published M5 specification."
            ),
            data_type=data_type,
            key_elasticity_columns=columns,
        )
        if not path.exists():
            spec.status = "not_downloaded"
            spec.note = "Re-fetch with `python -m src.walmart_data`."
            specs.append(spec)
            continue
        with open(path) as f:
            rows = sum(1 for _ in f) - 1
        header = open(path).readline().rstrip("\n").split(",")
        spec.status = "downloaded"
        spec.row_count = rows
        spec.columns = len(header)
        spec.date_range = "2011-01-29 to 2016-06-19"
        spec.note = "Verified against the published M5 shape by src/walmart_data.py."
        specs.append(spec)
    return specs
def profile_usda_elasticities() -> DatasetSpec:
    path = CSV_DIR / "usda_elasticities.csv"
    if not path.exists():
        return _carry_forward("usda_elasticities.csv", DatasetSpec(
            filename="usda_elasticities.csv",
            source_url="https://www.ers.usda.gov/data-products/commodity-and-food-elasticities/documentation",
            description="USDA ERS compilation of published demand elasticity estimates.",
            data_type="aggregated",
            key_elasticity_columns="MAJOR_COMMODITY,GEOGRAPHY,ELASTICITY_INFO,AMOUNT,DATA_PERIOD",
        ))
    df = pd.read_csv(path)
    return DatasetSpec(
        filename="usda_elasticities.csv",
        source_url="https://www.ers.usda.gov/data-products/commodity-and-food-elasticities/documentation",
        description=(
            "USDA Economic Research Service compilation of own-price, "
            "cross-price, and income elasticity estimates drawn from "
            "published literature across 100+ countries/commodities. "
            "Pre-computed elasticities (not transaction data) -- useful as "
            "an external benchmark to sanity-check whatever the model fits "
            "from scanner_data.csv. Not updated since 2006."
        ),
        row_count=len(df),
        columns=len(df.columns),
        date_range="studies published through 2006, covering data periods back to the 1960s-90s",
        data_type="aggregated",
        key_elasticity_columns="MAJOR_COMMODITY,GEOGRAPHY,ELASTICITY_INFO,AMOUNT,DATA_PERIOD",
        status="downloaded",
        note=(
            f"{df['GEOGRAPHY'].nunique()} distinct geographies, "
            f"{df['MAJOR_COMMODITY'].nunique()} major commodities, "
            f"{df['ELASTICITY_INFO'].nunique()} elasticity types "
            "(own price/cross price/income/etc). One row per literature-"
            "reported estimate, not per commodity -- expect duplicates "
            "across studies."
        ),
    )


def profile_wooldridge_fish() -> DatasetSpec:
    path = CSV_DIR / "fish_prices.csv"
    if not path.exists():
        return _carry_forward("fish_prices.csv", DatasetSpec(
            filename="fish_prices.csv",
            source_url="https://pypi.org/project/wooldridge/ (dataset: fish, Graddy 1995)",
            description="Graddy (1995) Fulton Fish Market daily price and quantity.",
            data_type="aggregated",
            key_elasticity_columns="avgprc,totqty,prca,prcw,qtya,qtyw,wave2,speed2",
        ))
    df = pd.read_csv(path)
    return DatasetSpec(
        filename="fish_prices.csv",
        source_url="https://pypi.org/project/wooldridge/ (dataset: fish, Graddy 1995)",
        description=(
            "Graddy (1995) Fulton Fish Market daily price/quantity by buyer "
            "type (Asian vs. white wholesalers), 97 daily observations, "
            "with wave-height/wind-speed instruments for IV elasticity "
            "estimation -- a classic clean supply/demand identification "
            "dataset."
        ),
        row_count=len(df),
        columns=len(df.columns),
        date_range="",
        data_type="aggregated",
        key_elasticity_columns="avgprc,totqty,prca,prcw,qtya,qtyw,wave2,speed2",
        status="downloaded",
        note="97 daily market-level observations, no missing avgprc/totqty rows -- small enough for a demo/test fixture rather than primary modeling data.",
    )


def profile_wooldridge_smoke() -> DatasetSpec:
    path = CSV_DIR / "smoking_prices.csv"
    if not path.exists():
        return _carry_forward("smoking_prices.csv", DatasetSpec(
            filename="smoking_prices.csv",
            source_url="https://pypi.org/project/wooldridge/ (dataset: smoke, Mullahy 1997)",
            description="Mullahy (1997) cross-section of 807 individuals: cigarette price vs cigarettes per day.",
            data_type="aggregated",
            key_elasticity_columns="cigpric,cigs,income,educ,age,restaurn",
        ))
    df = pd.read_csv(path)
    return DatasetSpec(
        filename="smoking_prices.csv",
        source_url="https://pypi.org/project/wooldridge/ (dataset: smoke, Mullahy 1997)",
        description=(
            "Mullahy (1997) cross-section of 807 individuals: state "
            "cigarette price (cigpric, cents/pack) vs. cigarettes/day "
            "(cigs), with income/education/age/restaurant-smoking-ban "
            "controls -- a demand elasticity dataset at the individual "
            "level rather than SKU level."
        ),
        row_count=len(df),
        columns=len(df.columns),
        date_range="",
        data_type="aggregated",
        key_elasticity_columns="cigpric,cigs,income,educ,age,restaurn",
        status="downloaded",
        note=f"{int((df['cigs'] == 0).sum())} of {len(df)} respondents report zero cigarettes/day (non-smokers) -- consider a two-part/Tobit model rather than plain OLS.",
    )


def build() -> list[DatasetSpec]:
    specs = [
        profile_scanner_data(),
        profile_monash_dominicks(),
        profile_usda_elasticities(),
        profile_wooldridge_fish(),
        profile_wooldridge_smoke(),
    ]

    for kd in KAGGLE_DATASETS:
        specs.append(DatasetSpec(
            filename=kd["filename"],
            source_url=f"https://www.kaggle.com/datasets/{kd['kaggle_ref']}",
            description=kd["description"],
            data_type=kd["data_type"],
            key_elasticity_columns=kd["key_elasticity_columns"],
            status="manual_required",
            note="Kaggle API returned 403 (unauthenticated). Configure ~/.kaggle/kaggle.json, then run `python -m src.data_loader`.",
        ))

    specs.extend(MANUAL_ONLY_DATASETS)
    specs.extend(profile_walmart())
    specs.extend(profile_reference_datasets())

    with open(MANIFEST_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for s in specs:
            writer.writerow({
                "filename": s.filename,
                "source_url": s.source_url,
                "description": s.description,
                "row_count": s.row_count if s.row_count is not None else "",
                "columns": s.columns if s.columns is not None else "",
                "date_range": s.date_range,
                "data_type": s.data_type,
                "key_elasticity_columns": s.key_elasticity_columns,
                "status": s.status,
                "note": s.note,
            })

    return specs


def write_validation_report(specs: list[DatasetSpec]) -> None:
    lines = ["DATA VALIDATION REPORT", "=" * 60, ""]
    downloaded = [s for s in specs if s.status == "downloaded"]
    carried = [s for s in specs if s.status == "previously_profiled"]
    manual = [s for s in specs if s.status == "manual_required"]
    missing = [s for s in specs if s.status == "not_downloaded"]

    rows_on_disk = sum(s.row_count or 0 for s in downloaded)
    rows_recorded = rows_on_disk + sum(s.row_count or 0 for s in carried)

    lines.append(f"Present and profiled:    {len(downloaded)}  ({rows_on_disk:,} rows on disk)")
    if carried:
        lines.append(f"Profiled previously:     {len(carried)}  (figures carried forward)")
    lines.append(f"Requires manual action:  {len(manual)}")
    if missing:
        lines.append(f"Not fetched:             {len(missing)}")
    lines.append(f"Rows across every profiled dataset: {rows_recorded:,}")
    lines.append("")

    # keep the manifest's own order: the two originals, then the reference roster
    for s in [s for s in specs if s.status in ("downloaded", "previously_profiled")]:
        lines += [
            f"--- {s.filename} ---",
            f"source: {s.source_url}",
            f"rows: {s.row_count:,}   columns: {s.columns}" if s.row_count else "rows: not recorded",
            f"date_range: {s.date_range}",
            f"data_type: {s.data_type}",
            f"key_elasticity_columns: {s.key_elasticity_columns}",
            f"notes: {s.note}",
            "",
        ]

    lines.append("REQUIRES MANUAL ACTION")
    lines.append("-" * 60)
    for s in manual + missing:
        lines += [
            f"--- {s.filename} ---",
            f"source: {s.source_url}",
            f"why blocked: {s.note}",
            "",
        ]

    REPORT_PATH.write_text("\n".join(lines))


if __name__ == "__main__":
    specs = build()
    write_validation_report(specs)
    print(f"Wrote {MANIFEST_PATH}")
    print(f"Wrote {REPORT_PATH}")
