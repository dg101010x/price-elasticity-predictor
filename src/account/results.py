"""
An account's stored runs, in the shapes the page already knows how to draw.

The public page reads /estimates, /catalog and /benchmarks. The dashboard
reads the same three shapes from /api/account/*, built here from the
account's latest ready upload -- which is what lets the existing verdict,
break-even scale, scenario curve, category chart and other-markets plot
redraw against a business's own numbers without a second implementation.

The decision layer (advice, evidence) comes from the same
src/elasticity_math functions the public estimates use.
"""

from __future__ import annotations

from ..elasticity_math import REVENUE_BREAKEVEN_ELASTICITY, evidence_summary, revenue_advice
from .supabase import Supabase

# Same constants as src/stats_engine.py, which isn't imported here because
# it pulls in pandas -- and every page view would pay for that at cold start.
# tests/test_account_api.py pins that the two agree.
Z95 = 1.96
MIN_OBS_PER_CATEGORY = 500
MIN_PRODUCTS_PER_CATEGORY = 15

OVERALL = "__overall__"


def latest_ready_source(sb: Supabase, token: str, account_id: str) -> dict | None:
    rows = sb.select("data_sources", token, account_id=f"eq.{account_id}", status="eq.ready",
                     order="uploaded_at.desc", limit="1")
    return rows[0] if rows else None


def runs_for(sb: Supabase, token: str, source_id: str) -> list[dict]:
    return sb.select("elasticity_runs", token, data_source_id=f"eq.{source_id}",
                     order="coefficient.asc")


def _interpretation(beta: float) -> str:
    if beta <= -1:
        return "elastic (quantity responds more than proportionally to price)"
    if beta < 0:
        return "inelastic (quantity responds less than proportionally to price)"
    return "positive association (likely confounded -- not a real demand response)"


def estimate_from_run(run: dict, meta: dict) -> dict:
    beta = float(run["coefficient"])
    ci_low, ci_high = float(run["ci_low"]), float(run["ci_high"])
    estimate = {
        "run_id": run["id"],
        "category": run["category"],
        "elasticity": beta,
        "std_error": meta.get("std_error", round((ci_high - ci_low) / (2 * Z95), 3)),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "r_squared": float(run["r_squared"]),
        "n_observations": int(run["n_observations"]),
        "n_skus": meta.get("n_products"),
        "interpretation": meta.get("interpretation", _interpretation(beta)),
        "pct_quantity_change_for_10pct_price_increase": meta.get(
            "pct_quantity_change_for_10pct_price_increase", round(((1.10 ** beta) - 1) * 100, 1)),
    }
    estimate["advice"] = revenue_advice(beta, ci_low, ci_high)
    estimate["evidence"] = evidence_summary(estimate)
    return estimate


def methodology(source: dict) -> dict:
    report = source.get("report") or {}
    dropped = report.get("dropped") or {}
    cleaning = ", ".join(f"{n:,} rows with {why}" for why, n in dropped.items()) or "no rows needed dropping"
    date_range = report.get("date_range")
    has_category = bool((report.get("mapping") or {}).get("category"))
    return {
        "method": "within-product (fixed-effects) log-log panel regression, weekly aggregation -- "
                  "the same estimator, in the same code, as the public UCI estimate",
        "source_dataset": f"your upload “{source['filename']}”"
                          + (f", {date_range[0]} to {date_range[1]}" if date_range else ""),
        "category_assignment": "the category column in your upload" if has_category
                               else "none -- the upload had no category column, so only the whole-catalogue "
                                    "estimate is fitted",
        "cleaning": f"rows rolled up to one per product per week (units summed, price quantity-weighted); "
                    f"dropped: {cleaning}",
        "exclusion_thresholds": f">= {MIN_OBS_PER_CATEGORY} product-week observations and "
                                f">= {MIN_PRODUCTS_PER_CATEGORY} distinct products required to report a category",
        "note": "Descriptive association from your own sales history, not a causal effect -- your prices "
                "weren't set at random, and whatever moved them (promotions, seasons, clearance) moved sales too.",
    }


def estimates_payload(source: dict, runs: list[dict]) -> dict:
    report = source.get("report") or {}
    meta = report.get("run_meta") or {}
    overall_run = next((r for r in runs if r["category"] is None), None)
    if overall_run is None:
        raise LookupError("this upload has no whole-catalogue run")
    by_category = [estimate_from_run(r, meta.get(r["category"], {})) for r in runs if r["category"] is not None]
    by_category.sort(key=lambda e: e["elasticity"])
    overall = estimate_from_run(overall_run, meta.get(OVERALL, {}))
    overall["scope"] = "overall"
    for e in by_category:
        e["scope"] = e["category"]
    return {
        "overall": overall,
        "by_category": by_category,
        "excluded_categories": report.get("excluded_categories", []),
        "methodology": methodology(source),
        "revenue_breakeven_elasticity": REVENUE_BREAKEVEN_ELASTICITY,
        "using_stub_data": False,
        "data_source": source_summary(source),
    }


def source_summary(source: dict) -> dict:
    report = source.get("report") or {}
    return {
        "id": source["id"],
        "filename": source["filename"],
        "status": source["status"],
        "status_reason": source.get("status_reason"),
        "uploaded_at": source["uploaded_at"],
        "row_count": source.get("row_count"),
        "rows_used": report.get("rows_used"),
        "product_weeks": report.get("product_weeks"),
        "products": report.get("products"),
        "weeks": report.get("weeks"),
        "date_range": report.get("date_range"),
        "currency": report.get("currency", "USD"),
        "dropped": report.get("dropped", {}),
        "excluded_categories": report.get("excluded_categories", []),
        "category_conflicts": report.get("category_conflicts", 0),
        "fractional_units_rounded": report.get("fractional_units_rounded", 0),
        "diagnostics": report.get("diagnostics"),
        "mapping": report.get("mapping"),
    }


def catalog_payload(sb: Supabase, token: str, source: dict, reported: list[str],
                    excluded: list[str]) -> dict:
    rows = sb.rpc("product_catalog", {"target_data_source_id": source["id"]}, token) or []
    categories = sorted({r[2] or "Uncategorized" for r in rows})
    index = {name: i for i, name in enumerate(categories)}
    return {
        "currency": (source.get("report") or {}).get("currency", "USD"),
        "categories": categories,
        "reported": sorted(reported),
        "excluded": sorted(excluded),
        "products": [[key, name, index[cat or "Uncategorized"], float(price)]
                     for key, name, cat, price in rows if price is not None and float(price) > 0],
    }


def benchmarks_payload(public: dict | None, account_name: str, overall: dict, source: dict) -> dict:
    if public is None:
        return {"available": False, "benchmarks": [], "brand_choice_benchmarks": []}
    report = source.get("report") or {}
    date_range = report.get("date_range")
    return {
        "available": True,
        "generated": public.get("generated"),
        "this_catalogue": {
            "id": "this_catalogue",
            "market": account_name,
            "elasticity": overall["elasticity"],
            "ci_low": overall["ci_low"],
            "ci_high": overall["ci_high"],
            "n_observations": overall["n_observations"],
            "method": "within",
            "method_label": "Within-product log-log, weekly panel",
            "identification": "descriptive",
            "period": f"{date_range[0][:4]}–{date_range[1][:4]}" if date_range else None,
        },
        "benchmarks": public["benchmarks"],
        "brand_choice_benchmarks": public["brand_choice_benchmarks"],
        "methodology": public["methodology"],
        "revenue_breakeven_elasticity": REVENUE_BREAKEVEN_ELASTICITY,
    }


def previous_ready_source(sb: Supabase, token: str, account_id: str, before: str) -> dict | None:
    rows = sb.select("data_sources", token, account_id=f"eq.{account_id}", status="eq.ready",
                     uploaded_at=f"lt.{before}", order="uploaded_at.desc", limit="1")
    return rows[0] if rows else None


def compare_runs(previous: list[dict], current: list[dict]) -> list[dict]:
    """Did the last upload's read hold up? For every estimate present in both
    uploads (the whole catalogue, and each category reported both times):
    does the new point estimate fall inside the old 95% interval?

    This is the start of outcome data: an insight is grounded in a run, so
    "the run it was grounded in held / moved" is a checkable, stored-data
    answer to "was that advice right?", derivable at any time from the
    immutable elasticity_runs rows -- nothing extra needs storing yet.
    """
    before = {r["category"]: r for r in previous}
    rows = []
    for now in sorted(current, key=lambda r: (r["category"] is not None, r["category"] or "")):
        was = before.get(now["category"])
        if was is None:
            continue
        coef = float(now["coefficient"])
        lo, hi = float(was["ci_low"]), float(was["ci_high"])
        rows.append({
            "category": now["category"],
            "previous": {"run_id": was["id"], "coefficient": float(was["coefficient"]), "ci_low": lo,
                         "ci_high": hi},
            "current": {"run_id": now["id"], "coefficient": coef, "ci_low": float(now["ci_low"]),
                        "ci_high": float(now["ci_high"])},
            "held": lo <= coef <= hi,
            "side_changed": (hi < -1) != (float(now["ci_high"]) < -1) or (lo > -1) != (float(now["ci_low"]) > -1),
        })
    return rows
