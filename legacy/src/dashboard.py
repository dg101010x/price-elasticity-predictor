"""
Serves the dashboard as a single self-contained HTML document.

The markup, styles and behaviour live in real files under src/web/ so they can
be edited, linted and diffed like frontend code -- they used to be one 460-line
Python string literal. This module inlines them at request time (cached after
the first read in production) so the page still ships as one response with no
external requests: no CDN, no font fetch, no second round-trip. That matters
here because the previous build hard-depended on cdn.plot.ly, and every chart
died with an uncaught "Plotly is not defined" wherever that host was blocked.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_WEB_DIR = Path(__file__).resolve().parent / "web"

# Re-read the source files on every request during local development so edits
# show up on refresh; cache them in production where they never change.
_RELOAD = os.environ.get("PEP_DEV_RELOAD") == "1"


def _build() -> str:
    html = (_WEB_DIR / "index.html").read_text(encoding="utf-8")
    css = (_WEB_DIR / "app.css").read_text(encoding="utf-8")
    js = (_WEB_DIR / "app.js").read_text(encoding="utf-8")

    if "/*__APP_CSS__*/" not in html or "/*__APP_JS__*/" not in html:
        raise RuntimeError("src/web/index.html is missing its CSS or JS placeholder")

    return html.replace("/*__APP_CSS__*/", css).replace("/*__APP_JS__*/", js)


@lru_cache(maxsize=1)
def _build_cached() -> str:
    return _build()


def render_dashboard() -> str:
    return _build() if _RELOAD else _build_cached()


# Kept so `from .dashboard import DASHBOARD_HTML` still works for anything
# importing the old name.
def __getattr__(name: str) -> str:
    if name == "DASHBOARD_HTML":
        return render_dashboard()
    raise AttributeError(name)
