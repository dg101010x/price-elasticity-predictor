"""
Profiles data/csv/*.csv and (re)writes:
  - data/manifests/data_manifest.csv
  - data/manifests/validation_report.txt

Every dataset the loader knows about gets a row. A file that is present on
disk is profiled from the file itself; one that isn't keeps whatever the
previous manifest recorded for it (flagged as carried over) so regenerating
the manifest on a machine that couldn't reach a source doesn't quietly erase
what a machine that could reach it already measured.

Run after src/data_loader.py: python -m src.build_manifest
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .data_loader import (
    CSV_DIR,
    MANIFEST_DIR,
    COMPLETEJOURNEY_BASE,
    COMPLETEJOURNEY_FILES,
    DOMINICKS_OJ_SPEC,
    KAGGLE_DATASETS,
    MANUAL_ONLY_DATASETS,
    MONASH_DOMINICKS_SPEC,
    OLIST_SPEC,
    ONLINE_RETAIL_II_SPEC,
    RDATASETS,
    RDATASETS_DOC_URL,
    DatasetSpec,
)

MANIFEST_PATH = MANIFEST_DIR / "data_manifest.csv"
REPORT_PATH = MANIFEST_DIR / "validation_report.txt"

MANIFEST_FIELDS = [
    "filename", "source_url", "description", "row_count", "columns",
    "date_range", "data_type", "key_elasticity_columns", "status", "note",
]

# Columns worth reporting a range for, in priority order.
DATE_COLUMNS = [
    "InvoiceDate", "transaction_timestamp", "order_purchase_timestamp",
    "Date", "date", "year", "week", "Week_Index", "WeekofPurchase",
]


def _read_existing_manifest() -> dict[str, dict]:
    if not MANIFEST_PATH.exists():
        return {}
    with open(MANIFEST_PATH, newline="") as f:
        return {row["filename"]: row for row in csv.DictReader(f)}


def _carry_over(spec: DatasetSpec, previous: dict) -> DatasetSpec:
    """Reuse a previous run's profile for a file that isn't on this disk."""
    spec.row_count = int(previous["row_count"]) if previous["row_count"] else None
    spec.columns = int(previous["columns"]) if previous["columns"] else None
    spec.date_range = previous["date_range"]
    spec.status = previous["status"]
    old_note = previous["note"].split(" | carried over from", 1)[0]
    spec.note = (
        f"{old_note} | carried over from an earlier run: the file is not in "
        "data/csv on this machine, so these numbers were not re-measured."
    )
    return spec


def _pick_date_column(df: pd.DataFrame) -> str | None:
    for col in DATE_COLUMNS:
        if col in df.columns and df[col].notna().any():
            return col
    return None


def _chunk_range(chunk: pd.DataFrame, col: str):
    """(min, max, is_date) for one chunk of a candidate date/period column."""
    series = chunk[col].dropna()
    if series.empty:
        return None, None, False
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.min(), series.max(), True
    if not pd.api.types.is_numeric_dtype(series):
        # pandas 2 gives these columns dtype object, pandas 3 dtype str.
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        if parsed.notna().mean() > 0.9:
            parsed = parsed.dropna()
            return parsed.min(), parsed.max(), True
    return series.min(), series.max(), False


def _profile(spec: DatasetSpec, extra_note=None) -> DatasetSpec:
    """Profile data/csv/<spec.filename>, chunked so the multi-million-row
    files don't have to fit in memory twice. The date range is accumulated
    across every chunk, not read off the first one."""
    path = CSV_DIR / spec.filename
    rows = 0
    head = None
    date_col = None
    low = high = None
    is_date = False

    for chunk in pd.read_csv(path, chunksize=500_000, low_memory=False):
        if head is None:
            head = chunk
            date_col = _pick_date_column(chunk)
        rows += len(chunk)
        if date_col is None:
            continue
        chunk_low, chunk_high, is_date = _chunk_range(chunk, date_col)
        if chunk_low is None:
            continue
        low = chunk_low if low is None else min(low, chunk_low)
        high = chunk_high if high is None else max(high, chunk_high)

    spec.row_count = rows
    spec.columns = len(head.columns)
    spec.status = "downloaded"
    if not spec.date_range and low is not None:
        spec.date_range = (
            f"{low.date()} to {high.date()}" if is_date
            else f"{date_col} {low} to {high}"
        )
    if extra_note is not None:
        spec.note = f"{spec.note} {extra_note(head, rows)}".strip()
    return spec


def _scanner_data_note(df: pd.DataFrame, rows: int) -> str:
    full = pd.read_csv(CSV_DIR / "scanner_data.csv", low_memory=False)
    return (
        f"{full['StockCode'].nunique()} unique SKUs, "
        f"{full['Customer ID'].nunique()} unique customers, "
        f"{full['Country'].nunique()} countries. "
        f"{int((full['Price'] <= 0).sum())} rows with Price<=0 and "
        f"{int((full['Quantity'] < 0).sum())} rows with negative Quantity "
        "(returns) -- filter both before fitting elasticity."
    )


def _monash_note(df: pd.DataFrame, rows: int) -> str:
    zeros, series = 0, set()
    for chunk in pd.read_csv(
        CSV_DIR / "monash_dominicks.csv",
        usecols=["SKU_ID", "Weekly_Profit"],
        chunksize=2_000_000,
    ):
        zeros += int((chunk["Weekly_Profit"] == 0).sum())
        series.update(chunk["SKU_ID"].unique())
    return (
        f"{len(series)} unique series. {zeros} of {rows} rows are zero-profit "
        "weeks (no sale that week, not missing data)."
    )


def _completejourney_note(df: pd.DataFrame, rows: int) -> str:
    full = pd.read_csv(CSV_DIR / "completejourney_transactions.csv", low_memory=False)
    discounted = int((full["retail_disc"] != 0).sum())
    paid = full["sales_value"] / full["quantity"].replace(0, pd.NA)
    return (
        f"{full['household_id'].nunique()} households, "
        f"{full['product_id'].nunique()} products, "
        f"{full['store_id'].nunique()} stores. "
        f"{discounted} of {rows} rows carry a retail discount -- that is the "
        "within-product price variation elasticity is identified from. "
        f"{int((full['quantity'] <= 0).sum())} rows have quantity<=0 and "
        f"{int(paid.isna().sum())} give no usable unit price; filter both. "
        "Shelf price = (sales_value + retail_disc + coupon_disc + "
        "coupon_match_disc) / quantity."
    )


def _dominicks_oj_note(df: pd.DataFrame, rows: int) -> str:
    if "store" not in df.columns:
        return "Reduced 4-column mirror (sales, price, brand, feat)."
    return (
        f"{df['store'].nunique()} stores x {df['brand'].nunique()} brands x "
        f"{df['week'].nunique()} weeks. Units sold = exp(logmove). "
        f"{int((df['feat'] == 1).sum())} of {rows} store-weeks were featured."
    )


def _olist_note(df: pd.DataFrame, rows: int) -> str:
    full = pd.read_csv(CSV_DIR / "olist_order_items.csv", low_memory=False)
    return (
        f"{full['product_id'].nunique()} products across "
        f"{full['product_category'].nunique()} categories; "
        f"{int(full['product_category'].isna().sum())} rows have no category. "
        "One row per unit sold (order_item_id enumerates units), so group by "
        "(product_id, week) for units. Prices are BRL and exclude freight."
    )


def _specs_from_loader() -> list[DatasetSpec]:
    """Every dataset the loader declares, in the order it fetches them."""
    specs = [
        DatasetSpec(**ONLINE_RETAIL_II_SPEC),
        DatasetSpec(**MONASH_DOMINICKS_SPEC),
    ]
    for cj in COMPLETEJOURNEY_FILES:
        specs.append(DatasetSpec(
            **{k: v for k, v in cj.items() if k != "remote"},
            source_url=f"{COMPLETEJOURNEY_BASE}/{cj['remote']}",
            note=(
                "Source: 84.51 degrees 'The Complete Journey', redistributed "
                f"as R data files by the completejourney package ({cj['remote']})."
            ),
        ))
    specs.append(DatasetSpec(**DOMINICKS_OJ_SPEC))
    specs.append(DatasetSpec(**OLIST_SPEC))
    for rd in RDATASETS:
        specs.append(DatasetSpec(
            **{k: v for k, v in rd.items() if k not in ("pkg", "item")},
            source_url=RDATASETS_DOC_URL.format(pkg=rd["pkg"], item=rd["item"]),
            note=(
                f"Rdatasets CSV mirror of R package `{rd['pkg']}`, dataset "
                f"`{rd['item']}`; the archive's row-index column is dropped."
            ),
        ))
    for kd in KAGGLE_DATASETS:
        specs.append(DatasetSpec(
            **{k: v for k, v in kd.items() if k != "kaggle_ref"},
            source_url=f"https://www.kaggle.com/datasets/{kd['kaggle_ref']}",
            status="manual_required",
            note=(
                "Kaggle API returned 403 (unauthenticated). Configure "
                "~/.kaggle/kaggle.json, then run `python -m src.data_loader`."
            ),
        ))
    specs.extend(MANUAL_ONLY_DATASETS)
    return specs


NOTE_BUILDERS = {
    "scanner_data.csv": _scanner_data_note,
    "monash_dominicks.csv": _monash_note,
    "completejourney_transactions.csv": _completejourney_note,
    "dominicks_oj.csv": _dominicks_oj_note,
    "olist_order_items.csv": _olist_note,
}


def build() -> list[DatasetSpec]:
    previous = _read_existing_manifest()
    specs: list[DatasetSpec] = []

    for spec in _specs_from_loader():
        if (CSV_DIR / spec.filename).exists():
            specs.append(_profile(spec, NOTE_BUILDERS.get(spec.filename)))
        elif spec.filename in previous and previous[spec.filename]["row_count"]:
            specs.append(_carry_over(spec, previous[spec.filename]))
        else:
            if spec.status == "not_downloaded":
                spec.status = "unreachable"
                spec.note = spec.note or (
                    "Not present in data/csv and no earlier profile recorded. "
                    "Run `python -m src.data_loader` on a machine that can "
                    "reach the source."
                )
            specs.append(spec)

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
    unreachable = [s for s in specs if s.status not in ("downloaded", "manual_required")]

    lines.append(f"Downloaded and profiled: {len(downloaded)}")
    lines.append(f"Requires manual action: {len(manual)}")
    lines.append(f"Unreachable from this machine: {len(unreachable)}")
    lines.append(f"Total rows across profiled files: "
                 f"{sum(s.row_count or 0 for s in downloaded):,}")
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

    if unreachable:
        lines.append("UNREACHABLE FROM THIS MACHINE")
        lines.append("-" * 60)
        for s in unreachable:
            lines += [f"--- {s.filename} ---", f"source: {s.source_url}",
                      f"why: {s.note}", ""]

    lines.append("REQUIRES MANUAL ACTION")
    lines.append("-" * 60)
    for s in manual:
        lines += [f"--- {s.filename} ---", f"source: {s.source_url}",
                  f"why blocked: {s.note}", ""]

    REPORT_PATH.write_text("\n".join(lines))


if __name__ == "__main__":
    specs = build()
    write_validation_report(specs)
    print(f"Wrote {MANIFEST_PATH}")
    print(f"Wrote {REPORT_PATH}")
