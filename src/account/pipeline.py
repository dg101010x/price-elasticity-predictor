"""
Upload -> stored file -> data_sources row -> weekly observations -> fitted
runs, synchronously, in the request that carried the file.

Order matters and is chosen so every failure leaves an honest trail:

  1. The mapping is checked against the file's header first. A wrong column
     choice is the user's to fix on the spot, so nothing is stored for it.
  2. The CSV goes to Storage under {account_id}/ with the uploader's own
     token -- the bucket's policies, not this code, decide whether their
     role may write -- and a data_sources row is filed as them (pending).
  3. From here the server acts with the service role: it marks the row
     processing, parses, cleans, fits, writes observations and runs, and
     marks it ready -- or failed, with a reason the Data page shows.

Sizing: a catalogue of weekly sales is thousands to tens of thousands of
rows, which fits comfortably in one request. There is no queue.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING

from .config import Settings
from .session import Membership, Session
from .supabase import SERVICE, Supabase, SupabaseError

if TYPE_CHECKING:
    from . import ingest

log = logging.getLogger(__name__)

UPLOAD_ROLES = ("owner", "manage")
INSERT_CHUNK = 5000


class UploadRefused(Exception):
    """A request-level problem (HTTP 4xx) -- nothing was stored."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def safe_filename(name: str) -> str:
    base = (name or "upload.csv").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.") or "upload"
    if not base.lower().endswith(".csv"):
        base += ".csv"
    return base[:120]


def process_upload(sb: Supabase, settings: Settings, session: Session, member: Membership,
                   raw: bytes, filename: str, mapping: dict, date_order: str | None,
                   currency: str) -> dict:
    from . import ingest          # pandas: loaded only when a file actually arrives

    if member.role not in UPLOAD_ROLES:
        raise UploadRefused(403, "Only the account's owner or a manager can upload sales data.")

    # 1. Cheap checks before anything is stored.
    try:
        text = ingest.decode(raw)
        head, _ = ingest.read_frame(text, nrows=5000)
        chosen = ingest.validate_mapping(mapping, list(head.columns))
        ingest.check_dates(head, chosen["date"], date_order)
    except ingest.IngestError as exc:
        raise UploadRefused(422, str(exc)) from exc

    # 2. Store the file and file the row, as the uploader.
    display_name = safe_filename(filename)
    path = f"{member.account_id}/{uuid.uuid4()}-{display_name}"
    try:
        sb.upload(settings.storage_bucket, path, raw, "text/csv", session.access_token)
    except SupabaseError as exc:
        if exc.status in (400, 401, 403) and "row-level security" in exc.message.lower():
            raise UploadRefused(403, "Your role on this account can't upload files.") from exc
        raise
    source = sb.insert("data_sources", {
        "account_id": member.account_id,
        "filename": display_name,
        "storage_path": path,
        "uploaded_by": session.user_id,
    }, session.access_token)[0]
    source_id = source["id"]

    # 3. Compute, as the server.
    def fail(reason: str, report: dict | None = None, row_count: int | None = None) -> dict:
        values = {"status": "failed", "status_reason": reason}
        if report is not None:
            values["report"] = report
        if row_count is not None:
            values["row_count"] = row_count
        return sb.update("data_sources", values, SERVICE, id=f"eq.{source_id}")[0]

    sb.update("data_sources", {"status": "processing"}, SERVICE, id=f"eq.{source_id}")
    try:
        prepared = ingest.prepare(raw, mapping, date_order=date_order, currency=currency)
    except ingest.IngestError as exc:
        return {"data_source": fail(str(exc)), "runs": []}
    except Exception:
        log.exception("ingest failed for data source %s", source_id)
        return {"data_source": fail("Something went wrong reading this file. It has been kept; "
                                    "try again, or contact support if it keeps happening."), "runs": []}

    reason = ingest.failure_reason(prepared)
    if reason:
        return {"data_source": fail(reason, prepared.report, prepared.row_count), "runs": []}

    try:
        _write_observations(sb, member.account_id, source_id, prepared)
        runs = sb.insert("elasticity_runs", [
            {"account_id": member.account_id, "data_source_id": source_id, **run}
            for run in prepared.runs
        ], SERVICE)
        report = dict(prepared.report)
        report["run_ids"] = {(r["category"] or "__overall__"): r["id"] for r in runs}
        ready = sb.update("data_sources", {
            "status": "ready", "status_reason": None, "row_count": prepared.row_count, "report": report,
        }, SERVICE, id=f"eq.{source_id}")[0]
    except Exception:
        log.exception("writing results failed for data source %s", source_id)
        _cleanup(sb, source_id)
        return {"data_source": fail("The estimate was computed but couldn't be saved. "
                                    "Nothing partial was kept; please upload again.",
                                    prepared.report, prepared.row_count), "runs": []}
    return {"data_source": ready, "runs": runs}


def _write_observations(sb: Supabase, account_id: str, source_id: str, prepared: ingest.Prepared) -> None:
    obs = prepared.observations
    records = [
        {"account_id": account_id, "data_source_id": source_id,
         "product_key": key, "product_description": desc, "category": cat,
         "week_start": week, "price": float(price), "units_sold": int(units)}
        for key, desc, cat, week, price, units in obs.itertuples(index=False, name=None)
    ]
    for start in range(0, len(records), INSERT_CHUNK):
        sb.insert("sales_observations", records[start:start + INSERT_CHUNK], SERVICE, returning=False)


def _cleanup(sb: Supabase, source_id: str) -> None:
    for table in ("elasticity_runs", "sales_observations"):
        try:
            sb.delete(table, SERVICE, data_source_id=f"eq.{source_id}")
        except Exception:
            log.exception("cleanup of %s for %s failed", table, source_id)
