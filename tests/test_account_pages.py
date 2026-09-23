"""
The signed-in pages as documents: self-contained like the public page,
safe with whatever a business calls itself, and gated before they're sent.
No Supabase needed -- these render the templates directly.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from src.account import pages, results
from src.api import app
from tests.test_api import _subresource_urls

client = TestClient(app)
ALL_PAGES = ["login", "onboarding", "overview", "products", "simulator", "insights", "benchmarks", "data"]


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_is_self_contained(page):
    html = pages.render(page, cfg={"configured": True}, user_email="a@b.c", account_name="Shop",
                        nav=page not in ("login", "onboarding")).body.decode()
    assert html.startswith("<!doctype html>")
    remote = [u for u in _subresource_urls(html) if re.match(r"(?:https?:)?//", u)]
    assert not remote, f"{page} fetches remote subresources: {remote}"
    assert "<script src=" not in html and "@import" not in html
    for marker in ("<!--@partial", "{{", "/*__"):
        assert marker not in html, f"{page} left a template marker: {marker}"


@pytest.mark.parametrize("page", ["overview", "products", "simulator", "benchmarks"])
def test_chart_pages_carry_the_shared_lab_script(page):
    html = pages.render(page, cfg={}, user_email="a@b.c", account_name="Shop", nav=True).body.decode()
    assert "buildScenario" in html, "app.js, the same charts as the public page"
    assert '"estimatesUrl": "/api/account/estimates"' in html


def test_a_hostile_business_name_is_inert():
    name = '{{NAV}}</script><script>alert(1)</script>/*__CONFIG__*/'
    html = pages.render("overview", cfg={"account": {"name": name}}, user_email="x@y.z",
                        account_name=name, nav=True).body.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;/script&gt;" in html                       # escaped in markup
    assert "\\u003c/script\\u003e" in html                  # escaped inside the config JSON
    assert html.count('<nav class="dept-strip"') == 1, "a placeholder inside the name isn't expanded"


def test_login_page_says_when_accounts_are_off():
    r = client.get("/login")
    assert r.status_code == 200
    assert '"configured": false' in r.text
    assert "auth-unavailable" in r.text


@pytest.mark.parametrize("path", ["/dashboard", "/dashboard/data", "/onboarding"])
def test_without_supabase_the_dashboard_sends_people_to_sign_in(path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


@pytest.mark.parametrize("value,expected", [
    ("/dashboard/insights", "/dashboard/insights"),
    ("//evil.example", "/dashboard"),
    ("https://evil.example", "/dashboard"),
    ("/\\evil.example", "/dashboard"),
    (None, "/dashboard"),
])
def test_the_next_parameter_cannot_leave_the_site(value, expected):
    assert pages._safe_next(value) == expected


def test_private_pages_are_never_cached():
    for path in ("/login", "/api/me"):
        assert client.get(path).headers["cache-control"] == "no-store"
    assert "no-store" not in client.get("/").headers.get("cache-control", "")


def test_sample_files_are_served_and_nothing_else():
    r = client.get("/examples/sample_gift_shop_weekly.csv")
    assert r.status_code == 200 and r.text.startswith("Week,SKU,")
    for bad in ("../pyproject.toml", "nope.csv", "..%2Fpyproject.toml"):
        assert client.get(f"/examples/{bad}").status_code == 404


def test_health_reports_which_features_are_switched_on():
    body = client.get("/health").json()
    assert body["accounts_configured"] is False and body["insights_configured"] is False


def test_account_api_answers_503_when_supabase_is_not_configured():
    r = client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 503


def test_results_constants_agree_with_the_estimator():
    """results.py copies three constants so the API doesn't import pandas at
    cold start; they must never drift from the estimator's."""
    from src import stats_engine
    assert results.Z95 == stats_engine.Z95
    assert results.MIN_OBS_PER_CATEGORY == stats_engine.MIN_OBS_PER_CATEGORY
    assert results.MIN_PRODUCTS_PER_CATEGORY == stats_engine.MIN_PRODUCTS_PER_CATEGORY


def test_the_public_page_does_not_load_pandas():
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-c", "import sys, src.api; print('pandas' in sys.modules)"],
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
