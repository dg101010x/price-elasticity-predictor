"""
The smallest Supabase client this app needs, over plain HTTP.

No supabase-py: the deployment ships only what it uses, and the four APIs
touched here are a handful of endpoints each.

  Auth (GoTrue)   /auth/v1/signup, /token?grant_type=password|refresh_token,
                  /logout, /user
  Data (PostgREST) /rest/v1/<table>, /rest/v1/rpc/<function>
  Storage          /storage/v1/object/<bucket>/<path>

Every Data and Storage call is made either *as the signed-in user* (their
access token in Authorization, so row-level security decides what they
see) or *as the service role* (the server's own key, which bypasses RLS).
The service role is used only for writes the schema reserves for the
server -- observations, fitted runs, insights, status updates -- and only
after the user's own request has proved membership of the account.

Keys: works with both the legacy anon/service_role JWTs and the newer
sb_publishable_/sb_secret_ keys. The new keys are not JWTs and go in the
`apikey` header only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings

SERVICE = object()          # sentinel: act as the service role, not a user


class SupabaseError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _error_from(response: httpx.Response) -> SupabaseError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    # GoTrue: {"code": 400, "error_code": "...", "msg": "..."} (or code/message
    # with the 2024-01-01 API version); PostgREST: {"code": "42501", "message"};
    # Storage: {"statusCode": "403", "error": "...", "message": "..."}.
    code = body.get("error_code") or body.get("code") or body.get("error") or ""
    message = (body.get("msg") or body.get("message") or body.get("error_description")
               or body.get("error") or response.text[:200] or response.reason_phrase)
    return SupabaseError(response.status_code, str(code), str(message))


@dataclass
class Supabase:
    settings: Settings
    http: httpx.Client

    @classmethod
    def create(cls, settings: Settings, transport: httpx.BaseTransport | None = None) -> "Supabase":
        return cls(settings, httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0), transport=transport))

    # ------------------------------------------------------------ headers --
    def _headers(self, token: Any) -> dict[str, str]:
        if token is SERVICE:
            key = self.settings.supabase_service_key
            headers = {"apikey": key}
            if not key.startswith("sb_"):
                headers["Authorization"] = f"Bearer {key}"
            return headers
        headers = {"apikey": self.settings.supabase_anon_key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.settings.supabase_url}{path}"

    def _send(self, method: str, path: str, token: Any, **kwargs) -> httpx.Response:
        headers = self._headers(token)
        headers.update(kwargs.pop("headers", {}) or {})
        response = self.http.request(method, self._url(path), headers=headers, **kwargs)
        if response.status_code >= 400:
            raise _error_from(response)
        return response

    # --------------------------------------------------------------- auth --
    def sign_up(self, email: str, password: str, redirect_to: str | None = None) -> dict:
        """Returns a session when email confirmation is off; a bare user
        (no access_token) when it's on, which is the hosted default."""
        params = {"redirect_to": redirect_to} if redirect_to else None
        return self._send("POST", "/auth/v1/signup", None, params=params,
                          json={"email": email, "password": password}).json()

    def sign_in(self, email: str, password: str) -> dict:
        return self._send("POST", "/auth/v1/token", None, params={"grant_type": "password"},
                          json={"email": email, "password": password}).json()

    def refresh(self, refresh_token: str) -> dict:
        return self._send("POST", "/auth/v1/token", None, params={"grant_type": "refresh_token"},
                          json={"refresh_token": refresh_token}).json()

    def sign_out(self, access_token: str) -> None:
        # scope=local ends this browser's session only, not every device's.
        self._send("POST", "/auth/v1/logout", access_token, params={"scope": "local"})

    def get_user(self, access_token: str) -> dict:
        return self._send("GET", "/auth/v1/user", access_token).json()

    # --------------------------------------------------------------- data --
    def select(self, table: str, token: Any, **params: str) -> list[dict]:
        return self._send("GET", f"/rest/v1/{table}", token, params=params).json()

    def insert(self, table: str, rows: dict | list[dict], token: Any, returning: bool = True) -> list[dict]:
        prefer = "return=representation" if returning else "return=minimal"
        response = self._send("POST", f"/rest/v1/{table}", token, json=rows,
                              headers={"Prefer": prefer})
        return response.json() if returning else []

    def update(self, table: str, values: dict, token: Any, **filters: str) -> list[dict]:
        if not filters:
            raise ValueError("refusing an unfiltered update")
        return self._send("PATCH", f"/rest/v1/{table}", token, params=filters, json=values,
                          headers={"Prefer": "return=representation"}).json()

    def delete(self, table: str, token: Any, **filters: str) -> None:
        if not filters:
            raise ValueError("refusing an unfiltered delete")
        self._send("DELETE", f"/rest/v1/{table}", token, params=filters,
                   headers={"Prefer": "return=minimal"})

    def rpc(self, function: str, args: dict, token: Any) -> Any:
        return self._send("POST", f"/rest/v1/rpc/{function}", token, json=args).json()

    # ------------------------------------------------------------ storage --
    def upload(self, bucket: str, path: str, data: bytes, content_type: str, token: Any) -> dict:
        return self._send("POST", f"/storage/v1/object/{bucket}/{quote(path)}", token, content=data,
                          headers={"Content-Type": content_type, "x-upsert": "false"},
                          timeout=httpx.Timeout(60.0, connect=5.0)).json()

    def download(self, bucket: str, path: str, token: Any) -> bytes:
        return self._send("GET", f"/storage/v1/object/authenticated/{bucket}/{quote(path)}", token,
                          timeout=httpx.Timeout(60.0, connect=5.0)).content


_client: Supabase | None = None


def client(settings: Settings) -> Supabase:
    global _client
    if _client is None or _client.settings != settings:
        _client = Supabase.create(settings)
    return _client


def reset() -> None:
    global _client
    _client = None
