"""
Environment configuration for the account features.

Read once per process from os.environ -- on Vercel, the project's
environment variables; locally, whatever `.env.local` was exported into
the shell (see .env.example). Nothing here has a default value that would
work against a real project: an unset variable means the feature is off,
and /health says so, rather than the app guessing.

The names follow .env.example. NEXT_PUBLIC_* is kept for compatibility with
the Vercel <-> Supabase integration, which writes those names; this app
reads them on the server only and never ships a key to the browser. The
unprefixed names the integration also writes are accepted as fallbacks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str          # legacy anon JWT, or an sb_publishable_ key
    supabase_service_key: str       # legacy service_role JWT, or an sb_secret_ key
    gemini_api_key: str
    gemini_model: str
    storage_bucket: str
    cookie_secure: bool

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key and self.supabase_service_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)


def load() -> Settings:
    return Settings(
        supabase_url=_first("NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL").rstrip("/"),
        supabase_anon_key=_first("NEXT_PUBLIC_SUPABASE_ANON_KEY", "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
                                 "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY"),
        supabase_service_key=_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"),
        gemini_api_key=_first("GEMINI_API_KEY"),
        gemini_model=_first("GEMINI_MODEL"),
        storage_bucket=_first("SUPABASE_STORAGE_BUCKET") or "sales-uploads",
        # Secure cookies need HTTPS; plain-http localhost opts out explicitly.
        cookie_secure=_first("PSL_INSECURE_COOKIES") != "1",
    )


_settings: Settings | None = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load()
    return _settings


def reset() -> None:
    """Tests change the environment between cases."""
    global _settings
    _settings = None
