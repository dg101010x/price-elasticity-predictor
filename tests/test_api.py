"""
API contract tests.

The record-level endpoints (/elasticity, /categories, /products, /methodology,
/health) predate the redesign and their existing fields are asserted here so
the rewrite can't quietly break an existing consumer. The decision-level ones
(/estimates, /catalog, /scenario) are new in 2.0.
"""

import re

import pytest
from fastapi.testclient import TestClient

from src.api import ELASTICITY_RESULTS, PRODUCTS, app

client = TestClient(app)


# ------------------------------------------------------- unchanged contract --

def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["using_stub_data"] is False, "tests expect the real artifacts to be present"


def test_elasticity_overall_keeps_its_original_fields():
    body = client.get("/elasticity").json()
    for key in ("scope", "elasticity", "std_error", "ci_low", "ci_high", "r_squared",
                "n_observations", "interpretation",
                "pct_quantity_change_for_10pct_price_increase", "caveat"):
        assert key in body, f"{key} disappeared from the /elasticity contract"
    assert body["scope"] == "overall"


def test_elasticity_by_category():
    name = ELASTICITY_RESULTS["by_category"][0]["category"]
    body = client.get("/elasticity", params={"category": name}).json()
    assert body["scope"] == name


def test_elasticity_unknown_category_is_404():
    assert client.get("/elasticity", params={"category": "Nope"}).status_code == 404


def test_elasticity_by_product_resolves_to_its_category():
    product = next(p for p in PRODUCTS if p["category"] != "Other/Uncategorized")
    body = client.get("/elasticity", params={"product_id": product["product_id"]}).json()
    assert body["resolved_from_product_id"] == product["product_id"]
    assert body["scope"] == product["category"]


def test_product_in_an_unreported_category_falls_back_to_overall():
    """Regression guard: these used to 404 on a perfectly valid product."""
    product = next(p for p in PRODUCTS if p["category"] == "Other/Uncategorized")
    body = client.get("/elasticity", params={"product_id": product["product_id"]}).json()
    assert body["scope"] == "overall"
    assert body["resolved_from_product_id"] == product["product_id"]


def test_elasticity_unknown_product_is_404():
    assert client.get("/elasticity", params={"product_id": "nope"}).status_code == 404


def test_elasticity_rejects_a_non_positive_price():
    assert client.get("/elasticity", params={"price": 0}).status_code == 422
    assert client.get("/elasticity", params={"price": -3}).status_code == 422


def test_elasticity_echoes_the_ten_percent_price():
    body = client.get("/elasticity", params={"price": 10}).json()
    assert body["price"] == 10
    assert body["price_after_10pct_increase"] == pytest.approx(11.0)


def test_categories_lists_reported_and_excluded():
    body = client.get("/categories").json()
    assert body["reported"] == sorted(body["reported"])
    assert all("category" in e and "reason" in e for e in body["excluded"])


def test_products_filter_and_limit():
    name = ELASTICITY_RESULTS["by_category"][0]["category"]
    body = client.get("/products", params={"category": name}).json()
    assert body["count"] > 0
    assert all(p["category"] == name for p in body["products"])
    assert len(client.get("/products", params={"limit": 3}).json()["products"]) == 3


def test_products_search():
    body = client.get("/products", params={"q": "cakestand"}).json()
    assert body["count"] > 0
    assert all("cakestand" in p["product_name"].lower() for p in body["products"])


def test_methodology_has_a_note():
    assert "note" in client.get("/methodology").json()


# ------------------------------------------------------------ decision layer --

def test_estimates_returns_everything_in_one_payload():
    body = client.get("/estimates").json()
    assert body["revenue_breakeven_elasticity"] == -1.0
    assert len(body["by_category"]) == len(ELASTICITY_RESULTS["by_category"])
    # sorted most price-sensitive first, so the chart doesn't have to re-sort
    values = [r["elasticity"] for r in body["by_category"]]
    assert values == sorted(values)


def test_every_estimate_carries_advice_and_evidence():
    body = client.get("/estimates").json()
    for row in [body["overall"]] + body["by_category"]:
        assert set(row["advice"]) == {"raising_price", "certain", "headline", "detail"}
        assert row["evidence"]["precision"]
        assert row["evidence"]["sample"]
        assert row["evidence"]["fit"]


def test_elasticity_also_carries_the_decision_layer():
    body = client.get("/elasticity").json()
    assert body["advice"]["headline"]
    assert body["evidence"]["n_observations"] == body["n_observations"]


def test_catalog_is_the_same_products_in_a_smaller_shape():
    body = client.get("/catalog").json()
    assert len(body["products"]) == len(PRODUCTS)
    ids = {row[0] for row in body["products"]}
    assert ids == {p["product_id"] for p in PRODUCTS}
    for product_id, name, cat_index, price in body["products"][:50]:
        assert 0 <= cat_index < len(body["categories"])
        assert isinstance(price, (int, float)) and price > 0
        assert name == name.strip(), "names should arrive ready to render"


def test_catalog_category_index_agrees_with_products():
    catalog = client.get("/catalog").json()
    by_id = {p["product_id"]: p["category"] for p in PRODUCTS}
    for product_id, _name, cat_index, _price in catalog["products"]:
        assert catalog["categories"][cat_index] == by_id[product_id]


def test_catalog_marks_which_categories_are_reported():
    body = client.get("/catalog").json()
    assert set(body["reported"]).isdisjoint(body["excluded"])
    assert set(body["reported"]) | set(body["excluded"]) <= set(body["categories"])


def test_scenario_matches_the_shared_math():
    body = client.get("/scenario", params={"pct_price_change": 10, "price": 10}).json()
    s = body["scenario"]
    assert s["pct_quantity_change"] == pytest.approx(-16.58, abs=0.01)
    assert s["pct_revenue_change"] == pytest.approx(-8.24, abs=0.01)
    assert s["new_price"] == pytest.approx(11.0)


def test_scenario_with_unit_cost_returns_profit():
    body = client.get("/scenario",
                      params={"pct_price_change": -20, "price": 10, "unit_cost": 6}).json()
    s = body["scenario"]
    assert s["pct_revenue_change"] > 0
    assert s["pct_profit_change"] < 0


@pytest.mark.parametrize("params,reason", [
    ({"pct_price_change": 10, "price": 0}, "zero price"),
    ({"pct_price_change": 10, "price": 10, "unit_cost": 10}, "cost equals price"),
    ({"pct_price_change": 10, "price": 10, "unit_cost": -1}, "negative cost"),
    ({"pct_price_change": 10, "unit_cost": 4}, "cost without price"),
])
def test_scenario_rejects_impossible_inputs(params, reason):
    assert client.get("/scenario", params=params).status_code == 422, reason


def test_scenario_rejects_a_total_price_cut():
    assert client.get("/scenario", params={"pct_price_change": -100}).status_code == 422


# ------------------------------------------------------------------- page ----

SUBRESOURCE_TAGS = ("script", "link", "img", "iframe", "source", "video", "audio", "embed")


def _subresource_urls(html: str) -> list:
    """Every URL the browser would fetch on its own to render the page.

    Deliberately excludes <a href>: a hyperlink out to the dataset's homepage
    is attribution, not a dependency.
    """
    urls = []
    for tag in SUBRESOURCE_TAGS:
        for attrs in re.findall(rf"<{tag}\b([^>]*)>", html, re.I):
            for m in re.finditer(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", attrs):
                urls.append(m.group(1))
    urls += re.findall(r"""url\(\s*["']?([^"')]+)""", html)
    return urls


def test_dashboard_is_self_contained():
    """No CDN, no external font host, no third-party subresource at all.

    The old build hard-depended on cdn.plot.ly, and every chart died with an
    uncaught "Plotly is not defined" wherever that host was blocked.
    """
    html = client.get("/").text
    assert html.startswith("<!doctype html>")

    remote = [u for u in _subresource_urls(html) if re.match(r"(?:https?:)?//", u)]
    assert not remote, f"page fetches remote subresources: {remote}"

    assert "@import" not in html, "CSS @import can reach off-origin"
    assert "<script src=" not in html, "the page should carry no external script tags"
    assert "/*__APP_CSS__*/" not in html and "/*__APP_JS__*/" not in html


def test_every_subresource_is_same_origin_or_inline():
    html = client.get("/").text
    for url in _subresource_urls(html):
        assert url.startswith(("/", "data:")), f"unexpected subresource: {url}"


def test_outbound_citation_links_are_still_allowed():
    """Attribution to the source dataset should survive the self-contained rule."""
    html = client.get("/").text
    assert 'href="https://archive.ics.uci.edu' in html


def test_dashboard_inlines_the_real_assets():
    html = client.get("/").text
    assert "Price Sensitivity Lab" in html
    assert "--accent" in html, "CSS was not inlined"
    assert "buildScenario" in html, "JS was not inlined"


def test_fonts_are_served_locally():
    r = client.get("/fonts/archivo-400-700.woff2")
    assert r.status_code == 200
    assert r.headers["content-type"] == "font/woff2"
    assert "immutable" in r.headers.get("cache-control", "")


@pytest.mark.parametrize("name", ["api.py", "../api.py", "nope.woff2", "..%2Fapi.py"])
def test_font_route_refuses_anything_but_a_bundled_font(name):
    assert client.get(f"/fonts/{name}").status_code == 404


def test_api_index_lists_the_new_endpoints():
    endpoints = client.get("/api").json()["endpoints"]
    for path in ("/elasticity", "/scenario", "/estimates", "/catalog"):
        assert path in endpoints


def test_large_responses_are_compressed():
    """/catalog is ~233KB uncompressed; it should never go over the wire that way."""
    for path in ("/", "/catalog", "/estimates"):
        r = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200
        assert r.headers.get("content-encoding") == "gzip", f"{path} was not compressed"


def test_clients_without_gzip_still_get_a_readable_response():
    r = client.get("/estimates", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert r.json()["revenue_breakeven_elasticity"] == -1.0
