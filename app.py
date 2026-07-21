"""
Streamlit dashboard on top of the FastAPI elasticity endpoint (src/api.py).

Run (with the API already running on API_BASE_URL, default localhost:8000):
    streamlit run app.py
"""

import os
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# Dark palette, validated against the #11151c chart surface
# (dataviz skill validator: lightness band, chroma, CVD separation, contrast)
BLUE = "#3987e5"        # negative / inelastic-direction coefficients, primary accent
RED = "#e66767"         # positive (anomalous) coefficients, elastic warnings
YELLOW = "#c98500"      # highlight for the selected category
PAGE_BG = "#0a0d12"
SURFACE = "#11151c"
GRIDLINE = "#222835"
BORDER = "rgba(255,255,255,0.10)"
INK_PRIMARY = "#e8eaf0"
INK_SECONDARY = "#9aa3b2"
INK_MUTED = "#6b7280"
MONO = '"SF Mono", "Cascadia Code", Menlo, Consolas, monospace'

CURRENCY_SYMBOLS = {"GBP": "£", "USD": "$", "INR": "₹", "EUR": "€"}

# Plain-language explanations, surfaced as hover tooltips everywhere a term
# appears, and repeated verbatim in the glossary expander for touch screens.
GLOSSARY = {
    "elasticity": (
        "How strongly shoppers react to a price change. It is the % change in "
        "quantity sold when the price rises by 1%. Example: an elasticity of "
        "−2 means a 10% price increase cuts sales by about 20%."
    ),
    "sign": (
        "A negative number is normal: price goes up, sales go down. A positive "
        "number would mean people buy MORE when it gets pricier — almost always "
        "a data quirk here, not real behavior."
    ),
    "elastic": (
        "Shoppers react strongly: raise the price 10% and sales fall MORE than "
        "10%. Discounts pay off; price hikes are risky."
    ),
    "inelastic": (
        "Shoppers barely react: raise the price 10% and sales fall LESS than "
        "10%. People keep buying — think everyday essentials."
    ),
    "ci": (
        "The 95% confidence interval: the range where the true value plausibly "
        "sits. A narrow range = precise estimate; a wide range = take the "
        "headline number with a grain of salt."
    ),
    "r2": (
        "R-squared: how much of the ups and downs in sales the model explains, "
        "from 0 to 1. Low values are normal for retail data — price is only one "
        "of many reasons people buy."
    ),
    "n": (
        "Sample size: how many product-month data points went into this "
        "estimate. More observations = a more trustworthy number."
    ),
    "typical_price": (
        "The average price this product actually sold at in the data, filled "
        "in for you automatically. Change it freely — it only anchors the "
        "chart, not the elasticity itself."
    ),
}

st.set_page_config(page_title="Price Elasticity Predictor", layout="wide")

st.markdown(
    f"""
<style>
/* ---- page chrome ---------------------------------------------------- */
.stApp {{ background: {PAGE_BG}; }}
.block-container {{ padding-top: 2.2rem; max-width: 1200px; }}

/* ---- hover tooltips -------------------------------------------------- */
.tip {{
  position: relative;
  border-bottom: 1px dotted {INK_MUTED};
  cursor: help;
}}
.tip::after {{
  content: attr(data-tip);
  position: absolute;
  left: 50%; top: calc(100% + 8px);
  transform: translateX(-50%);
  width: 280px;
  text-transform: none;
  letter-spacing: normal;
  background: #1a2029;
  color: {INK_PRIMARY};
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.8rem; font-weight: 400; line-height: 1.45;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  text-align: left;
  opacity: 0; visibility: hidden;
  transition: opacity 120ms ease;
  z-index: 1000;
  pointer-events: none;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
}}
.tip:hover::after {{ opacity: 1; visibility: visible; }}
div[data-testid="stElementContainer"]:has(.tip:hover),
div[data-testid="stMarkdownContainer"]:has(.tip:hover) {{
  position: relative; z-index: 1001;
}}

/* ---- header ---------------------------------------------------------- */
.pep-header h1 {{
  font-size: 1.7rem; letter-spacing: -0.01em; margin: 0;
  color: {INK_PRIMARY};
}}
.pep-header .tagline {{ color: {INK_SECONDARY}; font-size: 0.92rem; margin-top: 2px; }}
.status-dot {{
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #0ca30c; margin-right: 6px;
  box-shadow: 0 0 6px rgba(12,163,12,0.8);
}}

/* ---- stat tiles ------------------------------------------------------- */
.tile-row {{ display: flex; gap: 12px; margin: 4px 0 14px 0; flex-wrap: wrap; }}
.tile {{
  flex: 1 1 130px;
  background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.00)), {SURFACE};
  border: 1px solid {BORDER};
  border-radius: 10px;
  padding: 12px 14px;
}}
.tile .label {{
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em;
  color: {INK_SECONDARY}; margin-bottom: 6px;
}}
.tile .value {{
  font-family: {MONO}; font-size: 1.45rem; font-weight: 600;
  color: {INK_PRIMARY}; font-variant-numeric: tabular-nums;
}}
.tile .sub {{ font-size: 0.72rem; color: {INK_MUTED}; margin-top: 3px; }}

/* ---- headline & callouts ---------------------------------------------- */
.headline {{
  font-size: 1.12rem; line-height: 1.6; color: {INK_PRIMARY};
  margin: 6px 0 10px 0;
}}
.headline .num {{ font-family: {MONO}; font-variant-numeric: tabular-nums; }}
.anomaly {{
  border: 1px solid rgba(230,103,103,0.35);
  border-left: 3px solid {RED};
  background: rgba(230,103,103,0.07);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 0.85rem; color: {INK_PRIMARY}; line-height: 1.5;
  margin-bottom: 10px;
}}

/* ---- widget polish ---------------------------------------------------- */
div[data-testid="stNumberInput"] input {{ font-family: {MONO}; }}
</style>
""",
    unsafe_allow_html=True,
)


def term(label: str, key: str) -> str:
    """An inline span that explains itself on hover."""
    return f'<span class="tip" data-tip="{GLOSSARY[key]}">{label}</span>'


# ---- API helpers ----------------------------------------------------------

@st.cache_data(ttl=60)
def fetch_categories() -> dict:
    r = requests.get(f"{API_BASE_URL}/categories", timeout=10)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def fetch_products(category: Optional[str]) -> list:
    params = {"category": category} if category else {}
    r = requests.get(f"{API_BASE_URL}/products", params=params, timeout=15)
    r.raise_for_status()
    return r.json()["products"]


@st.cache_data(ttl=60)
def fetch_methodology() -> dict:
    r = requests.get(f"{API_BASE_URL}/methodology", timeout=10)
    r.raise_for_status()
    return r.json()


def fetch_elasticity(category: Optional[str], product_id: Optional[str], price: Optional[float]) -> dict:
    params = {}
    if category:
        params["category"] = category
    if product_id:
        params["product_id"] = product_id
    if price:
        params["price"] = price
    r = requests.get(f"{API_BASE_URL}/elasticity", params=params, timeout=10)
    if r.status_code != 200:
        raise RuntimeError(r.json().get("detail", r.text))
    return r.json()


# ---- charts ---------------------------------------------------------------

def _dark_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        font=dict(color=INK_PRIMARY, family="system-ui, -apple-system, Segoe UI, sans-serif"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=height,
        hoverlabel=dict(bgcolor="#1a2029", bordercolor="rgba(255,255,255,0.15)",
                        font=dict(color=INK_PRIMARY)),
    )
    return fig


def demand_curve_figure(elasticity: float, price: Optional[float], symbol: str) -> go.Figure:
    multipliers = np.linspace(0.5, 1.5, 100)
    quantity_index = multipliers ** elasticity

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=multipliers, y=quantity_index, mode="lines",
        line=dict(color=BLUE, width=2),
        hovertemplate="price x%{x:.2f} &rarr; quantity x%{y:.2f}<extra></extra>",
        showlegend=False,
    ))
    fig.add_vline(x=1.0, line_dash="dot", line_color=INK_MUTED, line_width=1)
    fig.add_trace(go.Scatter(
        x=[1.0, 1.1], y=[1.0, 1.1 ** elasticity], mode="markers",
        marker=dict(color=[INK_SECONDARY, RED if elasticity > 0 else BLUE], size=9,
                    line=dict(color=SURFACE, width=2)),
        text=["baseline price", "price +10%"],
        hovertemplate="%{text}: quantity x%{y:.3f}<extra></extra>",
        showlegend=False,
    ))
    x_title = "Price relative to baseline" if price is None else f"Price relative to {symbol}{price:,.2f}"
    fig.update_layout(
        xaxis=dict(title=x_title, tickformat=".0%", gridcolor=GRIDLINE, zeroline=False),
        yaxis=dict(title="Quantity relative to baseline", tickformat=".0%", gridcolor=GRIDLINE, zeroline=False),
    )
    return _dark_layout(fig, 340)


def category_comparison_figure(categories: list, highlight: Optional[str]) -> go.Figure:
    df = pd.DataFrame(categories).sort_values("elasticity")
    top = pd.concat([df.head(10), df.tail(10)]).drop_duplicates(subset="category")
    colors = [RED if v > 0 else BLUE for v in top["elasticity"]]
    if highlight:
        colors = [c if cat != highlight else YELLOW for c, cat in zip(colors, top["category"])]

    fig = go.Figure(go.Bar(
        x=top["elasticity"], y=top["category"], orientation="h",
        marker=dict(color=colors, line=dict(color=SURFACE, width=1)),
        text=[f"{v:.2f}" for v in top["elasticity"]],
        textposition="outside",
        textfont=dict(family=MONO, color=INK_SECONDARY, size=11),
        hovertemplate="%{y}: elasticity %{x:.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=INK_MUTED, line_width=1)
    fig.update_layout(
        xaxis=dict(title="Elasticity  (more negative = shoppers more price-sensitive)",
                   gridcolor=GRIDLINE, zeroline=False),
        yaxis=dict(title=None, gridcolor=GRIDLINE, autorange="reversed"),
        showlegend=False,
    )
    return _dark_layout(fig, 520)


# ---- header ---------------------------------------------------------------

st.markdown(
    """
<div class="pep-header">
  <h1>Price Elasticity Predictor</h1>
  <div class="tagline"><span class="status-dot"></span>Log-log panel regression estimates of
  price elasticity from public retail data &middot; research/portfolio project, not pricing advice</div>
</div>
""",
    unsafe_allow_html=True,
)
st.markdown(
    f"""<div style="color:{INK_SECONDARY}; font-size:0.9rem; margin:10px 0 4px 0;">
    {term("Price elasticity", "elasticity")} measures how much sales move when prices move.
    Pick a product or category below &mdash; hover any dotted term or stat label for a plain-English explanation.
    </div>""",
    unsafe_allow_html=True,
)

try:
    categories_payload = fetch_categories()
    reported_categories = categories_payload["reported"]
except requests.exceptions.ConnectionError:
    st.error(
        f"Can't reach the API at {API_BASE_URL}. Start it with:\n\n"
        f"`uvicorn src.api:app --reload`\n\nthen reload this page."
    )
    st.stop()
except Exception as e:
    st.error(f"API error: {e}")
    st.stop()

def is_human_readable(category: str) -> bool:
    return len(category) > 4 or " " in category

reported_categories = [c for c in reported_categories if is_human_readable(c)]

# ---- query + result -------------------------------------------------------

col_input, col_result = st.columns([1, 2], gap="large")

with col_input:
    st.subheader("Look up an estimate")
    mode = st.segmented_control(
        "Scope", ["Overall", "By category", "By product"], default="By product",
        help="Overall = one number for the whole dataset. By category = e.g. Kitchen & Dining. "
             "By product = pick a real product by name.",
    )

    category = None
    product_id = None
    selected_product = None

    if mode == "By category":
        category = st.selectbox("Category", reported_categories,
                                help="Product categories with enough data for a reliable estimate. "
                                     "Type to search.")
    elif mode == "By product":
        cat_options = ["All categories"] + reported_categories
        cat_filter = st.selectbox("Browse category", cat_options,
                                  help="Narrow the product list, or search across everything.")
        try:
            products = fetch_products(None if cat_filter == "All categories" else cat_filter)
        except Exception as e:
            st.error(f"Couldn't load the product directory: {e}")
            products = []
        if products:
            selected_product = st.selectbox(
                "Product", products,
                format_func=lambda p: f"{p['product_name'].title()}  ·  "
                                      f"{CURRENCY_SYMBOLS.get(p['currency'], '')}{p['typical_price']:,.2f}",
                help="Real products from the underlying datasets, most-sold first. "
                     "Type any word to search (e.g. 'lantern'). The price shown is what "
                     "it typically sold for — it fills the price box automatically.",
            )
            product_id = selected_product["product_id"]

    if selected_product is not None:
        symbol = CURRENCY_SYMBOLS.get(selected_product["currency"], "")
        price = st.number_input(
            f"Price ({symbol})", min_value=0.01,
            value=float(selected_product["typical_price"]), step=0.5,
            key=f"price_{product_id}",
            help=GLOSSARY["typical_price"],
        )
    else:
        symbol = ""
        price = st.number_input(
            "Price (native currency of the source)", min_value=0.01, value=10.00, step=0.5,
            key="price_manual",
            help="A reference price point. It anchors the demand-curve chart; "
                 "the elasticity estimate itself doesn't depend on it.",
        )

with col_result:
    st.subheader("Result")
    result = None
    if mode is not None:
        try:
            result = fetch_elasticity(category, product_id, price)
        except RuntimeError as e:
            st.warning(str(e))
        except Exception as e:
            st.error(f"API error: {e}")

    if result:
        e_val = result["elasticity"]
        tiles = f"""
<div class="tile-row">
  <div class="tile">
    <div class="label"><span class="tip" data-tip="{GLOSSARY['elasticity']} {GLOSSARY['sign']}">Elasticity</span></div>
    <div class="value" style="color:{RED if e_val > 0 else BLUE};">{e_val:.3f}</div>
    <div class="sub">{'&#9888; positive sign' if e_val > 0 else 'negative = normal'}</div>
  </div>
  <div class="tile">
    <div class="label"><span class="tip" data-tip="{GLOSSARY['ci']}">95% CI</span></div>
    <div class="value">[{result['ci_low']:.2f}, {result['ci_high']:.2f}]</div>
    <div class="sub">plausible range</div>
  </div>
  <div class="tile">
    <div class="label"><span class="tip" data-tip="{GLOSSARY['r2']}">R&sup2;</span></div>
    <div class="value">{result['r_squared']:.3f}</div>
    <div class="sub">variance explained</div>
  </div>
  <div class="tile">
    <div class="label"><span class="tip" data-tip="{GLOSSARY['n']}">N</span></div>
    <div class="value">{result['n_observations']:,}</div>
    <div class="sub">product-months</div>
  </div>
</div>"""
        st.markdown(tiles, unsafe_allow_html=True)

        scope_label = result["scope"]
        if selected_product is not None:
            scope_label = f"{selected_product['product_name'].title()} ({result['scope']})"
        interp_key = "elastic" if "inelastic" not in result["interpretation"] else "inelastic"
        qty_change = result["pct_quantity_change_for_10pct_price_increase"]
        st.markdown(
            f"""<div class="headline"><b>{scope_label}</b> is
            {term(result['interpretation'], interp_key)}.
            A 10% price increase is associated with a
            <span class="num" style="color:{RED if qty_change > 0 else BLUE};"><b>{qty_change:+.1f}%</b></span>
            change in quantity sold.</div>""",
            unsafe_allow_html=True,
        )

        if e_val > 0:
            st.markdown(
                f"""<div class="anomaly"><b>Odd result:</b>
                {term("this coefficient is positive", "sign")} (sales rising with price), which is
                very unlikely to be real behavior at this scale. Treat it as a symptom of price
                endogeneity or a small sample, not a literal finding.</div>""",
                unsafe_allow_html=True,
            )

        st.plotly_chart(demand_curve_figure(e_val, price, symbol), use_container_width=True)
        st.caption(result["caveat"])

# ---- category comparison --------------------------------------------------

st.divider()
st.subheader("How categories compare")
st.markdown(
    f"""<div style="color:{INK_SECONDARY}; font-size:0.86rem; margin-bottom:6px;">
    Bars further left = {term("more elastic", "elastic")} (price-sensitive shoppers).
    Bars near zero or positive = {term("inelastic", "inelastic")} or anomalous.
    Your current selection is highlighted in yellow.</div>""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60)
def fetch_all_category_estimates(names: tuple) -> list:
    out = []
    for name in names:
        try:
            r = requests.get(f"{API_BASE_URL}/elasticity", params={"category": name}, timeout=10)
            if r.status_code == 200:
                out.append(r.json())
        except requests.exceptions.RequestException:
            pass
    return out


category_estimates = fetch_all_category_estimates(tuple(reported_categories))
if category_estimates:
    highlight = category or (result and result.get("scope"))
    renamed = [{"category": r["scope"], "elasticity": r["elasticity"]} for r in category_estimates]
    st.plotly_chart(
        category_comparison_figure(renamed, highlight=highlight),
        use_container_width=True,
    )
    st.caption(
        "Top 10 most negative and top 10 least negative/positive of the reported categories. "
        "Categories with opaque source codes instead of names (e.g. scanner-data 'PBV') are "
        "hidden here but still reachable through a product lookup."
    )

# ---- methodology + glossary ------------------------------------------------

with st.expander("Plain-English glossary (everything the tooltips say, in one place)"):
    st.markdown(
        "\n".join(
            f"- **{name}** &mdash; {text}"
            for name, text in [
                ("Price elasticity", GLOSSARY["elasticity"]),
                ("Negative vs positive sign", GLOSSARY["sign"]),
                ("Elastic", GLOSSARY["elastic"]),
                ("Inelastic", GLOSSARY["inelastic"]),
                ("95% confidence interval", GLOSSARY["ci"]),
                ("R²", GLOSSARY["r2"]),
                ("N (sample size)", GLOSSARY["n"]),
            ]
        )
    )

with st.expander("Methodology and caveats"):
    try:
        methodology = fetch_methodology()
        st.json(methodology)
    except Exception:
        st.write("Methodology unavailable.")
    st.markdown(
        "- Price is not randomly assigned in this data -- these are descriptive associations, "
        "not causal effects.\n"
        "- Category taxonomies are not harmonized across the underlying sources.\n"
        "- See the repo README for the full data quality writeup."
    )
