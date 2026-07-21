"""
FastAPI layer serving the elasticity estimates. Loads elasticity_results.json
once at startup (a precomputed artifact).

Run: uvicorn src.api:app --reload
"""

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .dashboard import DASHBOARD_HTML

# Stub data for demo (normally loaded from files)
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

app = FastAPI(
    title="Price Elasticity Predictor API",
    description="Log-log panel regression estimates of price elasticity of demand, "
                 "from public retail transaction data. See /methodology for caveats.",
    version="1.0.0",
)


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
    caveat: str = (
        "Descriptive association from observational data, not a causal effect -- "
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
    )


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD_HTML


@app.get("/api")
def api_info() -> dict:
    return {
        "name": "Price Elasticity Predictor API",
        "endpoints": ["/elasticity", "/categories", "/methodology", "/health", "/products"],
        "docs": "/docs",
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/methodology")
def methodology() -> dict:
    return STUB_ELASTICITY_RESULTS["methodology"]


@app.get("/categories")
def list_categories() -> dict:
    by_cat = {r["category"]: r for r in STUB_ELASTICITY_RESULTS["by_category"]}
    return {
        "reported": sorted(by_cat.keys()),
        "excluded": STUB_ELASTICITY_RESULTS["excluded_categories"],
    }


@app.get("/products")
def list_products(category: Optional[str] = None, limit: int = 500) -> dict:
    """Browsable product directory with typical prices for auto-fill."""
    products = STUB_PRODUCTS
    if category is not None:
        products = [p for p in products if p["category"] == category]
    return {"count": len(products), "products": products[:limit]}


@app.get("/elasticity", response_model=ElasticityResponse)
def get_elasticity(
    category: Optional[str] = None,
    product_id: Optional[str] = None,
    price: Optional[float] = None,
) -> ElasticityResponse:
    """Look up an elasticity estimate by category or product_id."""
    if price is not None and price <= 0:
        raise HTTPException(status_code=422, detail="price must be positive")

    by_category = {r["category"]: r for r in STUB_ELASTICITY_RESULTS["by_category"]}

    if category is None and product_id is None:
        return _estimate_to_response(STUB_ELASTICITY_RESULTS["overall"], scope="overall", price=price)

    if category is None and product_id is not None:
        product = next((p for p in STUB_PRODUCTS if p["product_id"] == product_id), None)
        if product is None:
            raise HTTPException(status_code=404, detail=f"product_id '{product_id}' not found")
        category = product["category"]

    if category not in by_category:
        raise HTTPException(status_code=404, detail=f"category '{category}' not found")

    return _estimate_to_response(
        by_category[category], scope=category, price=price,
        resolved_from_product_id=product_id,
    )
