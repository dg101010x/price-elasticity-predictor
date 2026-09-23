"""
The signed-in product in a real browser: sign-up, onboarding, the uploader
and its mapping step, the dashboard pages, and tracing a recommendation's
numbers -- against the local Supabase stand-in (tests/supabase_gateway.py)
with the app served over HTTP.

Skips without Chromium, Postgres server binaries or PostgREST.
"""

from __future__ import annotations

import os
import threading
import time

import httpx
import pytest
import uvicorn

from src.account import config, session, supabase
from tests.local_supabase import free_port
from tests.supabase_gateway import start_fake_supabase
from tests.synthetic_sales import GIFT_SHOP, make_sales_csv

pytestmark = pytest.mark.browser
pytest.importorskip("psycopg", reason="psycopg is not installed")

PASSWORD = "correct horse battery staple"
ENV_KEYS = ("NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY",
            "PSL_INSECURE_COOKIES", "GEMINI_API_KEY")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def stack():
    fake, reason = start_fake_supabase(confirm_email=True)
    if fake is None:
        pytest.skip(reason)
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    os.environ.update({"NEXT_PUBLIC_SUPABASE_URL": fake.url, "NEXT_PUBLIC_SUPABASE_ANON_KEY": fake.anon_key,
                       "SUPABASE_SERVICE_ROLE_KEY": fake.service_key, "PSL_INSECURE_COOKIES": "1"})
    os.environ.pop("GEMINI_API_KEY", None)
    config.reset(); supabase.reset(); session.clear_caches()
    from src.api import app
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(f"{base}/health", trust_env=False, timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield {"fake": fake, "base": base}
    server.should_exit = True
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    config.reset(); supabase.reset(); session.clear_caches()
    fake.stop()
    fake.db.stop()


def _page(browser, width=1280, height=900):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
    return context, page


def _sign_up_and_in(page, stack, email):
    base = stack["base"]
    page.goto(f"{base}/login")
    page.click('[data-auth-mode="signup"]')
    page.fill("#auth-email", email)
    page.fill("#auth-password", PASSWORD)
    page.click("#auth-submit")
    page.wait_for_selector("#auth-message:not([hidden])")
    assert "confirmation link" in page.text_content("#auth-message")
    stack["fake"].confirm(email)
    page.fill("#auth-password", PASSWORD)
    page.click("#auth-submit")
    page.wait_for_url("**/onboarding")


@pytest.fixture(scope="module")
def onboarded(browser, stack, tmp_path_factory):
    """One business taken all the way through onboarding in the browser."""
    context, page = _page(browser)
    _sign_up_and_in(page, stack, "shop@example.com")
    page.fill("#business-name", "Harbour & Co")
    page.click("#name-submit")
    page.wait_for_selector("#step-upload:not([hidden])")
    path = tmp_path_factory.mktemp("csv") / "harbour-sales.csv"
    path.write_bytes(make_sales_csv(GIFT_SHOP, seed=5))
    page.set_input_files("#file-input", str(path))
    page.wait_for_selector("#mapping:not([hidden])")
    page.click("#upload-button")
    page.wait_for_selector("#upload-result:not([hidden])", timeout=60000)
    result_text = page.text_content("#upload-result")
    page.click("#upload-result a.btn-primary")
    page.wait_for_url("**/dashboard")
    yield {"context": context, "page": page, "result_text": result_text}
    context.close()


# ---------------------------------------------------------------- gating --

def test_signed_out_visitors_are_sent_to_sign_in(browser, stack):
    context, page = _page(browser)
    page.goto(f"{stack['base']}/dashboard/insights")
    assert page.url.endswith("/login?next=/dashboard/insights")
    assert page.is_visible("#auth-form")
    context.close()


def test_the_public_page_still_works_and_links_in(browser, stack):
    context, page = _page(browser)
    page.goto(stack["base"] + "/")
    page.wait_for_selector("#compare-chart svg")
    assert page.is_visible('a[href="/login"]')
    assert page.errors == []
    context.close()


# ------------------------------------------------------------ onboarding --

def test_onboarding_ends_with_a_fitted_upload(onboarded):
    assert "Fitted." in onboarded["result_text"]
    assert "Greeting Cards has no estimate of its own" in onboarded["result_text"]


def test_overview_leads_with_the_number_and_its_range(onboarded):
    page = onboarded["page"]
    page.wait_for_selector("#headline-ticket")
    figure = page.text_content(".ticket-figure")
    assert figure.startswith("−") and "." in figure
    assert page.text_content(".ticket-range").startswith("likely ")
    assert "R²" in page.text_content(".ticket-meta")
    assert page.text_content("#verdict-text").strip()
    assert page.query_selector("#scale-chart svg") is not None


def test_overview_shows_two_or_three_recommendations(onboarded):
    page = onboarded["page"]
    page.wait_for_selector("#overview-insights li")
    count = len(page.query_selector_all("#overview-insights > li"))
    assert 2 <= count <= 3
    assert page.query_selector_all("#overview-insights .num-tag")


def test_methodology_is_there_but_collapsed(onboarded):
    page = onboarded["page"]
    assert page.is_hidden("#method-spec")
    page.click(".method-disclosure > summary")
    assert page.is_visible("#method-categories")
    assert "category column" in page.text_content("#method-categories")
    assert len(page.query_selector_all("#glossary-list > div")) == 6
    assert "Revenue is not profit" in page.text_content(".method-body")


def test_a_number_in_a_recommendation_traces_to_its_estimate(onboarded):
    page = onboarded["page"]
    page.goto(page.url.split("/dashboard")[0] + "/dashboard/insights")
    page.wait_for_selector("#insight-list .num-tag")
    tag = page.query_selector("#insight-list .num-tag")
    text = tag.text_content()
    tag.click()
    assert page.is_visible("#trace-pop")
    assert page.text_content("#trace-pop-title") == f"Where {text} comes from"
    lit = page.query_selector_all("#grounding-table [data-lit=true]")
    assert lit and any(c.text_content() == text for c in lit), "the source cell lights up"
    page.keyboard.press("Escape")
    assert page.is_hidden("#trace-pop")
    assert page.evaluate("document.activeElement.classList.contains('num-tag')"), "focus returns to the tag"


def test_insights_say_how_they_were_written(onboarded):
    page = onboarded["page"]
    text = page.text_content("#insight-provenance")
    assert "fixed template" in text and "No AI model is set up" in text


def test_categories_page_explains_what_was_left_out(onboarded):
    page = onboarded["page"]
    base = page.url.split("/dashboard")[0]
    page.goto(base + "/dashboard/products")
    page.wait_for_selector("#compare-chart svg")
    assert page.is_visible("#excluded-card")
    assert "Greeting Cards" in page.text_content("#excluded-list")
    bars = page.query_selector_all("#compare-chart rect.chart-hit")
    names = page.eval_on_selector_all("#compare-chart rect.chart-hit", "els => els.map(e => e.getAttribute('aria-label'))")
    candles = next(i for i, n in enumerate(names) if n.startswith("Candles"))
    bars[candles].click()
    page.wait_for_url("**/dashboard/simulator?scope=category&category=Candles")
    page.wait_for_selector("#scenario-tiles .tile")
    assert page.text_content("#verdict-scope") == "Candles"


def test_the_simulator_runs_on_the_accounts_own_numbers(onboarded):
    page = onboarded["page"]
    page.goto(page.url.split("/dashboard")[0] + "/dashboard/simulator")
    page.wait_for_selector("#scenario-tiles .tile")
    assert page.text_content("#price-symbol") == "$"
    page.click('.quick-changes button[data-change="-10"]')
    revenue = page.eval_on_selector_all(
        ".tile", "els => els.filter(e => e.querySelector('.tile-label').textContent === 'Revenue')"
                 ".map(e => e.querySelector('.tile-value').textContent)[0]")
    assert revenue.startswith("+"), "an elastic catalogue's revenue rises on a cut"


def test_benchmarks_place_the_business_among_the_markets(onboarded):
    page = onboarded["page"]
    page.goto(page.url.split("/dashboard")[0] + "/dashboard/benchmarks")
    page.wait_for_selector("#benchmark-card:not([hidden]) #benchmark-chart svg")
    labels = page.eval_on_selector_all("#benchmark-chart text.chart-strong", "els => els.map(e => e.textContent)")
    assert "Harbour & Co" in labels
    assert len(page.query_selector_all("#benchmark-chart rect.chart-hit")) >= 14


def test_data_page_lists_the_upload(onboarded):
    page = onboarded["page"]
    page.goto(page.url.split("/dashboard")[0] + "/dashboard/data")
    page.wait_for_selector("#history table")
    row = page.text_content("#history tbody tr")
    assert "harbour-sales.csv" in row and "Ready" in row


def test_ambiguous_dates_must_be_settled_before_upload(onboarded, tmp_path):
    page = onboarded["page"]
    page.goto(page.url.split("/dashboard")[0] + "/dashboard/data")
    lines = make_sales_csv({"Beans": (16, -1.0)}, seed=4, weeks=10, date_format="%d/%m/%Y").decode().splitlines()
    keep = [l for l in lines[1:] if int(l.split(",")[0].split("/")[0]) <= 12]
    path = tmp_path / "ambiguous.csv"
    path.write_text("\n".join([lines[0]] + keep) + "\n")
    page.set_input_files("#file-input", str(path))
    page.wait_for_selector("#mapping:not([hidden])")
    assert page.is_visible("#date-order-field")
    assert page.is_visible("#mapping-warning")
    page.click("#upload-button")
    assert "day first or month first" in page.text_content("#upload-error")
    page.check('input[name="date-order"][value="dmy"]')
    page.click("#upload-button")
    page.wait_for_selector("#upload-result:not([hidden])", timeout=60000)


@pytest.mark.parametrize("path", ["/dashboard", "/dashboard/products", "/dashboard/simulator",
                                  "/dashboard/insights", "/dashboard/benchmarks", "/dashboard/data"])
def test_pages_fit_a_phone_and_raise_no_errors(browser, onboarded, path):
    cookies = onboarded["context"].cookies()
    base = onboarded["page"].url.split("/dashboard")[0]
    context = browser.new_context(viewport={"width": 360, "height": 780}, has_touch=True, is_mobile=True)
    context.add_cookies(cookies)
    page = context.new_page()
    errors, external = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("request", lambda r: external.append(r.url) if not r.url.startswith((base, "data:")) else None)
    page.goto(base + path, wait_until="networkidle")
    page.wait_for_timeout(300)
    sw, cw = page.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    context.close()
    assert sw <= cw + 1, f"{path} scrolls sideways at 360px ({sw} > {cw})"
    assert errors == [], errors
    assert external == [], f"{path} reached off-origin: {external}"


def test_sign_out_returns_to_sign_in(browser, onboarded):
    cookies = onboarded["context"].cookies()
    base = onboarded["page"].url.split("/dashboard")[0]
    context = browser.new_context()
    context.add_cookies(cookies)
    page = context.new_page()
    page.goto(base + "/dashboard/data")
    page.click("[data-signout]")
    page.wait_for_url("**/login")
    page.goto(base + "/dashboard")
    assert "/login" in page.url
    context.close()
