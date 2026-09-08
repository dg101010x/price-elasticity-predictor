"""
Profiles data/csv/*.csv and (re)writes:
  - data/manifests/data_manifest.csv
  - data/manifests/validation_report.txt

Covers three groups: the two originally-scoped datasets that can be fetched
without an account, the eight that are gated and stay undownloaded, and the
twelve reference markets added in 2.1 (see src/reference_data.py).

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
            description=f"{ref.label} — {ref.market}. Source: {ref.source}.",
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
