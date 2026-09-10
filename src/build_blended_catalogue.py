"""
Blends the two catalogues into one view.

Which operation, and why
------------------------
Not a join. A join needs a match key present in both tables, and these two
share none: no product ids, no stores, no category names, not even a
currency. An inner join returns zero rows. A left, right or full outer join
returns a table that is almost entirely nulls, which is a worse way of saying
the same thing.

The correct operation is a vertical **concatenation**, a UNION ALL, onto one
harmonised schema:

    market | group | level | elasticity | ci_low | ci_high | std_error | n

(The one genuine inner join in this project lives inside
src/build_walmart_catalogue.py, where weekly units meet sell_prices on the
composite key store_id + item_id + wm_yr_wk. Inner is right there: a missing
price row means the store was not carrying that item yet, so those rows have
to disappear rather than be filled.)

Why the union is legitimate despite two currencies
--------------------------------------------------
Because of what the estimator does. Every estimate is a within-entity log-log
slope, and demeaning log price inside each entity removes any constant
multiplicative factor. An exchange rate is exactly that. So a slope fitted in
pounds and a slope fitted in dollars are already the same unit, a
dimensionless percentage-per-percentage, and stacking them needs no
conversion. The same argument covers pack sizes and units of measure.

How the stacked rows are pooled
-------------------------------
Not by observation count. Walmart brings 4.0 million store-item-weeks against
the UK catalogue's 194 thousand, so anything weighted by n is not a blend, it
is the Walmart number wearing a blend's clothes. Inverse-variance weighting
has the same defect in another form, because Walmart's standard errors are
tiny for the same reason.

These are two genuinely different populations rather than two samples of one,
so the pooled figure here is a **random-effects** estimate (DerSimonian and
Laird), which adds the between-market variance to each weight and stops the
larger dataset swallowing the smaller. Both the fixed-effect and
random-effects figures are written out, along with Cochran's Q, tau squared
and I squared, because the honest headline of this blend is how much the two
markets disagree.

Run: python -m src.build_blended_catalogue
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

SOURCES = [
    {
        "market": "uk",
        "label": "UK gift and homeware",
        "file": "elasticity_results.json",
        "currency": "GBP",
        "period": "December 2009 to December 2011",
        "levels": {"by_category": "department"},
    },
    {
        "market": "walmart",
        "label": "US Walmart",
        "file": "walmart_results.json",
        "currency": "USD",
        "period": "January 2011 to June 2016",
        "levels": {"by_category": "category", "by_department": "aisle", "by_state": "state"},
    },
]


def _load(name: str) -> dict | None:
    path = PROCESSED / name
    return json.loads(path.read_text()) if path.exists() else None


def union_rows() -> list[dict]:
    """UNION ALL of every reported group across both catalogues."""
    rows = []
    for src in SOURCES:
        results = _load(src["file"])
        if not results:
            continue
        for block, level in src["levels"].items():
            for row in results.get(block, []):
                rows.append({
                    "market": src["market"],
                    "market_label": src["label"],
                    "currency": src["currency"],
                    "period": src["period"],
                    "level": level,
                    "group": row["category"],
                    "elasticity": row["elasticity"],
                    "std_error": row["std_error"],
                    "ci_low": row["ci_low"],
                    "ci_high": row["ci_high"],
                    "r_squared": row["r_squared"],
                    "n_observations": row["n_observations"],
                    "n_lines": row.get("n_skus"),
                })
    rows.sort(key=lambda r: r["elasticity"])
    return rows


def pool(rows: list[dict]) -> dict:
    """Fixed-effect and random-effects pooling, plus how much they disagree.

    Weights are 1/variance. The random-effects version adds tau squared, the
    estimated variance *between* groups, to every one of them, which is what
    stops a single huge dataset dominating a pooled figure it should only be
    one voice in.
    """
    ok = [r for r in rows if r["std_error"] and r["std_error"] > 0]
    if len(ok) < 2:
        return {}

    y = [r["elasticity"] for r in ok]
    v = [r["std_error"] ** 2 for r in ok]
    w = [1.0 / vi for vi in v]

    sum_w = sum(w)
    fixed = sum(wi * yi for wi, yi in zip(w, y)) / sum_w
    fixed_se = math.sqrt(1.0 / sum_w)

    # Cochran's Q: observed dispersion against what sampling error alone predicts
    q = sum(wi * (yi - fixed) ** 2 for wi, yi in zip(w, y))
    df = len(ok) - 1
    sum_w_sq = sum(wi ** 2 for wi in w)
    c = sum_w - (sum_w_sq / sum_w)
    tau2 = max(0.0, (q - df) / c) if c > 0 else 0.0
    i2 = max(0.0, (q - df) / q) * 100 if q > 0 else 0.0

    w_re = [1.0 / (vi + tau2) for vi in v]
    sum_w_re = sum(w_re)
    random = sum(wi * yi for wi, yi in zip(w_re, y)) / sum_w_re
    random_se = math.sqrt(1.0 / sum_w_re)

    return {
        "groups_pooled": len(ok),
        "fixed_effect": {
            "elasticity": round(fixed, 3),
            "std_error": round(fixed_se, 4),
            "ci_low": round(fixed - 1.96 * fixed_se, 3),
            "ci_high": round(fixed + 1.96 * fixed_se, 3),
        },
        "random_effects": {
            "elasticity": round(random, 3),
            "std_error": round(random_se, 4),
            "ci_low": round(random - 1.96 * random_se, 3),
            "ci_high": round(random + 1.96 * random_se, 3),
        },
        "heterogeneity": {
            "cochran_q": round(q, 1),
            "degrees_of_freedom": df,
            "tau_squared": round(tau2, 4),
            "i_squared_pct": round(i2, 1),
            "reading": (
                "I squared is the share of the spread between these groups that is real "
                "rather than sampling noise. Above 75% the groups are telling different "
                "stories and a single pooled number should be read as a midpoint, not a "
                "summary."
            ),
        },
        "headline": "random_effects",
        "why": (
            "Random effects rather than fixed, because these are two different "
            "populations rather than two samples of one. Weighting by sample size or "
            "by inverse variance alone would hand the answer to whichever catalogue is "
            "bigger, which here is Walmart by a factor of twenty."
        ),
    }


def main() -> None:
    rows = union_rows()
    if not rows:
        raise SystemExit("No catalogue results found. Run the model builders first.")

    by_market = {}
    for src in SOURCES:
        subset = [r for r in rows if r["market"] == src["market"]]
        if subset:
            by_market[src["market"]] = {
                "label": src["label"],
                "currency": src["currency"],
                "period": src["period"],
                "groups": len(subset),
                "observations": sum(r["n_observations"] for r in subset),
                "pooled": pool(subset),
            }

    # The union is over comparable levels only. Walmart's aisles sit inside its
    # categories and its states cut across both, so pooling all three together
    # would count the same weeks up to three times.
    comparable = [r for r in rows if r["level"] in ("department", "category")]

    payload = {
        "operation": "concatenation (UNION ALL)",
        "why_not_a_join": (
            "The two catalogues share no match key: no product ids, no stores, no "
            "category names, no common currency. An inner join returns nothing and an "
            "outer join returns nulls. The one real inner join in this project is "
            "inside the Walmart build, joining weekly units to shelf prices on "
            "store_id + item_id + wm_yr_wk."
        ),
        "why_currencies_can_be_stacked": (
            "Every estimate is a within-entity log-log slope, and demeaning log price "
            "within an entity removes any constant multiplicative factor, an exchange "
            "rate included. The slopes are already the same dimensionless unit, so no "
            "conversion is needed or wanted."
        ),
        "schema": ["market", "level", "group", "elasticity", "ci_low", "ci_high",
                   "std_error", "n_observations"],
        "rows": rows,
        "totals": {
            "rows": len(rows),
            "markets": len(by_market),
            "comparable_groups": len(comparable),
            "observations": sum(r["n_observations"] for r in rows if r["level"] in ("department", "category")),
        },
        "by_market": by_market,
        "pooled": pool(comparable),
    }

    out = PROCESSED / "blended_results.json"
    out.write_text(json.dumps(payload, indent=2))

    print(f"UNION ALL over {len(SOURCES)} catalogues -> {len(rows)} rows "
          f"({len(comparable)} comparable groups)\n")
    print(f"  {'market':<9} {'level':<11} {'group':<24} {'beta':>7} {'n':>12}")
    for r in rows:
        print(f"  {r['market']:<9} {r['level']:<11} {r['group'][:23]:<24} "
              f"{r['elasticity']:>7.3f} {r['n_observations']:>12,}")

    p = payload["pooled"]
    print(f"\n  fixed effect   {p['fixed_effect']['elasticity']:+.3f}  "
          f"[{p['fixed_effect']['ci_low']}, {p['fixed_effect']['ci_high']}]")
    print(f"  random effects {p['random_effects']['elasticity']:+.3f}  "
          f"[{p['random_effects']['ci_low']}, {p['random_effects']['ci_high']}]   <- headline")
    h = p["heterogeneity"]
    print(f"  Q={h['cochran_q']} on {h['degrees_of_freedom']} df, "
          f"tau2={h['tau_squared']}, I2={h['i_squared_pct']}%")
    for key, m in by_market.items():
        print(f"    {m['label']:<22} {m['pooled']['random_effects']['elasticity']:+.3f} "
              f"across {m['groups']} groups")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
