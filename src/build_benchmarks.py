"""
Fits one price-elasticity benchmark per external dataset and writes
data/processed/benchmarks.json, which the API serves at /benchmarks and the
page uses for its "other markets" comparison.

This is the counterpart to src/build_elasticity_model.py. That one answers
"what does this catalogue do"; this one answers "is that number normal".

Method, per dataset rather than one-size-fits-all
-------------------------------------------------
Each dataset gets the estimator its design supports, and says which one it
got:

  within        log-log with fixed effects absorbed (store, state, country,
                week, year), standard errors clustered on the panel unit
  ols           log-log on a cross-section or a short series, with the
                controls the literature on that dataset uses
  iv            the same, with price instrumented -- a cigarette sales tax,
                offshore wave height, a cartel collapse
  logit         McFadden conditional logit on brand-choice panels, converted
                to an own-price elasticity at sample shares

`identification` on every record says plainly whether the number is a
correlation ("descriptive") or something with a defensible causal claim
("instrumented"). The page does not blur the two, and neither does this.

Run: python -m src.build_benchmarks
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .panel_fit import (
    conditional_logit,
    logit_own_price_elasticity,
    ols,
    summarize,
    tsls,
    within,
)
from .reference_datasets import REFERENCE_DATASETS, fetch

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "processed"
OUT_PATH = OUT_DIR / "benchmarks.json"

# Published ranges, for the few markets where the literature has actually
# converged on one. Quoted so a reader can see whether a fit lands where
# decades of work says it should -- not as a target the fit was tuned to.
LITERATURE = {
    "cigarettes_state_panel": {
        "range": "Most published estimates for high-income countries sit between −0.25 and −0.5, with panel estimates clustering near −0.4.",
        "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7789936/",
        "source_label": "Tobacco taxation practitioner's guide (NIH PMC)",
    },
    "cigarettes_stock_watson": {
        "range": "Most published estimates for high-income countries sit between −0.25 and −0.5, with panel estimates clustering near −0.4.",
        "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10277038/",
        "source_label": "Cross-country cigarette demand panel estimates (NIH PMC)",
    },
    "gasoline_oecd": {
        "range": "Survey estimates average about −0.26 in the short run and −0.86 in the long run; recent work puts the short run nearer −0.4.",
        "source": "https://www.dallasfed.org/research/economics/2020/0616",
        "source_label": "Dallas Fed, gasoline demand elasticity",
    },
    "us_gasoline_market": {
        "range": "Survey estimates average about −0.26 in the short run and −0.86 in the long run.",
        "source": "https://www.dallasfed.org/research/economics/2020/0616",
        "source_label": "Dallas Fed, gasoline demand elasticity",
    },
    "dominicks_oj": {
        "range": "Category-level orange juice estimates run about −0.7 to −1.0; a single brand on a shelf full of substitutes is far more elastic than the category as a whole.",
        "source": "https://ask.ifas.ufl.edu/publication/FE1174",
        "source_label": "UF/IFAS, own-price elasticity of orange juice",
    },
}


# The page sets every other number with a real minus sign and every other
# aside with a real em dash. Text that ships in the payload is held to the
# same standard: _signed() for figures, _typeset() for the prose fields,
# which keeps the ASCII convention this codebase writes its comments in from
# leaking onto the page.
def _signed(value: float) -> str:
    return f"{value:.2f}".replace("-", "\u2212")


def _typeset(text: str) -> str:
    return text.replace(" -- ", " — ") if isinstance(text, str) else text


def _log(series) -> np.ndarray:
    return np.log(np.asarray(series, dtype=float))


def _dummies(series) -> np.ndarray:
    """Dummy columns with the first level dropped (an intercept is always in)."""
    codes, uniques = pd.factorize(pd.Series(series).astype(str))
    if len(uniques) < 2:
        return np.empty((len(codes), 0))
    out = np.zeros((len(codes), len(uniques) - 1))
    for j in range(1, len(uniques)):
        out[:, j - 1] = (codes == j).astype(float)
    return out


# ---------------------------------------------------------------------------
# Quantity regressions
# ---------------------------------------------------------------------------


def fit_dominicks_oj(df: pd.DataFrame) -> dict:
    """Within store-brand and week, with the whole shelf's prices on the
    right-hand side.

    The own-price column has to be picked per row (brand 3's price is
    `price3`), and the competing-brand index is the mean log price of the
    other ten. Promotions are controlled for rather than dropped: a price
    cut that runs with a feature ad would otherwise hand the ad's effect to
    the price coefficient.
    """
    price_cols = [f"price{i}" for i in range(1, 12)]
    d = df.dropna(subset=["logmove", "store", "brand", "week", *price_cols]).copy()
    d = d[(d[price_cols] > 0).all(axis=1)]

    log_prices = np.log(d[price_cols].to_numpy(dtype=float))
    brand_idx = d["brand"].to_numpy(dtype=int) - 1
    rows = np.arange(len(d))

    own = log_prices[rows, brand_idx]
    total = log_prices.sum(axis=1)
    rival = (total - own) / (log_prices.shape[1] - 1)

    y = d["logmove"].to_numpy(dtype=float)
    feat = d["feat"].to_numpy(dtype=float)
    deal = d["deal"].to_numpy(dtype=float)

    entity = d["store"].astype(str) + ":" + d["brand"].astype(str)
    demeaned = within([y, own, rival, feat, deal],
                      [entity.to_numpy(), d["week"].to_numpy()])
    y_d, own_d, rival_d, feat_d, deal_d = demeaned

    n_entity = entity.nunique()
    n_week = d["week"].nunique()
    fit = ols(y_d, np.column_stack([own_d, rival_d, feat_d, deal_d]),
              cluster=d["store"].to_numpy(), absorbed=n_entity + n_week - 1,
              add_const=False)

    return summarize(
        fit["beta"][0], fit["se"][0], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="within",
        method_label="Within store-brand and week, log-log, promotions controlled",
        identification="descriptive",
        controls="competing-brand price index, feature ad, in-store display",
        cross_price_elasticity=round(float(fit["beta"][1]), 3),
        cross_price_std_error=round(float(fit["se"][1]), 3),
        n_units=int(n_entity),
        clustered_on=f"{d['store'].nunique()} stores",
    )


def fit_cigar_panel(df: pd.DataFrame) -> dict:
    """46 states x 30 years, two-way fixed effects, deflated to real prices.

    Nominal prices rose sixfold over this window for reasons that have
    nothing to do with cigarettes, so both price and income are deflated by
    the CPI before logging; year effects then absorb whatever moved the
    whole country at once, leaving state tax changes to identify the slope.
    """
    d = df.dropna(subset=["price", "sales", "cpi", "ndi", "pimin", "state", "year"]).copy()
    d = d[(d["price"] > 0) & (d["sales"] > 0) & (d["ndi"] > 0) & (d["pimin"] > 0)]

    real_price = _log(d["price"] / d["cpi"])
    real_income = _log(d["ndi"] / d["cpi"])
    neighbour_price = _log(d["pimin"] / d["cpi"])
    y = _log(d["sales"])

    y_d, p_d, inc_d, nb_d = within([y, real_price, real_income, neighbour_price],
                                   [d["state"].to_numpy(), d["year"].to_numpy()])
    n_state, n_year = d["state"].nunique(), d["year"].nunique()
    fit = ols(y_d, np.column_stack([p_d, inc_d, nb_d]), cluster=d["state"].to_numpy(),
              absorbed=n_state + n_year - 1, add_const=False)

    return summarize(
        fit["beta"][0], fit["se"][0], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="within",
        method_label="Two-way fixed effects (state, year), log-log, CPI-deflated",
        identification="descriptive",
        controls="real disposable income per capita, cheapest neighbouring-state price",
        n_units=int(n_state),
        clustered_on=f"{n_state} states",
        note="More elastic than the −0.4 that studies of smoking report, for two reasons worth knowing: "
             "this counts packs sold in a state, not cigarettes smoked by its residents — when one state "
             "raises tax, buyers drive across the line — and a static fit like this sits somewhere between "
             "a short-run and a long-run response rather than cleanly being either.",
    )


def fit_cigarettes_sw(df: pd.DataFrame) -> dict:
    """The tax-instrumented one.

    Price and quantity are set together -- a state where people smoke more
    is a state where the industry prices differently -- so OLS on this is
    not a demand curve. The general sales tax moves the shelf price without
    being chosen in response to smoking, which is the whole point of the
    dataset.
    """
    d = df.dropna(subset=["packs", "price", "income", "population", "cpi", "tax", "taxs"]).copy()

    real_price = _log(d["price"] / d["cpi"])
    real_income = _log(d["income"] / d["population"] / d["cpi"])
    y = _log(d["packs"])
    sales_tax = ((d["taxs"] - d["tax"]) / d["cpi"]).to_numpy(dtype=float)
    cig_tax = (d["tax"] / d["cpi"]).to_numpy(dtype=float)

    year_dummies = _dummies(d["year"])
    exog = np.column_stack([real_income, year_dummies])

    fit = tsls(y, real_price, exog, np.column_stack([sales_tax, cig_tax]),
               cluster=d["state"].to_numpy())

    return summarize(
        fit["beta"][1], fit["se"][1], fit["n"],
        method="iv",
        method_label="Two-stage least squares, price instrumented by state tax",
        identification="instrumented",
        controls="real income per capita, year effects",
        instrument="general sales tax and cigarette-specific tax per pack",
        first_stage_f=round(float(fit["first_stage_f"]), 1),
        n_units=int(d["state"].nunique()),
        clustered_on=f"{d['state'].nunique()} states",
        note="Like the state panel above, this counts packs sold rather than cigarettes smoked, so "
             "cross-border buying is folded into the number.",
    )


def fit_gasoline_oecd(df: pd.DataFrame) -> dict:
    """Already in logs in the source, so no transform -- just the panel."""
    d = df.dropna(subset=["gas", "price", "income", "cars", "country", "year"]).copy()
    y_d, p_d, inc_d, car_d = within(
        [d["gas"].to_numpy(float), d["price"].to_numpy(float),
         d["income"].to_numpy(float), d["cars"].to_numpy(float)],
        [d["country"].to_numpy(), d["year"].to_numpy()],
    )
    n_country, n_year = d["country"].nunique(), d["year"].nunique()
    fit = ols(y_d, np.column_stack([p_d, inc_d, car_d]),
              cluster=d["country"].to_numpy(), absorbed=n_country + n_year - 1,
              add_const=False)

    return summarize(
        fit["beta"][0], fit["se"][0], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="within",
        method_label="Two-way fixed effects (country, year), log-log",
        identification="descriptive",
        controls="real income per capita, cars per capita",
        n_units=int(n_country),
        clustered_on=f"{n_country} countries",
        note="Quantity is fuel per car, so this is consumption per vehicle, not total demand.",
    )


def fit_natural_gas(df: pd.DataFrame) -> dict:
    """Own price and two substitutes, which is the reason to keep this one."""
    d = df.dropna(subset=["consumption", "price", "eprice", "oprice", "heating",
                          "income", "state", "year"]).copy()
    d = d[(d[["consumption", "price", "eprice", "oprice", "heating", "income"]] > 0).all(axis=1)]

    cols = [_log(d["consumption"]), _log(d["price"]), _log(d["eprice"]),
            _log(d["oprice"]), _log(d["heating"]), _log(d["income"])]
    y_d, p_d, ep_d, op_d, heat_d, inc_d = within(cols, [d["state"].to_numpy(), d["year"].to_numpy()])
    n_state, n_year = d["state"].nunique(), d["year"].nunique()

    # Six states is far too few to cluster on -- cluster-robust variance is
    # badly biased below ~30 groups -- so these are classical SEs, and the
    # note says so rather than dressing them up.
    fit = ols(y_d, np.column_stack([p_d, ep_d, op_d, heat_d, inc_d]),
              absorbed=n_state + n_year - 1, add_const=False)

    return summarize(
        fit["beta"][0], fit["se"][0], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="within",
        method_label="Two-way fixed effects (state, year), log-log",
        identification="descriptive",
        controls="electricity price, heating oil price, heating degree-days, income",
        cross_price_elasticity=round(float(fit["beta"][1]), 3),
        cross_price_std_error=round(float(fit["se"][1]), 3),
        cross_price_label="electricity",
        n_units=int(n_state),
        note="Only 6 states, so standard errors are classical rather than clustered and are likely optimistic.",
    )


def fit_cartel(df: pd.DataFrame) -> dict:
    """Porter's identification: price wars move supply, not demand.

    When the cartel broke down, rates collapsed for reasons internal to the
    railroads' own agreement -- nothing about grain shippers' willingness to
    pay changed that week. Using the cartel indicator as an instrument
    traces out the demand curve; OLS on the same rows does not, and both are
    reported so the gap is visible.
    """
    d = df.dropna(subset=["price", "quantity", "cartel", "season"]).copy()
    d = d[(d["price"] > 0) & (d["quantity"] > 0)]

    y = _log(d["quantity"])
    log_price = _log(d["price"])
    ice = (d["ice"].astype(str).str.lower() == "yes").to_numpy(float) if "ice" in d else None
    season = _dummies(d["season"])
    exog_parts = [season] + ([ice.reshape(-1, 1)] if ice is not None else [])
    exog = np.column_stack(exog_parts)

    cartel = (d["cartel"].astype(str).str.lower() == "yes").to_numpy(float)
    iv_fit = tsls(y, log_price, exog, cartel.reshape(-1, 1))
    ols_fit = ols(y, np.column_stack([log_price, exog]))

    return summarize(
        iv_fit["beta"][1], iv_fit["se"][1], iv_fit["n"],
        method="iv",
        method_label="Two-stage least squares, price instrumented by cartel breakdown",
        identification="instrumented",
        controls="season effects, Great Lakes ice closure",
        instrument="whether the cartel was holding that week",
        first_stage_f=round(float(iv_fit["first_stage_f"]), 1),
        ols_comparison=round(float(ols_fit["beta"][1]), 3),
        note="The uninstrumented slope on the same weeks is "
             f"{_signed(ols_fit['beta'][1])} — the difference is what simultaneity does to a price coefficient.",
    )


def fit_fulton_fish(df: pd.DataFrame) -> dict:
    """Weather at sea as the instrument; the classic clean identification."""
    d = df.dropna(subset=["ltotqty", "lavgprc", "wave2", "speed2",
                          "mon", "tues", "wed", "thurs"]).copy()
    y = d["ltotqty"].to_numpy(float)
    log_price = d["lavgprc"].to_numpy(float)
    days = d[["mon", "tues", "wed", "thurs"]].to_numpy(float)
    instruments = d[["wave2", "speed2"]].to_numpy(float)

    iv_fit = tsls(y, log_price, days, instruments)
    ols_fit = ols(y, np.column_stack([log_price, days]))

    return summarize(
        iv_fit["beta"][1], iv_fit["se"][1], iv_fit["n"],
        method="iv",
        method_label="Two-stage least squares, price instrumented by offshore weather",
        identification="instrumented",
        controls="day-of-week effects",
        instrument="wave height and wind speed at sea (2-day lags)",
        first_stage_f=round(float(iv_fit["first_stage_f"]), 1),
        ols_comparison=round(float(ols_fit["beta"][1]), 3),
        note="The uninstrumented slope is "
             f"{_signed(ols_fit['beta'][1])}; storms raise price without changing anyone's appetite for fish.",
    )


def fit_individual_smoking(df: pd.DataFrame) -> dict:
    """A deliberate null result.

    Cigarettes per day is a count with 60% zeros, and state prices barely
    move within one year, so this is reported as an elasticity at the sample
    mean with an interval wide enough to contain almost anything. It earns
    its place by showing what "no usable price variation" looks like from
    the outside.
    """
    d = df.dropna(subset=["cigs", "lcigpric", "lincome", "educ", "age", "agesq", "restaurn"]).copy()
    y = d["cigs"].to_numpy(float)
    X = d[["lcigpric", "lincome", "educ", "age", "agesq", "restaurn"]].to_numpy(float)
    fit = ols(y, X)

    mean_cigs = float(y.mean())
    beta = float(fit["beta"][1]) / mean_cigs
    se = float(fit["se"][1]) / mean_cigs

    return summarize(
        beta, se, fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="ols",
        method_label="OLS on cigarettes per day, converted to an elasticity at the sample mean",
        identification="descriptive",
        controls="income, education, age, age squared, restaurant smoking ban",
        note="60% of respondents smoke nothing at all and state prices hardly vary within a single year: "
             "this interval is wide because the data genuinely cannot answer the question.",
    )


def fit_journals(df: pd.DataFrame) -> dict:
    """Library subscriptions against price per citation."""
    d = df.dropna(subset=["subs", "price", "citations"]).copy()
    d = d[(d["subs"] > 0) & (d["price"] > 0) & (d["citations"] > 0)]
    y = _log(d["subs"])
    x = _log(d["price"] / d["citations"])
    fit = ols(y, x)

    return summarize(
        fit["beta"][1], fit["se"][1], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="ols",
        method_label="Log-log cross-section, price measured per citation",
        identification="descriptive",
        controls="none -- price per citation is the quality adjustment",
    )


def fit_avocados(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["AveragePrice", "TotalVolume", "Date"]).copy()
    d["Date"] = pd.to_datetime(d["Date"])
    d = d.sort_values("Date")
    y = _log(d["TotalVolume"])
    x = _log(d["AveragePrice"])
    trend = np.arange(len(d), dtype=float)
    month = _dummies(d["Date"].dt.month)
    fit = ols(y, np.column_stack([x, trend, month]))

    return summarize(
        fit["beta"][1], fit["se"][1], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="ols",
        method_label="Log-log weekly time series with a trend and month effects",
        identification="descriptive",
        controls="linear trend, month-of-year effects",
        note="Weekly series, so the residuals are serially correlated and the interval is narrower than it should be.",
    )


def fit_ice_cream(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["cons", "price", "income", "temp"]).copy()
    fit = ols(_log(d["cons"]),
              np.column_stack([_log(d["price"]), _log(d["income"]), d["temp"].to_numpy(float)]))
    return summarize(
        fit["beta"][1], fit["se"][1], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="ols",
        method_label="Log-log with income and mean temperature",
        identification="descriptive",
        controls="income, mean temperature",
        note="Only 30 periods; the temperature control is doing as much work as the price.",
    )


def fit_us_gasoline(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["gas", "price", "income", "population"]).copy()
    y = _log(d["gas"] / d["population"])
    trend = np.arange(len(d), dtype=float)
    fit = ols(y, np.column_stack([_log(d["price"]), _log(d["income"]), trend]))
    return summarize(
        fit["beta"][1], fit["se"][1], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="ols",
        method_label="Log-log national time series, per capita, with a trend",
        identification="descriptive",
        controls="real income per capita, linear trend",
        note="36 annual observations of one country: a short-run national number, not a long-run one.",
    )


def fit_recreation(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["trips", "costS", "income", "quality"]).copy()
    d = d[(d["trips"] > 0) & (d["costS"] > 0)]
    fit = ols(_log(d["trips"]),
              np.column_stack([_log(d["costS"]), _log(d["income"].clip(lower=0.1)),
                               d["quality"].to_numpy(float)]))
    return summarize(
        fit["beta"][1], fit["se"][1], fit["n"],
        r_squared=round(fit["r_squared"], 3),
        method="ols",
        method_label="Log-log on households that took at least one trip",
        identification="descriptive",
        controls="income, subjective site quality",
        note="Households taking zero trips are dropped, which biases this toward zero: the people most put off "
             "by the cost are the ones excluded.",
    )


# ---------------------------------------------------------------------------
# Brand-choice panels
# ---------------------------------------------------------------------------

CHOICE_SPECS = {
    "choice_ketchup": dict(choice="Ketchup.choice", price="price.", disp=None, feat=None),
    "choice_catsup": dict(choice="choice", price="price.", disp="disp.", feat="feat."),
    "choice_tuna": dict(choice="Tuna.choice", price="price.", disp=None, feat=None),
    "choice_yogurt": dict(choice="choice", price="price.", disp=None, feat="feat."),
    "choice_crackers": dict(choice="choice", price="price.", disp="disp.", feat="feat."),
}


def fit_choice_panel(df: pd.DataFrame, spec: dict) -> dict:
    """Conditional logit on "which brand did this shopper pick".

    There are no units sold here -- one purchase occasion, one brand chosen
    -- so the elasticity is the logit one: beta * price * (1 - share), share-
    weighted across the brands on the shelf. It answers a different question
    from every other row in this file (switching between brands, not buying
    more or less of the category) and is labelled as such everywhere it
    appears.
    """
    price_cols = [c for c in df.columns if c.startswith(spec["price"])]
    brands = [c[len(spec["price"]):] for c in price_cols]
    needed = list(price_cols) + [spec["choice"]]
    d = df.dropna(subset=needed).copy()
    d = d[(d[price_cols] > 0).all(axis=1)]

    chosen_label = d[spec["choice"]].astype(str).str.lower().str.strip()
    lookup = {b.lower(): i for i, b in enumerate(brands)}
    keep = chosen_label.isin(lookup)
    d, chosen_label = d[keep], chosen_label[keep]
    chosen = chosen_label.map(lookup).to_numpy(int)

    n_obs, n_alt = len(d), len(brands)
    prices = d[price_cols].to_numpy(float)

    # Alternative-specific constants (first brand is the reference), then
    # price, then whichever promotion flags this panel carries.
    layers = [np.zeros((n_obs, n_alt, n_alt - 1))]
    for j in range(1, n_alt):
        layers[0][:, j, j - 1] = 1.0
    layers.append(prices.reshape(n_obs, n_alt, 1))
    names = [f"asc_{b}" for b in brands[1:]] + ["price"]

    for flag_prefix, label in ((spec["disp"], "display"), (spec["feat"], "feature")):
        if not flag_prefix:
            continue
        cols = [f"{flag_prefix}{b}" for b in brands if f"{flag_prefix}{b}" in d.columns]
        if len(cols) != n_alt:
            continue
        layers.append(d[cols].to_numpy(float).reshape(n_obs, n_alt, 1))
        names.append(label)

    X = np.concatenate(layers, axis=2)
    fit = conditional_logit(X, chosen)
    price_ix = names.index("price")
    beta, se = logit_own_price_elasticity(
        float(fit["beta"][price_ix]), float(fit["se"][price_ix]),
        prices.mean(axis=0), fit["shares"],
    )

    controls = ", ".join(["brand constants"] + [n for n in names if n in ("display", "feature")])
    return summarize(
        beta, se, n_obs,
        r_squared=round(float(fit["pseudo_r_squared"]), 3),
        method="logit",
        method_label="Conditional logit on brand choice, elasticity at sample shares",
        identification="descriptive",
        controls=controls,
        n_units=n_alt,
        measures="brand switching, not category volume",
        note="A brand-level number: it counts shoppers moving to the brand next to it on the shelf, "
             "which is always a bigger effect than the category losing volume outright.",
    )


FITTERS = {
    "dominicks_oj": fit_dominicks_oj,
    "cigarettes_state_panel": fit_cigar_panel,
    "cigarettes_stock_watson": fit_cigarettes_sw,
    "gasoline_oecd": fit_gasoline_oecd,
    "natural_gas_states": fit_natural_gas,
    "rail_freight_cartel": fit_cartel,
    "fulton_fish": fit_fulton_fish,
    "individual_smoking": fit_individual_smoking,
    "economics_journals": fit_journals,
    "avocados_california": fit_avocados,
    "ice_cream": fit_ice_cream,
    "us_gasoline_market": fit_us_gasoline,
    "recreation_trips": fit_recreation,
}
FITTERS.update({key: (lambda df, s=spec: fit_choice_panel(df, s)) for key, spec in CHOICE_SPECS.items()})


def build(force_download: bool = False) -> dict:
    benchmarks, failures = [], []

    for spec in REFERENCE_DATASETS:
        fitter = FITTERS.get(spec.key)
        if fitter is None:                                  # pragma: no cover
            continue
        try:
            df = fetch(spec, force=force_download)
            record = fitter(df)
        except Exception as exc:                            # noqa: BLE001
            failures.append({"key": spec.key, "market": spec.market, "error": f"{type(exc).__name__}: {exc}"})
            print(f"  [failed] {spec.key}: {type(exc).__name__}: {exc}")
            continue

        for field in ("note", "method_label", "controls", "measures"):
            if field in record:
                record[field] = _typeset(record[field])

        record.update({
            "id": spec.key,
            "market": spec.market,
            "region": spec.region,
            "period": spec.period,
            "data_type": spec.data_type,
            "source": {
                "package": spec.package,
                "item": spec.item,
                "url": spec.doc_url or spec.source_url,
                "license": spec.license,
                "citation": spec.citation,
            },
            "description": _typeset(spec.description),
        })
        if spec.key in LITERATURE:
            record["literature"] = LITERATURE[spec.key]
        benchmarks.append(record)
        print(f"  [ok] {spec.key:26s} {record['elasticity']:+.3f} "
              f"[{record['ci_low']:+.2f}, {record['ci_high']:+.2f}]  n={record['n_observations']:,}")

    quantity = [b for b in benchmarks if b["method"] != "logit"]
    quantity.sort(key=lambda b: b["elasticity"])
    choice = [b for b in benchmarks if b["method"] == "logit"]
    choice.sort(key=lambda b: b["elasticity"])

    return {
        "generated": date.today().isoformat(),
        "benchmarks": quantity,
        "brand_choice_benchmarks": choice,
        "failures": failures,
        "methodology": {
            "purpose": (
                "External reference points, so a number fitted from one UK catalogue can be read "
                "against markets where price response is already well studied."
            ),
            "estimators": {
                "within": "log-log with fixed effects absorbed, standard errors clustered on the panel unit",
                "ols": "log-log regression with the controls that dataset's literature uses",
                "iv": "two-stage least squares, price instrumented by something that moves supply only",
                "logit": "conditional logit on brand choice, converted to an own-price elasticity at sample shares",
            },
            "identification": (
                "'instrumented' rows have a defensible causal claim; 'descriptive' rows are associations "
                "in observational data, the same caveat that applies to this site's own estimates."
            ),
            "redistribution": (
                "No source data is committed to this repository. Datasets are re-fetched from their "
                "packages (CRAN mirrors and PyPI) by src/reference_datasets.py; only the fitted "
                "coefficients are stored here."
            ),
            "reproduce": "python -m src.build_benchmarks",
        },
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Fitting external benchmarks ...")
    payload = build()
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUT_PATH} "
          f"({len(payload['benchmarks'])} quantity benchmarks, "
          f"{len(payload['brand_choice_benchmarks'])} brand-choice, "
          f"{len(payload['failures'])} failed)")


if __name__ == "__main__":
    main()
