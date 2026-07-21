"""
Static HTML/JS port of app.py's Streamlit dashboard, served directly by the
FastAPI app at "/" so the whole product deploys as one Vercel function.
Same palette, same copy, same chart specs -- just vanilla JS + Plotly.js
calling the sibling API endpoints instead of Streamlit widgets.
"""

DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Price Elasticity Predictor</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #0a0d12; color: #e8eaf0;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}
.container { max-width: 1200px; margin: 0 auto; padding: 2.2rem 1.5rem 3rem; }
h1, h2, h3 { margin: 0; }

/* ---- hover tooltips ---- */
.tip { position: relative; border-bottom: 1px dotted #6b7280; cursor: help; }
.tip::after {
  content: attr(data-tip);
  position: absolute; left: 50%; top: calc(100% + 8px);
  transform: translateX(-50%);
  width: 280px; text-transform: none; letter-spacing: normal;
  background: #1a2029; color: #e8eaf0; border: 1px solid rgba(255,255,255,0.10);
  border-radius: 8px; padding: 10px 12px;
  font-size: 0.8rem; font-weight: 400; line-height: 1.45;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  text-align: left; opacity: 0; visibility: hidden;
  transition: opacity 120ms ease; z-index: 1000; pointer-events: none;
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
}
.tip:hover::after { opacity: 1; visibility: visible; }

/* ---- header ---- */
.pep-header h1 { font-size: 1.7rem; letter-spacing: -0.01em; color: #e8eaf0; }
.pep-header .tagline { color: #9aa3b2; font-size: 0.92rem; margin-top: 2px; }
.status-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #0ca30c; margin-right: 6px; box-shadow: 0 0 6px rgba(12,163,12,0.8);
}

/* ---- layout ---- */
.columns { display: flex; gap: 32px; flex-wrap: wrap; margin-top: 18px; }
.col-input { flex: 1 1 320px; max-width: 380px; }
.col-result { flex: 2 1 480px; min-width: 0; }
.divider { border: none; border-top: 1px solid rgba(255,255,255,0.10); margin: 28px 0; }

/* ---- controls ---- */
label { display: block; font-size: 0.85rem; color: #9aa3b2; margin: 14px 0 6px; }
select, input[type=number] {
  width: 100%; background: #11151c; border: 1px solid rgba(255,255,255,0.10);
  color: #e8eaf0; border-radius: 8px; padding: 8px 10px; font-size: 0.95rem;
}
input[type=number] { font-family: "SF Mono", "Cascadia Code", Menlo, Consolas, monospace; }
.segmented {
  display: flex; background: #11151c; border: 1px solid rgba(255,255,255,0.10);
  border-radius: 8px; padding: 3px; gap: 2px; margin-top: 10px;
}
.segmented button {
  flex: 1; background: transparent; border: none; color: #9aa3b2;
  padding: 7px 10px; border-radius: 6px; cursor: pointer; font-size: 0.85rem;
}
.segmented button.active { background: #242b38; color: #e8eaf0; }

/* ---- stat tiles ---- */
.tile-row { display: flex; gap: 12px; margin: 4px 0 14px 0; flex-wrap: wrap; }
.tile {
  flex: 1 1 130px;
  background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.00)), #11151c;
  border: 1px solid rgba(255,255,255,0.10); border-radius: 10px; padding: 12px 14px;
}
.tile .label {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em;
  color: #9aa3b2; margin-bottom: 6px;
}
.tile .value {
  font-family: "SF Mono", "Cascadia Code", Menlo, Consolas, monospace;
  font-size: 1.45rem; font-weight: 600; color: #e8eaf0; font-variant-numeric: tabular-nums;
}
.tile .sub { font-size: 0.72rem; color: #6b7280; margin-top: 3px; }

/* ---- headline & callouts ---- */
.headline { font-size: 1.12rem; line-height: 1.6; color: #e8eaf0; margin: 6px 0 10px 0; }
.headline .num { font-family: "SF Mono", "Cascadia Code", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
.anomaly {
  border: 1px solid rgba(230,103,103,0.35); border-left: 3px solid #e66767;
  background: rgba(230,103,103,0.07); border-radius: 8px; padding: 10px 14px;
  font-size: 0.85rem; color: #e8eaf0; line-height: 1.5; margin-bottom: 10px;
}
.warn-box {
  background: rgba(201,133,0,0.1); border: 1px solid rgba(201,133,0,0.35);
  border-radius: 8px; padding: 10px 14px; font-size: 0.85rem; margin: 10px 0;
}
.error-box {
  background: rgba(230,103,103,0.1); border: 1px solid rgba(230,103,103,0.35);
  border-radius: 8px; padding: 10px 14px; font-size: 0.85rem; margin: 10px 0;
}

/* ---- expanders ---- */
details {
  background: #11151c; border: 1px solid rgba(255,255,255,0.10);
  border-radius: 8px; padding: 10px 14px; margin-top: 14px;
}
summary { cursor: pointer; color: #e8eaf0; font-size: 0.9rem; }
pre.methodology { background: #0a0d12; padding: 10px; border-radius: 8px; overflow: auto; font-size: 0.8rem; }
.caption { color: #6b7280; font-size: 0.78rem; margin-top: 6px; }
</style>
</head>
<body>
<div class="container">
  <div class="pep-header">
    <h1>Price Elasticity Predictor</h1>
    <div class="tagline"><span class="status-dot"></span>Log-log panel regression estimates of
    price elasticity from public retail data &middot; research/portfolio project, not pricing advice</div>
  </div>
  <div style="color:#9aa3b2; font-size:0.9rem; margin:10px 0 4px 0;">
    <span class="tip" data-tip="How strongly shoppers react to a price change. It is the % change in quantity sold when the price rises by 1%. Example: an elasticity of &minus;2 means a 10% price increase cuts sales by about 20%.">Price elasticity</span>
    measures how much sales move when prices move.
    Pick a product or category below &mdash; hover any dotted term or stat label for a plain-English explanation.
  </div>
  <div id="app"><div class="caption">Loading&hellip;</div></div>
</div>

<script>
const CURRENCY_SYMBOLS = {GBP: "£", USD: "$", INR: "₹", EUR: "€"};
const GLOSSARY = {
  elasticity: "How strongly shoppers react to a price change. It is the % change in quantity sold when the price rises by 1%. Example: an elasticity of −2 means a 10% price increase cuts sales by about 20%.",
  sign: "A negative number is normal: price goes up, sales go down. A positive number would mean people buy MORE when it gets pricier — almost always a data quirk here, not real behavior.",
  elastic: "Shoppers react strongly: raise the price 10% and sales fall MORE than 10%. Discounts pay off; price hikes are risky.",
  inelastic: "Shoppers barely react: raise the price 10% and sales fall LESS than 10%. People keep buying — think everyday essentials.",
  ci: "The 95% confidence interval: the range where the true value plausibly sits. A narrow range = precise estimate; a wide range = take the headline number with a grain of salt.",
  r2: "R-squared: how much of the ups and downs in sales the model explains, from 0 to 1. Low values are normal for retail data — price is only one of many reasons people buy.",
  n: "Sample size: how many product-month data points went into this estimate. More observations = a more trustworthy number.",
  typical_price: "The average price this product actually sold at in the data, filled in for you automatically. Change it freely — it only anchors the chart, not the elasticity itself.",
};
const BLUE = "#3987e5", RED = "#e66767", YELLOW = "#c98500", SURFACE = "#11151c",
      GRIDLINE = "#222835", INK_PRIMARY = "#e8eaf0", INK_SECONDARY = "#9aa3b2",
      INK_MUTED = "#6b7280", MONO = '"SF Mono","Cascadia Code",Menlo,Consolas,monospace';

let state = { mode: "By product", categories: [], products: [], selectedProduct: null, category: null, price: 10.00, result: null };

function term(label, key) { return `<span class="tip" data-tip="${GLOSSARY[key]}">${label}</span>`; }
function titleCase(s) { return s.replace(/\w\S*/g, t => t[0].toUpperCase() + t.slice(1).toLowerCase()); }
function isHumanReadable(c) { return c.length > 4 || c.includes(" "); }
function fmt2(n) { return Number(n).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) {
    let detail;
    try { detail = (await r.json()).detail; } catch (e) {}
    throw new Error(detail || r.statusText);
  }
  return r.json();
}

async function init() {
  try {
    const cats = await fetchJSON("/categories");
    state.categories = cats.reported.filter(isHumanReadable);
  } catch (e) {
    document.getElementById("app").innerHTML =
      `<div class="error-box">Can't reach the API. ${e.message}</div>`;
    return;
  }
  renderLayout();
  await setMode("By product");
}

function renderLayout() {
  document.getElementById("app").innerHTML = `
    <div class="columns">
      <div class="col-input">
        <h3>Look up an estimate</h3>
        <div class="segmented" id="segmented">
          <button data-mode="Overall">Overall</button>
          <button data-mode="By category">By category</button>
          <button data-mode="By product">By product</button>
        </div>
        <div id="mode-controls"></div>
      </div>
      <div class="col-result">
        <h3>Result</h3>
        <div id="result"></div>
      </div>
    </div>
    <hr class="divider" />
    <h3>How categories compare</h3>
    <div style="color:${INK_SECONDARY};font-size:0.86rem;margin-bottom:6px;">
      Bars further left = ${term("more elastic", "elastic")} (price-sensitive shoppers).
      Bars near zero or positive = ${term("inelastic", "inelastic")} or anomalous.
      Your current selection is highlighted in yellow.
    </div>
    <div id="comparison-chart"></div>
    <div class="caption" id="comparison-caption" style="display:none;">
      Top 10 most negative and top 10 least negative/positive of the reported categories.
      Categories with opaque source codes instead of names (e.g. scanner-data 'PBV') are
      hidden here but still reachable through a product lookup.
    </div>
    <details>
      <summary>Plain-English glossary (everything the tooltips say, in one place)</summary>
      <div style="margin-top:10px;font-size:0.9rem;line-height:1.6;">
        ${[["elasticity","Price elasticity"],["sign","Negative vs positive sign"],["elastic","Elastic"],
           ["inelastic","Inelastic"],["ci","95% confidence interval"],["r2","R²"],["n","N (sample size)"]]
          .map(([k, name]) => `<div>&bull; <b>${name}</b> &mdash; ${GLOSSARY[k]}</div>`).join("")}
      </div>
    </details>
    <details>
      <summary>Methodology and caveats</summary>
      <div id="methodology" style="margin-top:10px;"></div>
    </details>
  `;
  document.querySelectorAll("#segmented button").forEach(btn => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode));
  });
  loadMethodology();
}

async function setMode(mode) {
  state.mode = mode;
  state.category = null;
  state.selectedProduct = null;
  document.querySelectorAll("#segmented button").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
  const el = document.getElementById("mode-controls");

  if (mode === "Overall") {
    el.innerHTML = `<div id="price-section"></div>`;
    renderPriceInput(null);
    await runQuery();
  } else if (mode === "By category") {
    el.innerHTML = `<label for="category-select">Category</label>
      <select id="category-select">${state.categories.map(c => `<option value="${c}">${c}</option>`).join("")}</select>
      <div id="price-section"></div>`;
    document.getElementById("category-select").addEventListener("change", async e => {
      state.category = e.target.value;
      await runQuery();
    });
    state.category = state.categories[0] || null;
    renderPriceInput(null);
    await runQuery();
  } else {
    el.innerHTML = `<label for="cat-filter">Browse category</label>
      <select id="cat-filter"><option>All categories</option>${state.categories.map(c => `<option>${c}</option>`).join("")}</select>
      <div id="product-select-wrap"></div>
      <div id="price-section"></div>`;
    document.getElementById("cat-filter").addEventListener("change", e => loadProducts(e.target.value));
    await loadProducts("All categories");
  }
}

async function loadProducts(catFilter) {
  const wrap = document.getElementById("product-select-wrap");
  wrap.innerHTML = `<label for="product-select">Product</label><select id="product-select"><option>Loading&hellip;</option></select>`;
  let products;
  try {
    const q = catFilter && catFilter !== "All categories" ? `?category=${encodeURIComponent(catFilter)}` : "";
    products = (await fetchJSON(`/products${q}`)).products;
  } catch (e) {
    wrap.innerHTML = `<div class="error-box">Couldn't load the product directory: ${e.message}</div>`;
    return;
  }
  state.products = products;
  if (!products.length) {
    wrap.innerHTML += `<div class="caption">No products in this category.</div>`;
    renderPriceInput(null);
    return;
  }
  const sel = document.getElementById("product-select");
  sel.innerHTML = products.map(p => {
    const symbol = CURRENCY_SYMBOLS[p.currency] || "";
    return `<option value="${p.product_id}">${titleCase(p.product_name)}  ·  ${symbol}${fmt2(p.typical_price)}</option>`;
  }).join("");
  sel.addEventListener("change", () => selectProduct(sel.value));
  selectProduct(products[0].product_id);
}

function selectProduct(productId) {
  const product = state.products.find(p => p.product_id === productId);
  state.selectedProduct = product;
  document.getElementById("product-select").value = productId;
  renderPriceInput(product);
  runQuery();
}

function renderPriceInput(product) {
  const section = document.getElementById("price-section");
  const symbol = product ? (CURRENCY_SYMBOLS[product.currency] || "") : "";
  const value = product ? Number(product.typical_price) : 10.00;
  state.price = value;
  const help = product ? GLOSSARY.typical_price
    : "A reference price point. It anchors the demand-curve chart; the elasticity estimate itself doesn't depend on it.";
  const label = product ? `Price (${symbol})` : "Price (native currency of the source)";
  section.innerHTML = `<label class="tip" data-tip="${help}" for="price-input">${label}</label>
    <input type="number" id="price-input" min="0.01" step="0.5" value="${value}" />`;
  document.getElementById("price-input").addEventListener("change", e => {
    const v = parseFloat(e.target.value);
    if (!isNaN(v) && v > 0) { state.price = v; runQuery(); }
  });
}

async function runQuery() {
  const resultEl = document.getElementById("result");
  let result;
  try {
    const params = new URLSearchParams();
    if (state.category) params.set("category", state.category);
    if (state.selectedProduct) params.set("product_id", state.selectedProduct.product_id);
    if (state.price) params.set("price", state.price);
    result = await fetchJSON(`/elasticity?${params.toString()}`);
  } catch (e) {
    resultEl.innerHTML = `<div class="warn-box">${e.message}</div>`;
    return;
  }
  state.result = result;
  renderResult(result);
  loadComparisonChart();
}

function renderResult(result) {
  const eVal = result.elasticity;
  const symbol = state.selectedProduct ? (CURRENCY_SYMBOLS[state.selectedProduct.currency] || "") : "";
  const tiles = `
    <div class="tile-row">
      <div class="tile">
        <div class="label">${term("Elasticity", "elasticity")}</div>
        <div class="value" style="color:${eVal > 0 ? RED : BLUE};">${eVal.toFixed(3)}</div>
        <div class="sub">${eVal > 0 ? "⚠ positive sign" : "negative = normal"}</div>
      </div>
      <div class="tile">
        <div class="label">${term("95% CI", "ci")}</div>
        <div class="value">[${result.ci_low.toFixed(2)}, ${result.ci_high.toFixed(2)}]</div>
        <div class="sub">plausible range</div>
      </div>
      <div class="tile">
        <div class="label">${term("R²", "r2")}</div>
        <div class="value">${result.r_squared.toFixed(3)}</div>
        <div class="sub">variance explained</div>
      </div>
      <div class="tile">
        <div class="label">${term("N", "n")}</div>
        <div class="value">${result.n_observations.toLocaleString()}</div>
        <div class="sub">product-months</div>
      </div>
    </div>`;

  let scopeLabel = result.scope;
  if (state.selectedProduct) scopeLabel = `${titleCase(state.selectedProduct.product_name)} (${result.scope})`;
  const interpKey = result.interpretation.includes("inelastic") ? "inelastic" : "elastic";
  const qtyChange = result.pct_quantity_change_for_10pct_price_increase;

  const headline = `<div class="headline"><b>${scopeLabel}</b> is ${term(result.interpretation, interpKey)}.
    A 10% price increase is associated with a
    <span class="num" style="color:${qtyChange > 0 ? RED : BLUE};"><b>${qtyChange > 0 ? "+" : ""}${qtyChange.toFixed(1)}%</b></span>
    change in quantity sold.</div>`;

  const anomaly = eVal > 0
    ? `<div class="anomaly"><b>Odd result:</b> ${term("this coefficient is positive", "sign")}
       (sales rising with price), which is very unlikely to be real behavior at this scale.
       Treat it as a symptom of price endogeneity or a small sample, not a literal finding.</div>`
    : "";

  document.getElementById("result").innerHTML =
    `${tiles}${headline}${anomaly}<div id="demand-chart"></div><div class="caption">${result.caveat}</div>`;

  drawDemandCurve(eVal, state.price, symbol);
}

function darkLayout(height) {
  return {
    plot_bgcolor: SURFACE, paper_bgcolor: SURFACE,
    font: {color: INK_PRIMARY, family: "system-ui,-apple-system,Segoe UI,sans-serif"},
    margin: {l: 10, r: 10, t: 10, b: 10}, height,
    hoverlabel: {bgcolor: "#1a2029", bordercolor: "rgba(255,255,255,0.15)", font: {color: INK_PRIMARY}},
  };
}

function drawDemandCurve(elasticity, price, symbol) {
  const multipliers = Array.from({length: 100}, (_, i) => 0.5 + i * (1.0 / 99));
  const quantityIndex = multipliers.map(m => Math.pow(m, elasticity));
  const line = {
    x: multipliers, y: quantityIndex, mode: "lines", line: {color: BLUE, width: 2},
    hovertemplate: "price x%{x:.2f} → quantity x%{y:.2f}<extra></extra>", showlegend: false,
  };
  const markers = {
    x: [1.0, 1.1], y: [1.0, Math.pow(1.1, elasticity)], mode: "markers",
    marker: {color: [INK_SECONDARY, elasticity > 0 ? RED : BLUE], size: 9, line: {color: SURFACE, width: 2}},
    text: ["baseline price", "price +10%"],
    hovertemplate: "%{text}: quantity x%{y:.3f}<extra></extra>", showlegend: false,
  };
  const xTitle = price == null ? "Price relative to baseline" : `Price relative to ${symbol}${fmt2(price)}`;
  const layout = Object.assign(darkLayout(340), {
    xaxis: {title: xTitle, tickformat: ".0%", gridcolor: GRIDLINE, zeroline: false},
    yaxis: {title: "Quantity relative to baseline", tickformat: ".0%", gridcolor: GRIDLINE, zeroline: false},
    shapes: [{type: "line", x0: 1, x1: 1, y0: 0, y1: 1, yref: "paper", line: {dash: "dot", color: INK_MUTED, width: 1}}],
  });
  Plotly.newPlot("demand-chart", [line, markers], layout, {displayModeBar: false, responsive: true});
}

async function loadComparisonChart() {
  const highlight = state.category || (state.result && state.result.scope);
  const results = await Promise.all(state.categories.map(async name => {
    try {
      const r = await fetchJSON(`/elasticity?category=${encodeURIComponent(name)}`);
      return {category: r.scope, elasticity: r.elasticity};
    } catch (e) { return null; }
  }));
  const clean = results.filter(Boolean);
  if (!clean.length) return;
  drawComparisonChart(clean, highlight);
  document.getElementById("comparison-caption").style.display = "block";
}

function drawComparisonChart(categories, highlight) {
  const sorted = [...categories].sort((a, b) => a.elasticity - b.elasticity);
  const combined = new Map();
  [...sorted.slice(0, 10), ...sorted.slice(-10)].forEach(c => combined.set(c.category, c));
  const top = Array.from(combined.values()).sort((a, b) => a.elasticity - b.elasticity);
  const colors = top.map(c => c.category === highlight ? YELLOW : (c.elasticity > 0 ? RED : BLUE));

  const trace = {
    x: top.map(c => c.elasticity), y: top.map(c => c.category), type: "bar", orientation: "h",
    marker: {color: colors, line: {color: SURFACE, width: 1}},
    text: top.map(c => c.elasticity.toFixed(2)), textposition: "outside",
    textfont: {family: MONO, color: INK_SECONDARY, size: 11},
    hovertemplate: "%{y}: elasticity %{x:.3f}<extra></extra>",
  };
  const layout = Object.assign(darkLayout(520), {
    xaxis: {title: "Elasticity  (more negative = shoppers more price-sensitive)", gridcolor: GRIDLINE, zeroline: false},
    yaxis: {title: null, gridcolor: GRIDLINE, autorange: "reversed"},
    showlegend: false,
    shapes: [{type: "line", x0: 0, x1: 0, y0: 0, y1: 1, yref: "paper", line: {color: INK_MUTED, width: 1}}],
  });
  Plotly.newPlot("comparison-chart", [trace], layout, {displayModeBar: false, responsive: true});
}

async function loadMethodology() {
  const el = document.getElementById("methodology");
  try {
    const m = await fetchJSON("/methodology");
    el.innerHTML = `<pre class="methodology">${JSON.stringify(m, null, 2)}</pre>
      <div style="font-size:0.85rem; line-height:1.6; margin-top:8px;">
        &bull; Price is not randomly assigned in this data -- these are descriptive associations, not causal effects.<br/>
        &bull; Category taxonomies are not harmonized across the underlying sources.<br/>
        &bull; See the repo README for the full data quality writeup.
      </div>`;
  } catch (e) {
    el.innerHTML = "Methodology unavailable.";
  }
}

init();
</script>
</body>
</html>
"""
