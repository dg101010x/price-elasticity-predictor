"""
Turn an uploaded sales CSV into the weekly panel the estimator reads.

Two stages, deliberately separate so a bad file fails before anything is
stored:

  inspect(raw)          header + a sample: which column is which, and whether
                        that is certain. Nothing is guessed silently -- a
                        field with no exact alias match, several matches, or
                        dates that read either way round (03/04) comes back
                        flagged, and the upload page asks.
  prepare(raw, mapping) the whole file: parse, clean, roll up to one row per
                        product per week (src/stats_engine.weekly_panel, the
                        same rollup as the public build), fit (fit_catalogue,
                        the same estimator), and a report of every row that
                        was dropped and why.

The estimate is fitted on exactly the rows that get stored as
sales_observations -- weekly units rounded to whole units and prices to six
decimals -- so anyone with database access can reproduce it from the table.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import stats_engine
from .limits import MAX_ROWS, MAX_UPLOAD_BYTES

UNCATEGORIZED = "Uncategorized"

# ----------------------------------------------------------------- fields --

FIELDS = ("product_key", "description", "category", "date", "price", "revenue", "units")
REQUIRED = ("product_key", "date", "units")      # plus one of price / revenue

FIELD_LABELS = {
    "product_key": "Product ID / SKU",
    "description": "Product name",
    "category": "Category",
    "date": "Date or week",
    "price": "Unit price",
    "revenue": "Sales amount (price x units)",
    "units": "Units sold",
}

# Header aliases, compared after normalising (lower case, runs of anything
# that isn't a letter or digit collapsed to "_"). Exact matches only; a
# header that merely contains one of these is offered as a suggestion that
# the user has to confirm.
ALIASES: dict[str, set[str]] = {
    "product_key": {
        "sku", "skus", "sku_id", "sku_code", "product_id", "productid", "product_key", "product_code",
        "productcode", "item_id", "itemid", "item_code", "itemcode", "item_number", "item_no",
        "stockcode", "stock_code", "article", "article_number", "variant_id", "variant_sku",
        "upc", "ean", "barcode", "gtin", "asin", "plu", "part_number", "part_no", "style_number",
    },
    "description": {
        "description", "product_description", "item_description", "product_name", "productname",
        "item_name", "itemname", "name", "title", "product_title", "product", "item", "lineitem_name",
        "variant_name",
    },
    "category": {
        "category", "product_category", "item_category", "categories", "department", "dept",
        "product_type", "producttype", "type", "collection", "product_group", "group", "class",
        "family", "segment", "category_name",
    },
    "date": {
        "date", "week", "week_start", "weekstart", "week_starting", "week_beginning", "week_of",
        "week_ending", "order_date", "orderdate", "invoice_date", "invoicedate", "transaction_date",
        "sale_date", "sales_date", "sold_date", "day", "created_at", "timestamp", "datetime",
        "order_created_at", "paid_at", "period",
    },
    "price": {
        "price", "unit_price", "unitprice", "price_per_unit", "avg_price", "average_price",
        "avg_unit_price", "average_unit_price", "selling_price", "sale_price", "net_price",
        "item_price", "lineitem_price", "retail_price", "price_paid",
    },
    "revenue": {
        "revenue", "sales", "net_sales", "gross_sales", "total_sales", "sales_amount", "sales_value",
        "line_total", "net_revenue", "gross_revenue", "turnover", "amount", "net_amount",
    },
    "units": {
        "units", "units_sold", "unitssold", "unit_sales", "quantity", "qty", "quantity_sold",
        "qty_sold", "items_sold", "net_quantity", "net_items_sold", "volume", "sold", "sales_units",
        "lineitem_quantity", "count",
    },
}

# Substrings good enough to *suggest* a column, never to pick it unasked.
HINTS: dict[str, tuple[str, ...]] = {
    "product_key": ("sku", "product_id", "item_id", "code", "barcode"),
    "description": ("description", "name", "title"),
    "category": ("categor", "department", "type", "collection"),
    "date": ("date", "week", "day", "time", "period"),
    "price": ("price",),
    "revenue": ("revenue", "sales", "amount", "total"),
    "units": ("qty", "quant", "units", "sold"),
}


class IngestError(ValueError):
    """A problem with the file the user can fix -- shown to them verbatim."""


AMBIGUOUS_DATES = ("The dates in that column could be read either way round — 03/04 as 3 April or as "
                   "4 March — and nothing in the file settles it. Say which way they're written.")


def check_dates(frame: pd.DataFrame, column: str, date_order: str | None) -> None:
    """Refuse, before anything is stored, to guess which way round dates go."""
    if date_order is None and not detect_date_order(frame[column])[1]:
        raise IngestError(AMBIGUOUS_DATES)


def _norm(header: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", str(header).strip().lower()).strip("_")


# ---------------------------------------------------------------- decoding --

def decode(raw: bytes) -> str:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise IngestError(f"That file is {len(raw) / 1e6:.0f} MB; the limit is "
                          f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestError("Couldn't read the file's text encoding. Save it as UTF-8 CSV and try again.")


def sniff_delimiter(text: str) -> str:
    sample = text[:65536]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def read_frame(text: str, nrows: int | None = None) -> tuple[pd.DataFrame, str]:
    delimiter = sniff_delimiter(text)
    try:
        frame = pd.read_csv(io.StringIO(text), sep=delimiter, dtype=str, keep_default_na=False,
                            skipinitialspace=True, nrows=nrows, on_bad_lines="error")
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise IngestError(f"That doesn't parse as a CSV file: {str(exc).splitlines()[0]}") from exc
    if frame.shape[1] < 3:
        raise IngestError("The file has fewer than three columns. It needs at least a product, "
                          "a date and units sold, plus a price or sales amount.")
    frame.columns = [str(c).strip() for c in frame.columns]
    if len(set(frame.columns)) != len(frame.columns):
        raise IngestError("Two columns share a header name. Rename one and upload again.")
    return frame, delimiter


# ----------------------------------------------------------------- mapping --

@dataclass
class FieldGuess:
    field: str
    column: str | None
    confident: bool
    candidates: list[str] = field(default_factory=list)
    why: str = ""


def guess_mapping(columns: list[str]) -> dict[str, FieldGuess]:
    normalised = {c: _norm(c) for c in columns}
    exact: dict[str, list[str]] = {f: [] for f in FIELDS}
    for col, n in normalised.items():
        for f in FIELDS:
            if n in ALIASES[f] or n.replace("_", "") in {a.replace("_", "") for a in ALIASES[f]}:
                exact[f].append(col)

    guesses: dict[str, FieldGuess] = {}
    for f in FIELDS:
        hits = exact[f]
        if len(hits) == 1:
            guesses[f] = FieldGuess(f, hits[0], True, hits, "exact header match")
        elif len(hits) > 1:
            guesses[f] = FieldGuess(f, hits[0], False, hits, "several columns could be this")
        else:
            near = [c for c, n in normalised.items() if any(h in n for h in HINTS[f])]
            guesses[f] = FieldGuess(f, near[0] if near else None, False, near,
                                    "closest header, please confirm" if near else "no matching header")

    # One column can't fill two fields. When it's the confident pick for one
    # field, drop it from the others; otherwise flag both.
    taken = {g.column: f for f, g in guesses.items() if g.confident and g.column}
    for f, g in guesses.items():
        if g.column and g.column in taken and taken[g.column] != f:
            others = [c for c in g.candidates if c not in taken]
            g.column = others[0] if others else None
            g.confident = False
            g.candidates = others
            g.why = "closest header, please confirm" if others else "no matching header"
    return guesses


DATE_ORDERS = ("ymd", "dmy", "mdy")


def detect_date_order(values: pd.Series) -> tuple[str | None, bool]:
    """Which way round the dates are written, and whether that is certain.

    ISO dates (2025-03-04) are unambiguous. For 03/04/2025 the day could be
    either number, so the file is read for proof: any first number over 12
    means day-first, any second number over 12 means month-first. If no
    value settles it, the answer is 'ambiguous' and the user is asked
    rather than a coin being tossed on their whole history.
    """
    sample = values[values.str.strip() != ""].head(5000)
    if sample.empty:
        return None, False
    iso = sample.str.match(r"^\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")
    if iso.mean() > 0.95:
        return "ymd", True
    parts = sample.str.extract(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})")
    parts = parts.dropna()
    if parts.empty:
        return None, True       # text dates ("4 Mar 2025") or timestamps; pandas reads those unaided
    first = parts[0].astype(int)
    second = parts[1].astype(int)
    if (first > 12).any() and not (second > 12).any():
        return "dmy", True
    if (second > 12).any() and not (first > 12).any():
        return "mdy", True
    return "dmy", False


def inspect(raw: bytes) -> dict:
    """Header, sample rows and a proposed mapping, for the upload page."""
    text = decode(raw)
    frame, delimiter = read_frame(text, nrows=2000)
    columns = list(frame.columns)
    guesses = guess_mapping(columns)

    date_order, date_certain = (None, True)
    if guesses["date"].column:
        date_order, date_certain = detect_date_order(frame[guesses["date"].column])

    have_price = guesses["price"].column is not None
    needs_confirmation = (
        any(not guesses[f].confident for f in REQUIRED)
        or not (guesses["price"].confident or guesses["revenue"].confident)
        or not date_certain
    )
    # A price column that's only a suggestion shouldn't block when revenue
    # is certain, and vice versa -- only one of the two is needed.
    if guesses["revenue"].confident and not guesses["price"].confident:
        guesses["price"].column = None if not have_price or not guesses["price"].candidates else guesses["price"].column

    return {
        "columns": columns,
        "delimiter": delimiter,
        "sample": frame.head(5).to_dict(orient="records"),
        "mapping": {f: g.column for f, g in guesses.items()},
        "fields": [
            {"field": f, "label": FIELD_LABELS[f], "column": g.column, "confident": g.confident,
             "candidates": g.candidates, "why": g.why,
             "required": f in REQUIRED, "one_of": "price_or_revenue" if f in ("price", "revenue") else None}
            for f, g in guesses.items()
        ],
        "date_order": date_order,
        "date_order_certain": date_certain,
        "needs_confirmation": needs_confirmation,
    }


def validate_mapping(mapping: dict, columns: list[str]) -> dict:
    clean = {f: (mapping.get(f) or None) for f in FIELDS}
    for f, col in clean.items():
        if col is not None and col not in columns:
            raise IngestError(f"The column “{col}” chosen for {FIELD_LABELS[f]} isn't in the file.")
    missing = [FIELD_LABELS[f] for f in REQUIRED if clean[f] is None]
    if missing:
        raise IngestError("Choose a column for: " + ", ".join(missing) + ".")
    if clean["price"] is None and clean["revenue"] is None:
        raise IngestError("Choose either a unit price column or a sales amount column.")
    used = [c for c in clean.values() if c is not None]
    if len(used) != len(set(used)):
        raise IngestError("The same column is chosen for two different fields.")
    return clean


# ----------------------------------------------------------------- parsing --

_CURRENCY_RE = re.compile(r"[^\d,.\-+eE()]")


def parse_numbers(values: pd.Series, decimal_comma: bool) -> pd.Series:
    """'£1,234.50', '$ 3.20', '(4.00)', '3,20' -> floats; anything else NaN."""
    s = values.astype(str).str.strip()
    negative = s.str.match(r"^\(.*\)$")
    s = s.str.replace(_CURRENCY_RE, "", regex=True).str.replace(r"[()]", "", regex=True)
    if decimal_comma:
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    else:
        s = s.str.replace(",", "", regex=False)
    out = pd.to_numeric(s, errors="coerce")
    out[negative] = -out[negative]
    return out


def parse_dates(values: pd.Series, order: str | None) -> pd.Series:
    s = values.astype(str).str.strip()
    # ISO week labels ("2025-W07") mean the Monday of that week.
    iso_week = s.str.match(r"^\d{4}-?W\d{1,2}$")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if iso_week.any():
        out[iso_week] = pd.to_datetime(s[iso_week].str.replace("-", "") + "1", format="%GW%V%u",
                                       errors="coerce")
    rest = ~iso_week
    if rest.any():
        parsed = pd.to_datetime(s[rest], errors="coerce", dayfirst=(order == "dmy"),
                                yearfirst=(order == "ymd"), format="mixed", utc=True)
        out[rest] = parsed.dt.tz_convert(None)
    return out


# ------------------------------------------------------------------ prepare --

@dataclass
class Prepared:
    observations: pd.DataFrame          # product_key, product_description, category, week_start, price, units_sold
    fitted: dict                        # stats_engine.fit_catalogue output
    runs: list[dict]                    # stats_engine.run_record objects, overall first
    report: dict
    row_count: int


def _modal(series: pd.Series) -> pd.Series:
    return series.groupby(level=0).agg(lambda s: s.value_counts().index[0] if len(s.dropna()) else None)


def prepare(raw: bytes, mapping: dict, date_order: str | None = None, currency: str = "USD") -> Prepared:
    text = decode(raw)
    frame, delimiter = read_frame(text)
    if len(frame) > MAX_ROWS:
        raise IngestError(f"The file has {len(frame):,} rows; the limit is {MAX_ROWS:,}. "
                          "Roll it up to one row per product per week or day first.")
    if frame.empty:
        raise IngestError("The file has a header but no rows.")
    columns = list(frame.columns)
    m = validate_mapping(mapping, columns)
    if date_order not in (None, *DATE_ORDERS):
        raise IngestError("Unknown date order.")

    rows_read = len(frame)
    decimal_comma = delimiter == ";"
    dropped: dict[str, int] = {}

    def drop(mask: pd.Series, reason: str) -> None:
        nonlocal work
        count = int(mask.sum())
        if count:
            dropped[reason] = dropped.get(reason, 0) + count
            work = work[~mask]

    if date_order is None:
        detected, certain = detect_date_order(frame[m["date"]])
        if not certain:
            raise IngestError(AMBIGUOUS_DATES)
        date_order = detected

    work = pd.DataFrame({
        "product": frame[m["product_key"]].astype(str).str.strip(),
        "description": frame[m["description"]].astype(str).str.strip() if m["description"] else "",
        "category": frame[m["category"]].astype(str).str.strip() if m["category"] else "",
        "date": parse_dates(frame[m["date"]], date_order),
        "quantity": parse_numbers(frame[m["units"]], decimal_comma),
    })
    if m["price"]:
        work["price"] = parse_numbers(frame[m["price"]], decimal_comma)
    else:
        revenue = parse_numbers(frame[m["revenue"]], decimal_comma)
        with np.errstate(divide="ignore", invalid="ignore"):
            work["price"] = revenue / work["quantity"]

    drop(work["product"] == "", "no product ID")
    drop(work["date"].isna(), "date couldn't be read")
    drop(work["quantity"].isna(), "units couldn't be read as a number")
    drop(work["quantity"] <= 0, "zero or negative units (returns, refunds, voids)")
    drop(work["price"].isna() | ~np.isfinite(work["price"]), "price couldn't be read as a number")
    drop(work["price"] <= 0, "zero or negative price (free items, comps)")

    if work.empty:
        raise IngestError("No usable rows are left after cleaning: " + _describe_drops(dropped) + ".")
    if dropped and sum(dropped.values()) > 0.5 * rows_read:
        worst = max(dropped, key=dropped.get)
        raise IngestError(f"More than half the rows were unusable (most often: {worst}). "
                          "Check the column choices, especially the date and number columns.")

    # One category and one name per product: the most common one it was
    # sold under. Without this, a product filed under two categories would
    # appear twice in the same week.
    work = work.set_index("product", drop=False)
    conflicts = int((work.groupby(level=0)["category"].nunique() > 1).sum())
    work["category"] = _modal(work["category"]).reindex(work.index).to_numpy()
    work["description"] = _modal(work["description"]).reindex(work.index).to_numpy()
    work = work.reset_index(drop=True)
    work["category"] = work["category"].fillna("").replace("", UNCATEGORIZED)

    panel = stats_engine.weekly_panel(work[["product", "category", "date", "quantity", "price"]])

    # Store what's fitted, fit what's stored.
    fractional = int((np.abs(panel["qty"] - np.round(panel["qty"])) > 1e-9).sum())
    panel["qty"] = np.round(panel["qty"])
    panel["price"] = np.round(panel["price"], 6)
    zeroed = int((panel["qty"] <= 0).sum())
    panel = panel[(panel["qty"] > 0) & (panel["price"] > 0)].reset_index(drop=True)

    if m["category"]:
        uncategorized_reason = "rows with a blank category — too mixed to report as a group of their own"
    else:
        uncategorized_reason = "no category column in the upload — add one to get per-category estimates"
    fitted = stats_engine.fit_catalogue(panel, catch_all={UNCATEGORIZED: uncategorized_reason})

    names = work.drop_duplicates("product").set_index("product")["description"]
    observations = pd.DataFrame({
        "product_key": panel["product"],
        "product_description": panel["product"].map(names).replace("", None),
        "category": panel["category"],
        "week_start": pd.to_datetime(panel["week"]).dt.date.astype(str),
        "price": panel["price"],
        "units_sold": panel["qty"].astype(int),
    })

    runs: list[dict] = []
    run_meta: dict[str, dict] = {}
    if fitted["overall"] is not None:
        runs.append(stats_engine.run_record(fitted["overall"], None))
        run_meta["__overall__"] = _meta(fitted["overall"])
    for row in fitted["by_category"]:
        runs.append(stats_engine.run_record(row, row["category"]))
        run_meta[row["category"]] = _meta(row)

    weeks = pd.to_datetime(panel["week"])
    report = {
        "mapping": m,
        "date_order": date_order,
        "currency": currency,
        "delimiter": delimiter,
        "rows_read": rows_read,
        "rows_used": int(len(work)),
        "dropped": dropped,
        "product_weeks": int(len(panel)),
        "products": int(panel["product"].nunique()),
        "weeks": int(weeks.nunique()),
        "date_range": [str(weeks.min().date()), str(weeks.max().date())] if len(weeks) else None,
        "category_conflicts": conflicts,
        "fractional_units_rounded": fractional,
        "product_weeks_rounded_to_zero": zeroed,
        "excluded_categories": fitted["excluded_categories"],
        "run_meta": run_meta,
        "thresholds": {"min_obs_per_category": stats_engine.MIN_OBS_PER_CATEGORY,
                       "min_products_per_category": stats_engine.MIN_PRODUCTS_PER_CATEGORY},
        "diagnostics": _identification_diagnostics(panel),
    }
    return Prepared(observations=observations, fitted=fitted, runs=runs, report=report,
                    row_count=rows_read)


def _meta(result: dict) -> dict:
    return {"std_error": result["std_error"], "n_products": int(result["n_skus"]),
            "interpretation": result["interpretation"],
            "pct_quantity_change_for_10pct_price_increase":
                result["pct_quantity_change_for_10pct_price_increase"]}


def _identification_diagnostics(panel: pd.DataFrame) -> dict:
    """What the regression can actually learn from: products seen in two or
    more weeks whose price moved at least once."""
    if panel.empty:
        return {"products_with_repeat_weeks": 0, "products_with_price_changes": 0, "usable_product_weeks": 0}
    g = panel.groupby("product")
    weeks_per = g["week"].transform("count")
    moved = g["price"].transform(lambda s: np.log(s).max() - np.log(s).min() > 1e-9)
    usable = (weeks_per >= 2) & moved
    return {
        "products_with_repeat_weeks": int((g["week"].count() >= 2).sum()),
        "products_with_price_changes": int(panel.loc[usable, "product"].nunique()),
        "usable_product_weeks": int(usable.sum()),
    }


def failure_reason(prepared: Prepared) -> str | None:
    """Why no estimate could be made, in words the uploader can act on."""
    if prepared.fitted["overall"] is not None:
        return None
    d = prepared.report["diagnostics"]
    return (
        "Not enough price movement to measure anything. The estimate needs at least 30 "
        "product-weeks from products whose price changed at some point; this file has "
        f"{d['usable_product_weeks']} (from {d['products_with_price_changes']} products). "
        "Upload a longer history, or more products."
    )


def _describe_drops(dropped: dict) -> str:
    return "; ".join(f"{n:,} with {reason}" for reason, n in dropped.items()) or "nothing to read"
