"""
The signed-in pages, served the way the public page is: one self-contained
HTML response each, CSS and JS inlined, fonts from this origin, nothing
from anywhere else.

  /login                 sign in or create an account
  /onboarding            name the business, then the first upload
  /dashboard             overview: the estimate, what to do, how far to trust it
  /dashboard/products    the per-category breakdown
  /dashboard/simulator   the public what-if tool, on the account's estimates
  /dashboard/insights    every recommendation, traceable to its numbers
  /dashboard/benchmarks  the account's number among the public markets
  /dashboard/data        uploads and their history

Gating happens here, on the server, before any page is sent: no session
-> /login, no account -> /onboarding. The page's own API calls are gated
again by the API and, underneath, by row-level security.
"""

from __future__ import annotations

import html
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..dashboard import expand_partials
from . import config, pipeline, results, session
from .supabase import client

router = APIRouter()

_WEB = Path(__file__).resolve().parent.parent / "web"
_EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
_RELOAD = os.environ.get("PEP_DEV_RELOAD") == "1"

LAB_PAGES = {"overview", "products", "simulator", "benchmarks"}
NAV = (
    ("overview", "/dashboard", "Overview"),
    ("products", "/dashboard/products", "Categories"),
    ("simulator", "/dashboard/simulator", "Simulator"),
    ("insights", "/dashboard/insights", "Insights"),
    ("benchmarks", "/dashboard/benchmarks", "Other markets"),
    ("data", "/dashboard/data", "Data"),
)
# Filled per request, in one pass: a value that happens to contain another
# placeholder (a business called "{{NAV}}") is never substituted again.
_SLOTS = re.compile(r"\{\{(ACCOUNT_TOOLS|NAV|HOME|BRAND_SUB)\}\}|/\*__(CONFIG)__\*/")

TITLES = {
    "login": "Sign in", "onboarding": "Set up your account", "overview": "Overview",
    "products": "Categories", "simulator": "Simulator", "insights": "Insights",
    "benchmarks": "Other markets", "data": "Your sales data",
}


def _build(page: str) -> str:
    shell = (_WEB / "account" / "shell.html").read_text(encoding="utf-8")
    body = (_WEB / "account" / "pages" / f"{page}.html").read_text(encoding="utf-8")
    css = (_WEB / "app.css").read_text(encoding="utf-8")
    account_css = (_WEB / "account.css").read_text(encoding="utf-8")
    scripts = []
    if page in LAB_PAGES:
        scripts.append((_WEB / "app.js").read_text(encoding="utf-8"))
    scripts.append((_WEB / "dash.js").read_text(encoding="utf-8"))

    out = shell.replace("{{BODY}}", body)
    out = expand_partials(out)
    out = (out.replace("/*__APP_CSS__*/", css)
              .replace("/*__ACCOUNT_CSS__*/", account_css)
              .replace("/*__SCRIPTS__*/", "\n".join(f"<script>{js}</script>" for js in scripts))
              .replace("{{PAGE}}", page)
              .replace("{{TITLE}}", TITLES[page]))
    return out


@lru_cache(maxsize=None)
def _build_cached(page: str) -> str:
    return _build(page)


def _template(page: str) -> str:
    return _build(page) if _RELOAD else _build_cached(page)


def _nav(active: str) -> str:
    current = ' aria-current="page"'
    links = "".join(f'<a href="{href}"{current if key == active else ""}>{label}</a>'
                    for key, href, label in NAV)
    return f'<nav class="dept-strip" aria-label="Dashboard"><div class="shell dept-inner">{links}</div></nav>'


def _safe_json(value: dict) -> str:
    # Inside <script>: no "</script>", no "<!--", whatever a business calls itself.
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render(page: str, *, cfg: dict, user_email: str | None = None,
           account_name: str | None = None, nav: bool = False) -> HTMLResponse:
    tools = '<a class="ghost-link" href="/">Public example</a>'
    if user_email:
        # The business name is already under the wordmark; this says who's signed in.
        tools = (f'<span class="acct"><span class="acct-email">{html.escape(user_email)}</span></span>'
                 '<button type="button" class="ghost-link" data-signout>Sign out</button>')
    config_blob = {"mode": "account", "page": page, "lab": page in LAB_PAGES, **cfg}
    if page in LAB_PAGES:
        config_blob.update(estimatesUrl="/api/account/estimates", catalogUrl="/api/account/catalog",
                           benchmarksUrl="/api/account/benchmarks")
    slots = {
        "ACCOUNT_TOOLS": tools,
        "NAV": _nav(page) if nav else "",
        "HOME": "/dashboard" if nav else "/",
        "BRAND_SUB": html.escape(account_name) if (nav and account_name)
                     else "Retail pricing, tested against sales history",
        "CONFIG": _safe_json(config_blob),
    }
    out = _SLOTS.sub(lambda m: slots[m.group(1) or m.group(2)], _template(page))
    return HTMLResponse(out)


def _safe_next(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/dashboard"


# ------------------------------------------------------------------- routes --

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str | None = None):
    settings = config.settings()
    if settings.supabase_configured:
        current = session.current_session(request)
        if current is not None:
            member = session.membership(request, current)
            return RedirectResponse(_safe_next(next) if member else "/onboarding", status_code=303)
    return render("login", cfg={"configured": settings.supabase_configured, "next": _safe_next(next)})


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request):
    if not config.settings().supabase_configured:
        return RedirectResponse("/login", status_code=303)
    current = session.current_session(request)
    if current is None:
        return RedirectResponse("/login?next=/onboarding", status_code=303)
    member = session.membership(request, current)
    if member is not None:
        sb = client(config.settings())
        if results.latest_ready_source(sb, current.access_token, member.account_id) is not None:
            return RedirectResponse("/dashboard", status_code=303)
    return render("onboarding", cfg={"configured": True,
                                     "account": _account_cfg(member) if member else None},
                  user_email=current.email, account_name=member.account_name if member else None)


def _account_cfg(member: session.Membership) -> dict:
    return {"name": member.account_name, "role": member.role,
            "can_upload": member.role in pipeline.UPLOAD_ROLES}


def _dashboard(page: str, request: Request):
    if not config.settings().supabase_configured:
        return RedirectResponse("/login", status_code=303)
    current = session.current_session(request)
    if current is None:
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target, safe='/')}", status_code=303)
    member = session.membership(request, current)
    if member is None:
        return RedirectResponse("/onboarding", status_code=303)
    return render(page, cfg={"configured": True, "account": _account_cfg(member)},
                  user_email=current.email, account_name=member.account_name, nav=True)


@router.get("/dashboard", response_class=HTMLResponse)
def overview_page(request: Request):
    return _dashboard("overview", request)


@router.get("/dashboard/products", response_class=HTMLResponse)
def products_page(request: Request):
    return _dashboard("products", request)


@router.get("/dashboard/simulator", response_class=HTMLResponse)
def simulator_page(request: Request):
    return _dashboard("simulator", request)


@router.get("/dashboard/insights", response_class=HTMLResponse)
def insights_page(request: Request):
    return _dashboard("insights", request)


@router.get("/dashboard/benchmarks", response_class=HTMLResponse)
def benchmarks_page(request: Request):
    return _dashboard("benchmarks", request)


@router.get("/dashboard/data", response_class=HTMLResponse)
def data_page(request: Request):
    return _dashboard("data", request)


EXAMPLE_FILES = {"sample_gift_shop_weekly.csv", "sample_coffee_roaster_daily.csv"}


@router.get("/examples/{name}")
def example_file(name: str) -> FileResponse:
    """Two synthetic sales histories (tests/synthetic_sales.py) to try the
    uploader with. Made up, and labelled as such in their own names."""
    path = _EXAMPLES / name
    if name not in EXAMPLE_FILES or not path.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="text/csv", filename=name)
