"""
FastAPI layer serving the elasticity estimates. Loads elasticity_results.json
and products.json once at startup -- precomputed artifacts built by
src/build_elasticity_model.py from data/csv/scanner_data.csv (see that file
for methodology). Falls back to the stub figures below only if those
artifacts are missing.

Endpoint groups
---------------
Record-level (unchanged contract):  /elasticity  /categories  /products
                                    /methodology /health      /api
Decision-level (added for the UI):  /estimates   /catalog     /scenario

The dashboard reads /estimates and /catalog exactly once at load. It used to
issue one /elasticity request per category on every interaction, which meant
~11 identical round-trips per keystroke for data that never changes.

Run: uvicorn src.api:app --reload
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .dashboard import render_dashboard
from .elasticity_math import (
    REVENUE_BREAKEVEN_ELASTICITY,
    build_scenario,
    evidence_summary,
    revenue_advice,
)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"


def _load_json(filename: str):
    path = _DATA_DIR / filename
    if path.exists():
        return json.loads(path.read_text())
    return None


# Stub data for demo (used only if the precomputed artifacts aren't present)
STUB_ELASTICITY_RESULTS = {
    "overall": {
        "elasticity": -0.743,
        "std_error": 0.045,
        "ci_low": -0.83,
        "ci_high": -0.66,
        "r_squared": 0.143,
        "n_observations": 12932,
        "interpretation": "inelastic (quantity responds less than proportionally to price)",
        "pct_quantity_change_for_10pct_price_increase": -6.8,
    },
    "by_category": [
        {
            "category": "Home Decor & Lighting",
            "elasticity": -0.743,
            "std_error": 0.045,
            "ci_low": -0.83,
            "ci_high": -0.66,
            "r_squared": 0.143,
            "n_observations": 12932,
            "interpretation": "inelastic (quantity responds less than proportionally to price)",
            "pct_quantity_change_for_10pct_price_increase": -6.8,
        },
        {
            "category": "Kitchen & Dining",
            "elasticity": -0.541,
            "std_error": 0.05,
            "ci_low": -0.59,
            "ci_high": -0.49,
            "r_squared": 0.088,
            "n_observations": 7154,
            "interpretation": "inelastic (quantity responds less than proportionally to price)",
            "pct_quantity_change_for_10pct_price_increase": -5.0,
        },
    ],
    "excluded_categories": [],
    "methodology": {"method": "log-log panel regression", "note": "descriptive only"},
}

STUB_PRODUCTS = [
    {"product_id": "85123A", "product_name": "WHITE HANGING HEART T-LIGHT HOLDER", "category": "Home Decor & Lighting", "currency": "GBP", "typical_price": 3.08},
    {"product_id": "22423", "product_name": "REGENCY CAKESTAND 3 TIER", "category": "Kitchen & Dining", "currency": "GBP", "typical_price": 14.16},
    {"product_id": "21212", "product_name": "PACK OF 72 RETROSPOT CAKE CASES", "category": "Kitchen & Dining", "currency": "GBP", "typical_price": 0.71},
    {"product_id": "20725", "product_name": "LUNCH BAG RED RETROSPOT", "category": "Kitchen & Dining", "currency": "GBP", "typical_price": 2.05},
]

_loaded_elasticity = _load_json("elasticity_results.json")
ELASTICITY_RESULTS = _loaded_elasticity or STUB_ELASTICITY_RESULTS
PRODUCTS = _load_json("products.json") or STUB_PRODUCTS
USING_STUB_DATA = _loaded_elasticity is None

_BY_CATEGORY = {r["category"]: r for r in ELASTICITY_RESULTS["by_category"]}
_EXCLUDED_NAMES = {e["category"] for e in ELASTICITY_RESULTS.get("excluded_categories", [])}

app = FastAPI(
    title="Price Elasticity Predictor API",
    description="Price-sensitivity estimates from public retail transaction data, plus the "
                "revenue arithmetic that turns them into a pricing decision. "
                "See /methodology for caveats.",
    version="2.0.0",
)

# The page inlines its own CSS and JS, and /catalog ships the whole 4,896-row
# product directory in one response, so both are large and highly compressible
# (~107KB -> ~20KB, ~233KB -> ~60KB). woff2 is already compressed and falls
# under the size threshold handling below anyway.
app.add_middleware(GZipMiddleware, minimum_size=1024)


class ElasticityResponse(BaseModel):
    scope: str
    resolved_from_product_id: Optional[str] = None
    elasticity: float
    std_error: float
    ci_low: float
    ci_high: float
    r_squared: float
    n_observations: int
    interpretation: str
    price: Optional[float] = None
    price_after_10pct_increase: Optional[float] = None
    pct_quantity_change_for_10pct_price_increase: float
    # Added in 2.0 -- the decision layer. Existing fields are untouched.
    advice: Optional[dict] = None
    evidence: Optional[dict] = None
    caveat: str = (
        "Descriptive association from observational data, not a causal effect — "
        "price is not randomly assigned in the underlying datasets. See /methodology."
    )


def _estimate_to_response(estimate: dict, scope: str, price: Optional[float],
                           resolved_from_product_id: Optional[str] = None) -> ElasticityResponse:
    return ElasticityResponse(
        scope=scope,
        resolved_from_product_id=resolved_from_product_id,
        elasticity=estimate["elasticity"],
        std_error=estimate["std_error"],
        ci_low=estimate["ci_low"],
        ci_high=estimate["ci_high"],
        r_squared=estimate["r_squared"],
        n_observations=estimate["n_observations"],
        interpretation=estimate["interpretation"],
        price=price,
        price_after_10pct_increase=round(price * 1.10, 4) if price is not None else None,
        pct_quantity_change_for_10pct_price_increase=estimate["pct_quantity_change_for_10pct_price_increase"],
        advice=revenue_advice(estimate["elasticity"], estimate["ci_low"], estimate["ci_high"]),
        evidence=evidence_summary(estimate),
    )


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return render_dashboard()


_FONT_DIR = Path(__file__).resolve().parent / "web" / "fonts"


@app.get("/fonts/{filename}")
def font(filename: str) -> FileResponse:
    """Serve the bundled webfonts.

    Self-hosted rather than loaded from fonts.gstatic.com for the same reason
    the charts no longer come from a CDN: a third-party host is one more thing
    that can be blocked or slow, and the page should look the same on a
    locked-down corporate network as it does anywhere else.
    """
    if not filename.endswith(".woff2") or "/" in filename or ".." in filename:
        raise HTTPException(status_code=404, detail="not found")
    path = _FONT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(
        path,
        media_type="font/woff2",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/api")
def api_info() -> dict:
    return {
        "name": "Price Elasticity Predictor API",
        "endpoints": [
            "/elasticity", "/scenario", "/estimates", "/categories",
            "/products", "/catalog", "/methodology", "/health",
        ],
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "using_stub_data": USING_STUB_DATA}


@app.get("/methodology")
def methodology() -> dict:
    return ELASTICITY_RESULTS["methodology"]


@app.get("/categories")
def list_categories() -> dict:
    return {
        "reported": sorted(_BY_CATEGORY.keys()),
        "excluded": ELASTICITY_RESULTS["excluded_categories"],
    }


@app.get("/estimates")
def all_estimates() -> dict:
    """Every estimate in one payload, with the decision layer attached.

    This is what the dashboard loads; it replaces one /elasticity round-trip
    per category per interaction.
    """

    def decorate(estimate: dict, scope: str) -> dict:
        out = dict(estimate)
        out["scope"] = scope
        out["advice"] = revenue_advice(estimate["elasticity"], estimate["ci_low"], estimate["ci_high"])
        out["evidence"] = evidence_summary(estimate)
        return out

    return {
        "overall": decorate(ELASTICITY_RESULTS["overall"], "overall"),
        "by_category": [
            decorate(row, row["category"])
            for row in sorted(ELASTICITY_RESULTS["by_category"], key=lambda r: r["elasticity"])
        ],
        "excluded_categories": ELASTICITY_RESULTS["excluded_categories"],
        "methodology": ELASTICITY_RESULTS["methodology"],
        "revenue_breakeven_elasticity": REVENUE_BREAKEVEN_ELASTICITY,
        "using_stub_data": USING_STUB_DATA,
    }


@app.get("/products")
def list_products(
    category: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(500, ge=1, le=10000),
) -> dict:
    """Browsable product directory with typical prices for auto-fill."""
    products = PRODUCTS
    if category is not None:
        products = [p for p in products if p["category"] == category]
    if q:
        needle = q.strip().lower()
        products = [
            p for p in products
            if needle in p["product_name"].lower() or needle in p["product_id"].lower()
        ]
    return {"count": len(products), "products": products[:limit]}


@app.get("/catalog")
def catalog() -> dict:
    """The whole product directory in a column-oriented shape, for the UI's
    client-side search box.

    Same data as /products, ~60% smaller on the wire: the category name is
    replaced by an index into `categories`, and the single currency is hoisted
    out of every row. Product names are title-cased here so 4,896 rows don't
    have to be re-cased in the browser on every keystroke.
    """
    categories = sorted({p["category"] for p in PRODUCTS})
    cat_index = {name: i for i, name in enumerate(categories)}
    currency = PRODUCTS[0]["currency"] if PRODUCTS else "GBP"
    return {
        "currency": currency,
        "categories": categories,
        "reported": sorted(_BY_CATEGORY.keys()),
        "excluded": sorted(_EXCLUDED_NAMES),
        # [product_id, title-cased name, category index, typical price]
        "products": [
            [p["product_id"], p["product_name"].strip().title(), cat_index[p["category"]], p["typical_price"]]
            for p in PRODUCTS
        ],
    }


def _resolve_estimate(category: Optional[str], product_id: Optional[str]):
    """Shared lookup for /elasticity and /scenario. Returns (estimate, scope)."""
    if category is None and product_id is None:
        return ELASTICITY_RESULTS["overall"], "overall"

    resolved_from_product = False
    if category is None and product_id is not None:
        product = next((p for p in PRODUCTS if p["product_id"] == product_id), None)
        if product is None:
            raise HTTPException(status_code=404, detail=f"product_id '{product_id}' not found")
        category = product["category"]
        resolved_from_product = True

    if category not in _BY_CATEGORY:
        if resolved_from_product:
            # The product's category didn't clear the reporting bar (e.g. the
            # "Other/Uncategorized" catch-all -- see excluded_categories).
            # Fall back to the overall estimate instead of 404ing on a
            # perfectly valid product just because its category isn't
            # separately reported.
            return ELASTICITY_RESULTS["overall"], "overall"
        raise HTTPException(status_code=404, detail=f"category '{category}' not found")

    return _BY_CATEGORY[category], category


@app.get("/elasticity", response_model=ElasticityResponse)
def get_elasticity(
    category: Optional[str] = None,
    product_id: Optional[str] = None,
    price: Optional[float] = None,
) -> ElasticityResponse:
    """Look up an elasticity estimate by category or product_id."""
    if price is not None and price <= 0:
        raise HTTPException(status_code=422, detail="price must be positive")

    estimate, scope = _resolve_estimate(category, product_id)
    return _estimate_to_response(estimate, scope=scope, price=price,
                                 resolved_from_product_id=product_id)


@app.get("/scenario")
def get_scenario(
    pct_price_change: float = Query(..., gt=-100, le=500,
                                    description="Price move to test, in percent. -10 = a 10%% price cut."),
    category: Optional[str] = None,
    product_id: Optional[str] = None,
    price: Optional[float] = None,
    unit_cost: Optional[float] = None,
) -> dict:
    """What happens to units, revenue and (optionally) gross profit at a given price move.

    The dashboard mirrors this arithmetic in JavaScript so the slider responds
    without a round-trip; this endpoint is the canonical version and what the
    tests pin.
    """
    if price is not None and price <= 0:
        raise HTTPException(status_code=422, detail="price must be positive")
    if unit_cost is not None:
        if unit_cost < 0:
            raise HTTPException(status_code=422, detail="unit_cost must not be negative")
        if price is None:
            raise HTTPException(status_code=422, detail="unit_cost requires price")
        if unit_cost >= price:
            raise HTTPException(status_code=422, detail="unit_cost must be below price")

    estimate, scope = _resolve_estimate(category, product_id)
    scenario = build_scenario(
        elasticity=estimate["elasticity"],
        pct_price_change=pct_price_change,
        price=price,
        unit_cost=unit_cost,
        ci_low=estimate["ci_low"],
        ci_high=estimate["ci_high"],
    )
    return {
        "scope": scope,
        "resolved_from_product_id": product_id,
        "elasticity": estimate["elasticity"],
        "scenario": scenario.to_dict(),
        "advice": revenue_advice(estimate["elasticity"], estimate["ci_low"], estimate["ci_high"]),
        "caveat": ElasticityResponse.model_fields["caveat"].default,
    }
