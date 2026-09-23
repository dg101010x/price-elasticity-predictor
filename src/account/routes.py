"""
The signed-in half of the API: auth, onboarding, uploads, and an account's
own estimates in the public page's shapes.

  POST /api/auth/signup | /login | /logout | /session     cookie sessions
  GET  /api/me                                            who, and which account
  POST /api/account                                       onboarding
  POST /api/uploads/inspect                               column mapping proposal
  POST /api/uploads                                       store + fit, synchronously
  GET  /api/uploads                                       upload history
  GET  /api/account/estimates | /catalog | /benchmarks    latest ready upload
  GET  /api/account/insights  POST /api/account/insights  grounded recommendations

Upload bodies are the raw CSV, optionally gzip-compressed by the browser
(Vercel caps request bodies at 4.5 MB; CSV compresses 5-10x).
"""

from __future__ import annotations

import json
import zlib
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import config, llm, pipeline, results, session
from .limits import MAX_UPLOAD_BYTES
from .supabase import SupabaseError, client

router = APIRouter(prefix="/api")

GZIP_MAGIC = b"\x1f\x8b"
CURRENCIES = ("USD", "GBP", "EUR", "CAD", "AUD", "INR", "NZD", "JPY", "CHF", "SEK", "SGD", "ZAR")


# ------------------------------------------------------------------ helpers --

def _require_configured() -> config.Settings:
    settings = config.settings()
    if not settings.supabase_configured:
        raise HTTPException(503, "Accounts aren't switched on for this deployment yet "
                                 "(Supabase environment variables are not set).")
    return settings


def _require_session(request: Request) -> session.Session:
    _require_configured()
    current = session.current_session(request)
    if current is None:
        raise HTTPException(401, "Sign in first.")
    return current


def _require_member(request: Request) -> tuple[session.Session, session.Membership]:
    current = _require_session(request)
    member = session.membership(request, current)
    if member is None:
        raise HTTPException(409, "Create your business account first.")
    return current, member


AUTH_MESSAGES = {
    "invalid_credentials": "That email and password don't match an account.",
    "invalid_grant": "That email and password don't match an account.",
    "email_not_confirmed": "Confirm your email address first — the link is in your inbox.",
    "user_already_exists": "There's already an account with that email. Sign in instead.",
    "email_exists": "There's already an account with that email. Sign in instead.",
    "signup_disabled": "New sign-ups are closed at the moment.",
    "email_address_invalid": "That email address doesn't look right.",
    "validation_failed": "That email address doesn't look right.",
    "over_email_send_rate_limit": "Too many emails sent to that address. Wait a few minutes and try again.",
    "over_request_rate_limit": "Too many attempts. Wait a minute and try again.",
}


def _auth_error(exc: SupabaseError) -> HTTPException:
    if exc.status >= 500:
        return HTTPException(502, "The sign-in service didn't answer. Try again in a moment.")
    if exc.code == "weak_password":
        return HTTPException(422, f"Choose a stronger password. {exc.message}")
    return HTTPException(exc.status if exc.status in (400, 401, 403, 409, 422, 429) else 400,
                         AUTH_MESSAGES.get(exc.code, exc.message))


async def _read_upload(request: Request) -> bytes:
    body = await request.body()
    if not body:
        raise HTTPException(400, "The upload was empty.")
    if body[:2] == GZIP_MAGIC:
        inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            body = inflater.decompress(body, MAX_UPLOAD_BYTES + 1)
        except zlib.error as exc:
            raise HTTPException(400, "The compressed upload was damaged. Try again.") from exc
        if len(body) > MAX_UPLOAD_BYTES or inflater.unconsumed_tail:
            raise HTTPException(413, "That file is too large once decompressed "
                                     f"(limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    return body


# --------------------------------------------------------------------- auth --

class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class TokenPair(BaseModel):
    access_token: str = Field(min_length=10)
    refresh_token: str = Field(min_length=4)
    expires_in: Optional[int] = 3600


@router.post("/auth/signup")
def signup(body: Credentials, request: Request) -> dict:
    settings = _require_configured()
    redirect = str(request.base_url).rstrip("/") + "/login"
    try:
        auth = client(settings).sign_up(body.email.strip(), body.password, redirect_to=redirect)
    except SupabaseError as exc:
        raise _auth_error(exc) from exc
    if auth.get("access_token"):
        session.stage_tokens(request, auth)
        return {"signed_in": True, "next": "/onboarding"}
    # Email confirmation is on (Supabase's hosted default). The response is
    # the same whether or not the address already had an account, so this
    # can't be used to find out who's registered.
    return {"signed_in": False, "confirm_email": True,
            "message": f"Check {body.email.strip()} for a confirmation link, then sign in."}


@router.post("/auth/login")
def login(body: Credentials, request: Request) -> dict:
    settings = _require_configured()
    try:
        auth = client(settings).sign_in(body.email.strip(), body.password)
    except SupabaseError as exc:
        raise _auth_error(exc) from exc
    session.stage_tokens(request, auth)
    return {"signed_in": True, "next": "/dashboard"}


@router.post("/auth/session")
def adopt_session(body: TokenPair, request: Request) -> dict:
    """Tokens handed back in the URL fragment after an email confirmation.
    Verified with Supabase before they become cookies."""
    settings = _require_configured()
    try:
        client(settings).get_user(body.access_token)
    except SupabaseError as exc:
        raise HTTPException(401, "That sign-in link has expired. Sign in with your password.") from exc
    session.stage_tokens(request, body.model_dump())
    return {"signed_in": True, "next": "/onboarding"}


@router.post("/auth/logout")
def logout(request: Request) -> dict:
    current = session.current_session(request) if config.settings().supabase_configured else None
    if current is not None:
        try:
            client(config.settings()).sign_out(current.access_token)
        except SupabaseError:
            pass          # the cookies go regardless
        session.forget(current)
    session.stage_clear(request)
    return {"signed_in": False}


@router.get("/me")
def me(request: Request) -> dict:
    settings = config.settings()
    if not settings.supabase_configured:
        return {"configured": False, "user": None, "account": None}
    current = session.current_session(request)
    if current is None:
        return {"configured": True, "user": None, "account": None}
    member = session.membership(request, current)
    return {
        "configured": True,
        "user": {"id": current.user_id, "email": current.email},
        "account": ({"id": member.account_id, "name": member.account_name, "role": member.role}
                    if member else None),
        "insights_configured": settings.gemini_configured,
    }


# --------------------------------------------------------------- onboarding --

class NewAccount(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/account")
def create_account(body: NewAccount, request: Request) -> dict:
    current = _require_session(request)
    try:
        account_id = client(config.settings()).rpc("create_account", {"account_name": body.name.strip()},
                                                   current.access_token)
    except SupabaseError as exc:
        if exc.status < 500:
            raise HTTPException(422, exc.message) from exc
        raise
    session.forget(current)
    request.state.__dict__.pop("psl_membership", None)
    member = session.membership(request, current)
    return {"account": {"id": account_id, "name": member.account_name if member else body.name,
                        "role": member.role if member else "owner"}}


# ------------------------------------------------------------------ uploads --

@router.post("/uploads/inspect")
async def inspect_upload(request: Request) -> dict:
    await run_in_threadpool(_require_member, request)
    raw = await _read_upload(request)
    from . import ingest
    try:
        return await run_in_threadpool(ingest.inspect, raw)
    except ingest.IngestError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/uploads")
async def upload(
    request: Request,
    filename: str = Query(..., max_length=255),
    mapping: str = Query(..., max_length=4000, description="JSON: field -> column header"),
    date_order: Optional[str] = Query(None, pattern="^(ymd|dmy|mdy)$"),
    currency: str = Query("USD", max_length=3),
) -> dict:
    current, member = await run_in_threadpool(_require_member, request)
    try:
        chosen = json.loads(mapping)
        if not isinstance(chosen, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(422, "The column mapping wasn't valid JSON.") from exc
    currency = currency.upper()
    if currency not in CURRENCIES:
        raise HTTPException(422, "Unsupported currency.")
    raw = await _read_upload(request)
    settings = config.settings()
    try:
        return await run_in_threadpool(pipeline.process_upload, client(settings), settings, current,
                                       member, raw, filename, chosen, date_order, currency)
    except pipeline.UploadRefused as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/uploads")
def upload_history(request: Request) -> dict:
    current, member = _require_member(request)
    rows = client(config.settings()).select(
        "data_sources", current.access_token, account_id=f"eq.{member.account_id}",
        select="id,filename,status,status_reason,row_count,uploaded_at,report",
        order="uploaded_at.desc", limit="50")
    return {"uploads": [results.source_summary(r) for r in rows],
            "can_upload": member.role in pipeline.UPLOAD_ROLES}


# ------------------------------------------------------------ account data --

def _latest(request: Request):
    current, member = _require_member(request)
    sb = client(config.settings())
    source = results.latest_ready_source(sb, current.access_token, member.account_id)
    if source is None:
        raise HTTPException(404, "No finished upload yet. Upload a sales file on the Data page.")
    runs = results.runs_for(sb, current.access_token, source["id"])
    return current, member, sb, source, runs


@router.get("/account/estimates")
def account_estimates(request: Request) -> dict:
    _, member, _, source, runs = _latest(request)
    payload = results.estimates_payload(source, runs)
    payload["account"] = {"id": member.account_id, "name": member.account_name}
    return payload


@router.get("/account/catalog")
def account_catalog(request: Request) -> dict:
    current, _, sb, source, runs = _latest(request)
    reported = [r["category"] for r in runs if r["category"] is not None]
    excluded = [e["category"] for e in (source.get("report") or {}).get("excluded_categories", [])]
    return results.catalog_payload(sb, current.access_token, source, reported, excluded)


@router.get("/account/benchmarks")
def account_benchmarks(request: Request) -> dict:
    from ..api import BENCHMARKS          # the public artefact, loaded once at startup
    _, member, _, source, runs = _latest(request)
    overall = results.estimates_payload(source, runs)["overall"]
    return results.benchmarks_payload(BENCHMARKS, member.account_name, overall, source)


# ----------------------------------------------------------------- insights --

def _insight_view(row: dict | None) -> dict | None:
    if row is None:
        return None
    grounding = row.get("grounding") or {}
    return {"id": row["id"], "elasticity_run_id": row["elasticity_run_id"], "model": row["model"],
            "created_at": row["created_at"], "body": row["body"],
            "source": grounding.get("source"), "tier": grounding.get("tier"),
            "items": grounding.get("items", []), "input": grounding.get("input", []),
            "run_ids": grounding.get("run_ids", []),
            "attempts": [{"ok": a.get("ok"), "problem": a.get("problem")} for a in grounding.get("attempts", [])]}


def _insights_payload(request: Request, insight: dict | None) -> dict:
    current, member, sb, source, runs = _latest(request)
    previous = results.previous_ready_source(sb, current.access_token, member.account_id, source["uploaded_at"])
    since = None
    if previous is not None:
        since = {"previous_upload": results.source_summary(previous),
                 "comparisons": results.compare_runs(results.runs_for(sb, current.access_token, previous["id"]),
                                                     runs)}
    settings = config.settings()
    return {
        "insight": _insight_view(insight),
        "runs": runs,
        "data_source": results.source_summary(source),
        "since_last_upload": since,
        "llm": {"configured": settings.gemini_configured, "model": llm.model_name(), "tier": llm.tier()},
        "can_regenerate": member.role in pipeline.UPLOAD_ROLES,
    }


def _latest_insight(sb, token: str, runs: list[dict]) -> dict | None:
    overall = next((r for r in runs if r["category"] is None), None)
    if overall is None:
        return None
    rows = sb.select("insights", token, elasticity_run_id=f"eq.{overall['id']}",
                     order="created_at.desc", limit="1")
    return rows[0] if rows else None


@router.get("/account/insights")
def get_insights(request: Request) -> dict:
    current, _, sb, _, runs = _latest(request)
    return _insights_payload(request, _latest_insight(sb, current.access_token, runs))


@router.post("/account/insights")
def create_insights(request: Request, regenerate: bool = False) -> dict:
    """Write recommendations for the latest upload -- once. Asking again
    returns the stored ones; `regenerate` (owner/manage only) writes afresh."""
    from . import insights
    from .supabase import SERVICE

    current, member, sb, source, runs = _latest(request)
    existing = _latest_insight(sb, current.access_token, runs)
    if existing is not None and not regenerate:
        return _insights_payload(request, existing)
    if regenerate and member.role not in pipeline.UPLOAD_ROLES:
        raise HTTPException(403, "Only the account's owner or a manager can rewrite insights.")
    overall = next(r for r in runs if r["category"] is None)
    settings = config.settings()
    result, grounding = insights.write(runs, settings.gemini_api_key or None)
    row = sb.insert("insights", {
        "account_id": member.account_id,
        "elasticity_run_id": overall["id"],
        "body": result.body,
        "model": result.model,
        "grounding": grounding,
    }, SERVICE)[0]
    return _insights_payload(request, row)
