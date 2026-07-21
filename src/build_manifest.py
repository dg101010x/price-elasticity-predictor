"""
Profiles data/csv/*.csv and (re)writes:
  - data/manifests/data_manifest.csv
  - data/manifests/validation_report.txt

Run after src/data_loader.py: python -m src.build_manifest
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .data_loader import CSV_DIR, MANIFEST_DIR, KAGGLE_DATASETS, MANUAL_ONLY_DATASETS, DatasetSpec

MANIFEST_PATH = MANIFEST_DIR / "data_manifest.csv"
REPORT_PATH = MANIFEST_DIR / "validation_report.txt"

MANIFEST_FIELDS = [
    "filename", "source_url", "description", "row_count", "columns",
    "date_range", "data_type", "key_elasticity_columns", "status", "note",
]


def profile_scanner_data() -> DatasetSpec:
    path = CSV_DIR / "scanner_data.csv"
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


def build() -> list[DatasetSpec]:
    specs = [profile_scanner_data(), profile_monash_dominicks()]

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
    manual = [s for s in specs if s.status == "manual_required"]

    lines.append(f"Downloaded and profiled: {len(downloaded)}")
    lines.append(f"Requires manual action: {len(manual)}")
    lines.append("")

    for s in downloaded:
        lines += [
            f"--- {s.filename} ---",
            f"source: {s.source_url}",
            f"rows: {s.row_count:,}   columns: {s.columns}",
            f"date_range: {s.date_range}",
            f"data_type: {s.data_type}",
            f"key_elasticity_columns: {s.key_elasticity_columns}",
            f"notes: {s.note}",
            "",
        ]

    lines.append("REQUIRES MANUAL ACTION")
    lines.append("-" * 60)
    for s in manual:
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
