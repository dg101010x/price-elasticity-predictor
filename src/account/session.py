"""
Browser sessions: Supabase tokens in httpOnly cookies, handled server-side.

The page never sees a token. Sign-in posts credentials to this server, which
exchanges them with Supabase Auth and sets two cookies -- the access token
(an hour) and the refresh token -- as HttpOnly, Secure, SameSite=Lax. Every
request that needs a user resolves the access token against Supabase's
/auth/v1/user, which also catches a session that was signed out elsewhere;
the answer is cached briefly so a page that makes six API calls doesn't
make six auth calls. An expired access token is refreshed transparently and
the new cookies ride back on whatever response the request produces.

CSRF: SameSite=Lax keeps the cookies off cross-site POSTs, and
reject_cross_site() refuses any state-changing request a browser labels
cross-site, as a second line.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import Response

from . import config
from .supabase import SupabaseError, client

ACCESS_COOKIE = "psl_at"
REFRESH_COOKIE = "psl_rt"
REFRESH_MAX_AGE = 60 * 60 * 24 * 60      # 60 days; Supabase refresh tokens don't expire on their own

_USER_TTL = 60.0
_ACCOUNT_TTL = 30.0


@dataclass
class Session:
    user_id: str
    email: str
    access_token: str


@dataclass
class Membership:
    account_id: str
    account_name: str
    role: str


class _TTLCache:
    def __init__(self, ttl: float, size: int = 2048):
        self.ttl, self.size = ttl, size
        self._items: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            self._items.pop(key, None)
            return None

    def put(self, key: str, value) -> None:
        with self._lock:
            if len(self._items) >= self.size:
                self._items.clear()
            self._items[key] = (time.monotonic() + self.ttl, value)

    def drop(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


_users = _TTLCache(_USER_TTL)
_memberships = _TTLCache(_ACCOUNT_TTL)


def _key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _jwt_exp(token: str) -> float | None:
    """The token's own expiry, read without verifying it -- only to decide
    whether to refresh before asking Supabase. Verification is Supabase's."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


# ----------------------------------------------------------------- cookies --

def stage_tokens(request: Request, auth: dict) -> None:
    """Queue fresh cookies from a Supabase token response for this request's
    response (applied by apply_staged_cookies)."""
    request.state.psl_set_tokens = {
        "access_token": auth["access_token"],
        "refresh_token": auth["refresh_token"],
        "expires_in": int(auth.get("expires_in") or 3600),
    }
    request.state.psl_clear_tokens = False


def stage_clear(request: Request) -> None:
    request.state.psl_clear_tokens = True
    request.state.psl_set_tokens = None


def apply_staged_cookies(request: Request, response: Response) -> None:
    secure = config.settings().cookie_secure
    tokens = getattr(request.state, "psl_set_tokens", None)
    if tokens:
        response.set_cookie(ACCESS_COOKIE, tokens["access_token"], max_age=tokens["expires_in"],
                            httponly=True, secure=secure, samesite="lax", path="/")
        response.set_cookie(REFRESH_COOKIE, tokens["refresh_token"], max_age=REFRESH_MAX_AGE,
                            httponly=True, secure=secure, samesite="lax", path="/")
    elif getattr(request.state, "psl_clear_tokens", False):
        for name in (ACCESS_COOKIE, REFRESH_COOKIE):
            response.delete_cookie(name, path="/", secure=secure, httponly=True, samesite="lax")


# ----------------------------------------------------------------- lookups --

def current_session(request: Request) -> Session | None:
    """The signed-in user, or None. Memoised per request."""
    if hasattr(request.state, "psl_session"):
        return request.state.psl_session
    session = _resolve(request)
    request.state.psl_session = session
    return session


def _resolve(request: Request) -> Session | None:
    settings = config.settings()
    if not settings.supabase_configured:
        return None
    access = request.cookies.get(ACCESS_COOKIE)
    refresh = request.cookies.get(REFRESH_COOKIE)
    if not access and not refresh:
        return None
    sb = client(settings)

    if access:
        exp = _jwt_exp(access)
        if exp is None or exp - time.time() > 30:
            cached = _users.get(_key(access))
            if cached is not None:
                return cached
            try:
                user = sb.get_user(access)
                session = Session(user["id"], user.get("email") or "", access)
                _users.put(_key(access), session)
                return session
            except SupabaseError as exc:
                if exc.status >= 500:
                    raise
                # 401/403: expired or revoked -- try the refresh token below.

    if refresh:
        try:
            auth = sb.refresh(refresh)
        except SupabaseError as exc:
            if exc.status >= 500:
                raise
            stage_clear(request)
            return None
        stage_tokens(request, auth)
        user = auth.get("user") or sb.get_user(auth["access_token"])
        session = Session(user["id"], user.get("email") or "", auth["access_token"])
        _users.put(_key(auth["access_token"]), session)
        return session

    stage_clear(request)
    return None


def membership(request: Request, session: Session) -> Membership | None:
    """The user's account (v1: exactly one). Read with the user's own token,
    so it is RLS -- not this code -- that decides it's theirs."""
    if hasattr(request.state, "psl_membership"):
        return request.state.psl_membership
    cached = _memberships.get(session.user_id)
    if cached is None:
        rows = client(config.settings()).select(
            "account_memberships", session.access_token,
            select="role,created_at,account:accounts(id,name)",
            user_id=f"eq.{session.user_id}", order="created_at.asc", limit="1")
        cached = (Membership(rows[0]["account"]["id"], rows[0]["account"]["name"], rows[0]["role"])
                  if rows else False)
        _memberships.put(session.user_id, cached)
    result = cached or None
    request.state.psl_membership = result
    return result


def forget(session: Session | None) -> None:
    if session is None:
        return
    _users.drop(_key(session.access_token))
    _memberships.drop(session.user_id)


def clear_caches() -> None:
    _users.clear()
    _memberships.clear()


# -------------------------------------------------------------------- CSRF --

def is_cross_site(request: Request) -> bool:
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        return True
    origin = request.headers.get("origin")
    if origin and origin != "null":
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        return origin.split("://", 1)[-1].rstrip("/") != host
    return False
