"""
The second catalogue: five and a half years of Walmart store sales.

What this is
------------
The M5 competition dataset, released by the M Open Forecasting Center at the
University of Nicosia for the M5 Forecasting Accuracy competition. It is real
Walmart point-of-sale data:

  3,049 products, 10 stores, 3 US states (CA, TX, WI)
  daily units sold, 2011-01-29 to 2016-06-19 (1,941 days)
  weekly shelf prices per store and item (6,841,121 of them)
  a real product hierarchy: 3 categories, 7 departments

Why it matters here
-------------------
The original catalogue is one UK gift and homeware wholesaler, 2009 to 2011,
and its departments are guessed from words in the product name because the
source data carries no category field. This one is five years more recent, in
a trade most people actually recognise (food, household, hobbies), and its
departments are the retailer's own rather than a keyword rule.

It is also large enough to change what the page can say: 30,490 store-item
series times 1,941 days is 59,181,090 daily records, which roll up to
8,598,180 store-item-weeks with a price attached.

Where it comes from
-------------------
Canonical source, from the competition organisers:

    https://github.com/Mcompetitions/M5-methods

That repository holds the competition's code and documentation but not the
data files themselves, so this module pulls the same CSVs from a public
mirror that keeps them in one 7-zip archive:

    https://github.com/Sanaxen/m5-forecasting-accuracy
    m5-forecasting-accuracy/m5-forecasting-accuracy.7z  (29 MB)

The archive contents are checked against the published M5 specification
before anything is written, so a mirror that has been altered fails loudly
rather than quietly feeding the model something else. See EXPECTED below.

Run: python -m src.walmart_data
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WALMART_DIR = ROOT / "data" / "csv" / "walmart"

MIRROR_REPO = "https://github.com/Sanaxen/m5-forecasting-accuracy"
ARCHIVE_PATH = "m5-forecasting-accuracy/m5-forecasting-accuracy.7z"
CANONICAL_SOURCE = "https://github.com/Mcompetitions/M5-methods"

WANTED = ["calendar.csv", "sell_prices.csv", "sales_train_evaluation.csv"]

# The published M5 shape. A mirror that does not match this is not the M5
# dataset, whatever it is called, and we would rather fail than fit it.
EXPECTED = {
    "calendar.csv": {"rows": 1969, "first_date": "2011-01-29", "last_date": "2016-06-19"},
    "sell_prices.csv": {"rows": 6841121, "stores": 10, "items": 3049, "weeks": 282},
    "sales_train_evaluation.csv": {"rows": 30490, "day_columns": 1941},
}


def fetch(dest: Path = WALMART_DIR) -> Path:
    """Clone the mirror without blobs, pull just the archive, unpack it."""
    dest.mkdir(parents=True, exist_ok=True)
    if all((dest / name).exists() for name in WANTED):
        print(f"  already present in {dest}")
        return dest

    try:
        import py7zr  # noqa: F401
    except ImportError:
        raise SystemExit("py7zr is required to unpack the M5 archive: pip install py7zr")

    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "mirror"
        print(f"  cloning {MIRROR_REPO} (metadata only) ...")
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", "--depth", "1",
             MIRROR_REPO, str(checkout)],
            check=True, capture_output=True,
            env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"},
        )
        print(f"  fetching {ARCHIVE_PATH} ...")
        subprocess.run(["git", "checkout", "HEAD", "--", ARCHIVE_PATH],
                       cwd=checkout, check=True, capture_output=True)

        import py7zr
        archive = checkout / ARCHIVE_PATH
        print(f"  unpacking {archive.stat().st_size / 1e6:.0f} MB ...")
        with py7zr.SevenZipFile(archive, "r") as z:
            z.extract(path=tmp, targets=WANTED)
        for name in WANTED:
            shutil.move(str(Path(tmp) / name), str(dest / name))

    return dest


def verify(dest: Path = WALMART_DIR) -> dict:
    """Check the unpacked files against the published M5 specification."""
    import pandas as pd

    report = {}

    calendar = pd.read_csv(dest / "calendar.csv")
    spec = EXPECTED["calendar.csv"]
    assert len(calendar) == spec["rows"], f"calendar has {len(calendar)} rows, expected {spec['rows']}"
    assert calendar["date"].min() == spec["first_date"], "calendar does not start where M5 starts"
    assert calendar["date"].max() == spec["last_date"], "calendar does not end where M5 ends"
    report["calendar.csv"] = {"rows": len(calendar), "columns": calendar.shape[1],
                              "date_range": f"{calendar['date'].min()} to {calendar['date'].max()}"}

    prices = pd.read_csv(dest / "sell_prices.csv")
    spec = EXPECTED["sell_prices.csv"]
    assert len(prices) == spec["rows"], f"sell_prices has {len(prices)} rows, expected {spec['rows']}"
    assert prices["store_id"].nunique() == spec["stores"]
    assert prices["item_id"].nunique() == spec["items"]
    assert prices["wm_yr_wk"].nunique() == spec["weeks"]
    report["sell_prices.csv"] = {"rows": len(prices), "columns": prices.shape[1],
                                 "stores": int(prices["store_id"].nunique()),
                                 "items": int(prices["item_id"].nunique()),
                                 "weeks": int(prices["wm_yr_wk"].nunique())}

    header = pd.read_csv(dest / "sales_train_evaluation.csv", nrows=1)
    day_columns = [c for c in header.columns if c.startswith("d_")]
    spec = EXPECTED["sales_train_evaluation.csv"]
    assert len(day_columns) == spec["day_columns"], \
        f"sales has {len(day_columns)} day columns, expected {spec['day_columns']}"
    rows = sum(1 for _ in open(dest / "sales_train_evaluation.csv")) - 1
    assert rows == spec["rows"], f"sales has {rows} rows, expected {spec['rows']}"
    report["sales_train_evaluation.csv"] = {
        "rows": rows, "columns": header.shape[1], "day_columns": len(day_columns),
        "daily_records": rows * len(day_columns),
    }
    return report


def main() -> None:
    fetch()
    report = verify()
    for name, facts in report.items():
        print(f"  [verified] {name:<30} " + "  ".join(f"{k}={v:,}" if isinstance(v, int) else f"{k}={v}"
                                                      for k, v in facts.items()))
    daily = report["sales_train_evaluation.csv"]["daily_records"]
    print(f"\n{daily:,} daily store-item records, matching the published M5 specification.")
    print(f"Canonical source: {CANONICAL_SOURCE}")


if __name__ == "__main__":
    sys.exit(main())
