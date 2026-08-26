/* ============================================================================
   Price Sensitivity Lab

   No framework, no CDN, no external chart library. The previous build pulled
   ~3.5MB of Plotly from cdn.plot.ly and every chart died with an uncaught
   "Plotly is not defined" wherever that host was unreachable. The three charts
   here are hand-built SVG: responsive, theme-aware, keyboard-reachable, and
   each one has a table-view twin so no value is gated behind a hover.

   Scenario arithmetic mirrors src/elasticity_math.py so the slider can respond
   without a round-trip. tests/ pins both sides against the same expectations.
   ========================================================================== */
(function () {
  "use strict";

  /* ------------------------------------------------------------- helpers -- */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  var SVG_NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs) {
    var el = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k) && attrs[k] != null) {
        el.setAttribute(k, String(attrs[k]));
      }
    }
    return el;
  }
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;   // never innerHTML for data
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  var CURRENCY_SYMBOLS = { GBP: "£", USD: "$", EUR: "€", INR: "₹" };

  var nf1 = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var nf2 = new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var nf3 = new Intl.NumberFormat(undefined, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  var nfInt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

  function signedPct(v, digits) {
    var n = digits === 0 ? nfInt : digits === 2 ? nf2 : nf1;
    return (v > 0 ? "+" : v < 0 ? "−" : "") + n.format(Math.abs(v)) + "%";
  }
  function money(v) { return state.currencySymbol + nf2.format(v); }

  /* -------------------------------------------------- scenario arithmetic -- */
  /* Mirror of src/elasticity_math.py — keep the two in step. */
  var REVENUE_BREAKEVEN = -1.0;

  function quantityRatio(e, m) { return Math.pow(m, e); }
  function revenueRatio(e, m) { return Math.pow(m, 1 + e); }
  function profitRatio(e, m, price, cost) {
    var marginNow = price - cost;
    if (marginNow <= 0) return null;
    return ((price * m - cost) / marginNow) * quantityRatio(e, m);
  }
  function pct(ratio) { return Math.round((ratio - 1) * 1e4) / 100; }

  function buildScenario(opts) {
    var m = 1 + opts.pctPriceChange / 100;
    var pctRev = pct(revenueRatio(opts.elasticity, m));
    var out = {
      pctPriceChange: opts.pctPriceChange,
      multiplier: m,
      newPrice: opts.price != null ? opts.price * m : null,
      pctQuantityChange: pct(quantityRatio(opts.elasticity, m)),
      pctRevenueChange: pctRev,
      pctRevenueLow: null,
      pctRevenueHigh: null,
      pctProfitChange: null,
      direction: Math.abs(pctRev) < 0.5 ? "flat" : pctRev > 0 ? "up" : "down"
    };
    if (opts.ciLow != null && opts.ciHigh != null) {
      var a = pct(revenueRatio(opts.ciLow, m));
      var b = pct(revenueRatio(opts.ciHigh, m));
      out.pctRevenueLow = Math.min(a, b);
      out.pctRevenueHigh = Math.max(a, b);
    }
    if (opts.price != null && opts.cost != null && opts.cost < opts.price) {
      var pr = profitRatio(opts.elasticity, m, opts.price, opts.cost);
      if (pr != null) out.pctProfitChange = pct(pr);
    }
    return out;
  }

  /* --------------------------------------------------------------- state -- */
  var state = {
    scope: "all",              // "all" | "category" | "product"
    category: null,
    product: null,             // {id, name, categoryIndex, price}
    price: 10,
    cost: null,
    change: 10,
    currencySymbol: "£",
    estimates: null,
    products: [],              // [{id, name, category, price}]
    domain: [-3, 0]
  };

  var GLOSSARY = [
    ["Price sensitivity", "price-sensitivity",
      "How sharply shoppers change what they buy when a price moves. Economists call it price elasticity: the percentage change in units sold for every 1% the price rises."],
    ["Break-even point", "breakeven",
      "The price sensitivity at which revenue doesn't care what you do with the price — whatever you gain per unit, you lose in units. It sits at −1. Below it, discounting grows revenue. Above it, raising the price does."],
    ["Likely range", "likely-range",
      "A 95% confidence interval. Run this analysis on many similar samples and the true answer would land inside this range about 19 times out of 20. Narrow means precise; wide means take the headline number lightly."],
    ["Weekly observations", "observations",
      "One row of evidence is one product in one week: what it sold for, and how many moved. More rows means a steadier estimate."],
    ["Explained variation", "explained",
      "How much of the week-to-week swing in units sold tracks price alone (statisticians call it R²). It is normally low in retail, because season, promotion and stock move sales too. Low doesn't mean wrong."],
    ["Revenue vs profit", "revenue-profit",
      "Revenue is price × units. Profit is what's left after unit cost. A discount can lift revenue while shrinking profit, which is why the cost box on the left matters."]
  ];
  var GLOSSARY_BY_KEY = {};
  GLOSSARY.forEach(function (g) { GLOSSARY_BY_KEY[g[1]] = { title: g[0], body: g[2] }; });

  /* --------------------------------------------------------------- theme -- */
  var themeMedia = window.matchMedia("(prefers-color-scheme: dark)");

  function applyTheme(pref) {
    if (pref === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", pref);
    document.body.setAttribute("data-theme-pref", pref);
    $$(".theme-toggle button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.themeSet === pref));
    });
    try { localStorage.setItem("pep-theme", pref); } catch (e) { /* private mode */ }
    renderCharts();
  }

  function initTheme() {
    var saved = "system";
    try { saved = localStorage.getItem("pep-theme") || "system"; } catch (e) { /* ignore */ }
    applyTheme(saved);
    $$(".theme-toggle button").forEach(function (b) {
      b.addEventListener("click", function () { applyTheme(b.dataset.themeSet); });
    });
    var onSystemChange = function () {
      if (document.body.getAttribute("data-theme-pref") === "system") renderCharts();
    };
    if (themeMedia.addEventListener) themeMedia.addEventListener("change", onSystemChange);
    else themeMedia.addListener(onSystemChange);
  }

  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  /* ------------------------------------------------------------ data i/o -- */
  function fetchJSON(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.detail || (r.status + " " + r.statusText));
        });
      }
      return r.json();
    });
  }

  function currentEstimate() {
    if (!state.estimates) return null;
    var name = null;
    if (state.scope === "category") name = state.category;
    else if (state.scope === "product" && state.product) name = state.product.category;
    if (!name) return state.estimates.overall;
    var found = state.estimates.by_category.filter(function (r) { return r.category === name; })[0];
    // A product in the excluded catch-all bucket has no category estimate of
    // its own; the whole-range figure is the honest fallback.
    return found || state.estimates.overall;
  }

  function scopeLabel() {
    if (state.scope === "product" && state.product) return state.product.name;
    if (state.scope === "category" && state.category) return state.category;
    return "Whole range";
  }

  function basisLabel() {
    var est = currentEstimate();
    if (!est) return "";
    if (state.scope === "product" && state.product) {
      var reported = state.estimates.by_category.some(function (r) {
        return r.category === state.product.category;
      });
      return reported
        ? "Priced as " + state.product.category
        : "No separate estimate for " + state.product.category + " — using the whole range";
    }
    if (state.scope === "category") return "Category estimate";
    return "All 11 categories pooled";
  }

  /* ----------------------------------------------------------- url state -- */
  function writeURL() {
    var p = new URLSearchParams();
    if (state.scope !== "all") p.set("scope", state.scope);
    if (state.scope === "category" && state.category) p.set("category", state.category);
    if (state.scope === "product" && state.product) p.set("product", state.product.id);
    if (state.change !== 10) p.set("change", String(state.change));
    if (state.cost != null) p.set("cost", String(state.cost));
    var qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }

  function readURL() {
    var p = new URLSearchParams(location.search);
    var scope = p.get("scope");
    if (scope === "category" || scope === "product" || scope === "all") state.scope = scope;
    var change = parseFloat(p.get("change"));
    if (!isNaN(change)) state.change = clamp(Math.round(change), -40, 40);
    var cost = parseFloat(p.get("cost"));
    if (!isNaN(cost) && cost >= 0) state.cost = cost;
    return { category: p.get("category"), product: p.get("product") };
  }

  /* ======================================================================
     CHARTS
     ====================================================================== */

  /* Charts are sized from their container, never from a fixed floor: an SVG
     with a width attribute wider than its box contributes that width as
     min-content and drags the whole grid track out with it. The fallback only
     covers the first paint, before layout has measured anything. */
  function chartWidth(host) {
    return Math.max(240, host.clientWidth || 320);
  }

  function chartRoot(W, H, label) {
    return svg("svg", {
      viewBox: "0 0 " + W + " " + H, width: "100%", height: H,
      preserveAspectRatio: "xMidYMid meet", role: "img", "aria-label": label
    });
  }

  /* Redrawing a chart replaces its whole SVG, which throws away whatever the
     keyboard was on. Without this, a user arrowing along the scenario curve
     loses focus after the very first keypress. */
  function redrawChart(hostSel, draw) {
    var host = $(hostSel);
    if (!host) return;
    var active = document.activeElement;
    var key = host.contains(active)
      ? (active.getAttribute("data-focus-key") || "")
      : null;
    draw();
    if (key === null) return;
    var next = (key && host.querySelector('[data-focus-key="' + key + '"]'))
      || host.querySelector(".chart-hit");
    if (next) next.focus({ preventScroll: true });
  }

  function chartTooltip(host) {
    var tip = el("div", "chart-tip");
    tip.hidden = true;
    host.appendChild(tip);
    return {
      node: tip,
      show: function (x, y, title, rows) {
        clear(tip);
        tip.appendChild(el("div", "chart-tip-title", title));
        rows.forEach(function (r) {
          var row = el("div", "chart-tip-row");
          if (r.color) {
            var key = el("span", "chart-tip-key");
            key.style.background = r.color;
            if (r.dashed) { key.style.background = "none"; key.style.borderTop = "2px dashed " + r.color; }
            row.appendChild(key);
          }
          row.appendChild(el("span", "chart-tip-name", r.name));
          row.appendChild(el("span", "chart-tip-val", r.value));
          tip.appendChild(row);
        });
        tip.hidden = false;
        var hw = host.clientWidth;
        var tw = tip.offsetWidth;
        tip.style.left = clamp(x - tw / 2, 4, Math.max(4, hw - tw - 4)) + "px";
        tip.style.top = Math.max(4, y - tip.offsetHeight - 12) + "px";
      },
      hide: function () { tip.hidden = true; }
    };
  }

  /* ---- 1. price-sensitivity scale (the signature graphic) ---------------- */
  /* This is the one graphic the whole product hangs on: it puts the estimate,
     its uncertainty, the -1 revenue threshold and the rest of the catalogue on
     a single ruler, so "which side of break-even am I on" is a glance, not a
     calculation. */
  function drawScaleChart() {
    var host = $("#scale-chart");
    var est = currentEstimate();
    if (!host || !est) return;

    var W = chartWidth(host);
    var narrow = W < 560;

    var padL = narrow ? 10 : 24, padR = narrow ? 10 : 24;
    var bandT = 30, bandH = narrow ? 92 : 100;
    var bandB = bandT + bandH;
    var axisY = bandB;
    var midY = bandT + bandH * 0.66;
    var H = axisY + (narrow ? 62 : 44);

    var d0 = state.domain[0], d1 = state.domain[1];
    var x = function (v) { return padL + ((v - d0) / (d1 - d0)) * (W - padL - padR); };

    var accent = token("--accent");
    var quiet = token("--mark-quiet");
    var quieter = token("--mark-quieter");
    var surface = token("--surface");

    clear(host);
    var root = chartRoot(W, H,
        "Price sensitivity scale from " + nf1.format(d0) + " to 0, with the break-even point marked at minus 1. " +
        scopeLabel() + " sits at " + nf2.format(est.elasticity) +
        ", likely range " + nf2.format(est.ci_low) + " to " + nf2.format(est.ci_high) + ", which is " +
        (est.elasticity < REVENUE_BREAKEVEN ? "left of break-even, where discounting grows revenue."
                                            : "right of break-even, where raising the price grows revenue."));

    var bx = x(REVENUE_BREAKEVEN);

    // Two zones. The 2px gap at the threshold is the separator — no strokes
    // drawn around either fill.
    root.appendChild(svg("rect", {
      x: x(d0), y: bandT, width: Math.max(0, bx - x(d0) - 1), height: bandH,
      fill: accent, opacity: 0.13, rx: 8
    }));
    root.appendChild(svg("rect", {
      x: bx + 1, y: bandT, width: Math.max(0, x(d1) - bx - 1), height: bandH,
      fill: quiet, opacity: 0.13, rx: 8
    }));

    // Zone captions live inside their own zone, so the meaning is where the
    // colour is rather than in a legend somewhere else.
    function zoneCaption(cx, lines, anchor) {
      lines.forEach(function (line, i) {
        var t = svg("text", {
          x: cx, y: bandT + 17 + i * 14, class: "chart-label",
          "text-anchor": anchor || "middle"
        });
        t.textContent = line;
        root.appendChild(t);
      });
    }
    if (narrow) {
      zoneCaption(x(d0) + 8, ["discount →", "revenue up"], "start");
      zoneCaption(x(d1) - 8, ["raise price →", "revenue up"], "end");
    } else {
      zoneCaption((x(d0) + bx) / 2, ["Discounting grows revenue"]);
      zoneCaption((bx + x(d1)) / 2, ["Raising the price grows revenue"]);
    }

    // Every other reported category, as a faint reference tick: one estimate
    // read against the spread instead of in isolation.
    state.estimates.by_category.forEach(function (row) {
      root.appendChild(svg("line", {
        x1: x(row.elasticity), y1: bandB - 16, x2: x(row.elasticity), y2: bandB - 7,
        stroke: quieter, "stroke-width": 2, "stroke-linecap": "round"
      }));
    });

    // Break-even threshold — solid hairline, always labelled.
    root.appendChild(svg("line", {
      x1: bx, y1: bandT - 12, x2: bx, y2: bandB, stroke: token("--ink-3"), "stroke-width": 1.5
    }));
    var beLabel = svg("text", { x: bx, y: bandT - 18, class: "chart-strong", "text-anchor": "middle" });
    beLabel.textContent = "break-even";
    root.appendChild(beLabel);

    // Likely range, then the estimate itself.
    var lo = x(est.ci_low), hi = x(est.ci_high);
    root.appendChild(svg("rect", {
      x: Math.min(lo, hi) - 1, y: midY - 11, width: Math.max(6, Math.abs(hi - lo) + 2), height: 22,
      fill: accent, opacity: 0.34, rx: 5
    }));
    root.appendChild(svg("rect", {
      x: x(est.elasticity) - 2.5, y: midY - 15, width: 5, height: 30,
      fill: accent, rx: 2.5, stroke: surface, "stroke-width": 2
    }));

    // Value pill, nudged to stay inside the frame at either extreme.
    var labelX = clamp(x(est.elasticity), padL + 30, W - padR - 30);
    var pillW = 52, pillH = 20, pillY = midY - 41;
    root.appendChild(svg("rect", {
      x: labelX - pillW / 2, y: pillY, width: pillW, height: pillH,
      rx: 6, fill: accent
    }));
    var pillText = svg("text", {
      x: labelX, y: pillY + 14, "text-anchor": "middle", class: "chart-pill-text"
    });
    pillText.textContent = nf2.format(est.elasticity);
    root.appendChild(pillText);

    // Axis
    root.appendChild(svg("line", { x1: x(d0), y1: axisY, x2: x(d1), y2: axisY, class: "chart-axis" }));
    var step = narrow ? 1 : 0.5;
    for (var t = Math.ceil(d0 / step) * step; t <= d1 + 1e-9; t += step) {
      var tx = x(t);
      root.appendChild(svg("line", { x1: tx, y1: axisY, x2: tx, y2: axisY + 5, class: "chart-axis" }));
      var tick = svg("text", { x: tx, y: axisY + 19, class: "chart-tick", "text-anchor": "middle" });
      tick.textContent = t === 0 ? "0" : "−" + (step === 1 ? String(Math.abs(t)) : nf1.format(Math.abs(t)));
      root.appendChild(tick);
    }

    // Two anchored labels rather than one padded string — SVG collapses
    // runs of whitespace, so a single centred string ran its halves together.
    var leftTitle = svg("text", { x: padL, y: H - 6, class: "chart-label", "text-anchor": "start" });
    leftTitle.textContent = narrow ? "← more sensitive" : "← shoppers more price-sensitive";
    root.appendChild(leftTitle);
    var rightTitle = svg("text", { x: W - padR, y: H - 6, class: "chart-label", "text-anchor": "end" });
    rightTitle.textContent = narrow ? "less sensitive →" : "less price-sensitive →";
    root.appendChild(rightTitle);

    host.appendChild(root);
  }

  /* ---- 2. scenario curve ------------------------------------------------ */
  function drawScenarioChart() {
    var host = $("#scenario-chart");
    var est = currentEstimate();
    if (!host || !est) return;

    var W = chartWidth(host);
    var narrow = W < 520;
    var H = narrow ? 260 : 300;
    var padL = 44, padR = narrow ? 16 : 58, padT = 18, padB = 46;
    var plotW = W - padL - padR, plotH = H - padT - padB;

    var xs = [];
    for (var p = -40; p <= 40; p += 1) xs.push(p);
    var series = xs.map(function (v) {
      var m = 1 + v / 100;
      return { p: v, units: quantityRatio(est.elasticity, m) * 100, revenue: revenueRatio(est.elasticity, m) * 100 };
    });

    var vals = series.reduce(function (acc, d) { return acc.concat([d.units, d.revenue]); }, []);
    var yMin = Math.min.apply(null, vals), yMax = Math.max.apply(null, vals);
    // Clean, rounded bounds that always contain the 100 baseline.
    var stepY = yMax - yMin > 160 ? 50 : yMax - yMin > 80 ? 25 : 10;
    yMin = Math.floor(Math.min(yMin, 100) / stepY) * stepY;
    yMax = Math.ceil(Math.max(yMax, 100) / stepY) * stepY;

    var x = function (v) { return padL + ((v + 40) / 80) * plotW; };
    var y = function (v) { return padT + plotH - ((v - yMin) / (yMax - yMin)) * plotH; };

    var accent = token("--accent");
    var quiet = token("--mark-quiet");
    var surface = token("--surface");

    clear(host);
    var root = chartRoot(W, H,
        "Line chart of units and revenue against price change, both indexed to 100 at today's price. " +
        "At " + signedPct(state.change) + ", units are at " +
        nfInt.format(quantityRatio(est.elasticity, 1 + state.change / 100) * 100) + " and revenue at " +
        nfInt.format(revenueRatio(est.elasticity, 1 + state.change / 100) * 100) + ".");

    // gridlines + y ticks
    for (var gy = yMin; gy <= yMax + 1e-9; gy += stepY) {
      root.appendChild(svg("line", { x1: padL, y1: y(gy), x2: padL + plotW, y2: y(gy), class: "chart-grid" }));
      var yl = svg("text", { x: padL - 8, y: y(gy) + 4, class: "chart-tick", "text-anchor": "end" });
      yl.textContent = nfInt.format(gy);
      root.appendChild(yl);
    }

    // the "today" baseline: 100 index at 0% change
    root.appendChild(svg("line", {
      x1: padL, y1: y(100), x2: padL + plotW, y2: y(100),
      stroke: token("--axis"), "stroke-width": 1
    }));
    root.appendChild(svg("line", {
      x1: x(0), y1: padT, x2: x(0), y2: padT + plotH,
      stroke: token("--axis"), "stroke-width": 1
    }));
    var todayLabel = svg("text", { x: x(0), y: padT + plotH + 30, class: "chart-label", "text-anchor": "middle" });
    todayLabel.textContent = "today";
    root.appendChild(todayLabel);

    // x ticks
    [-40, -20, 20, 40].forEach(function (v) {
      var xl = svg("text", { x: x(v), y: padT + plotH + 16, class: "chart-tick", "text-anchor": "middle" });
      xl.textContent = (v > 0 ? "+" : "−") + Math.abs(v) + "%";
      root.appendChild(xl);
    });
    var axisTitle = svg("text", {
      x: padL + plotW / 2, y: H - 6, class: "chart-label", "text-anchor": "middle"
    });
    axisTitle.textContent = "Price change";
    root.appendChild(axisTitle);

    function path(key) {
      return series.map(function (d, i) {
        return (i ? "L" : "M") + x(d.p).toFixed(2) + " " + y(d[key]).toFixed(2);
      }).join(" ");
    }

    // Units is context (dashed, quiet); revenue is the story (solid, accent).
    // The dash is a second channel so the two never rely on hue alone.
    root.appendChild(svg("path", {
      d: path("units"), fill: "none", stroke: quiet, "stroke-width": 1.75,
      "stroke-dasharray": "6 4", "stroke-linecap": "round", opacity: 0.75
    }));
    root.appendChild(svg("path", {
      d: path("revenue"), fill: "none", stroke: accent, "stroke-width": 2.5,
      "stroke-linejoin": "round", "stroke-linecap": "round"
    }));

    // current scenario marker
    var cur = series.filter(function (d) { return d.p === state.change; })[0] || series[40];
    var crosshair = svg("line", {
      x1: x(cur.p), y1: padT, x2: x(cur.p), y2: padT + plotH,
      stroke: accent, "stroke-width": 1.5, opacity: 0.45
    });
    root.appendChild(crosshair);
    [["units", quiet], ["revenue", accent]].forEach(function (pair) {
      root.appendChild(svg("circle", {
        cx: x(cur.p), cy: y(cur[pair[0]]), r: 5,
        fill: pair[1], stroke: surface, "stroke-width": 2
      }));
    });

    // direct-label the one series the story is about
    if (!narrow) {
      var labelRight = x(cur.p) < padL + plotW * 0.62;
      var lab = svg("text", {
        x: x(cur.p) + (labelRight ? 10 : -10),
        y: clamp(y(cur.revenue) - 10, padT + 10, padT + plotH),
        class: "chart-strong", "text-anchor": labelRight ? "start" : "end"
      });
      lab.textContent = "revenue " + nfInt.format(cur.revenue);
      root.appendChild(lab);
    }

    host.appendChild(root);

    // hover / focus layer — one tooltip listing every series at that x
    var tip = chartTooltip(host);
    var hit = svg("rect", {
      x: padL, y: padT, width: plotW, height: plotH, class: "chart-hit",
      tabindex: "0", role: "application", "data-focus-key": "plot",
      "aria-label": "Explore the price-change curve. Use left and right arrow keys."
    });
    root.appendChild(hit);

    function readAt(pv) {
      var d = series.filter(function (s) { return s.p === pv; })[0];
      if (!d) return;
      tip.show(x(d.p), y(Math.max(d.units, d.revenue)), signedPct(d.p, 0) + " price change", [
        { name: "Revenue", value: nfInt.format(d.revenue), color: accent },
        { name: "Units", value: nfInt.format(d.units), color: quiet, dashed: true }
      ]);
    }
    function pointerAt(ev) {
      var rect = host.getBoundingClientRect();
      var px = ((ev.clientX - rect.left) / rect.width) * W;
      readAt(clamp(Math.round(((px - padL) / plotW) * 80 - 40), -40, 40));
    }
    hit.addEventListener("pointermove", pointerAt);
    hit.addEventListener("pointerleave", tip.hide);
    hit.addEventListener("focus", function () { readAt(state.change); });
    hit.addEventListener("blur", tip.hide);
    hit.addEventListener("keydown", function (ev) {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
      ev.preventDefault();
      setChange(clamp(state.change + (ev.key === "ArrowRight" ? 1 : -1), -40, 40));
      readAt(state.change);
    });
  }

  /* ---- 3. category comparison ------------------------------------------- */
  function comparisonRows() {
    var rows = state.estimates.by_category.map(function (r) {
      return { name: r.category, value: r.elasticity, ci: [r.ci_low, r.ci_high], n: r.n_observations };
    });
    rows.push({
      name: "Whole range", value: state.estimates.overall.elasticity,
      ci: [state.estimates.overall.ci_low, state.estimates.overall.ci_high],
      n: state.estimates.overall.n_observations, isOverall: true
    });
    rows.sort(function (a, b) { return a.value - b.value; });
    return rows;
  }

  function highlightedRowName() {
    if (state.scope === "category" && state.category) return state.category;
    if (state.scope === "product" && state.product) {
      var reported = state.estimates.by_category.some(function (r) { return r.category === state.product.category; });
      return reported ? state.product.category : "Whole range";
    }
    return "Whole range";
  }

  function drawCompareChart() {
    var host = $("#compare-chart");
    if (!host || !state.estimates) return;

    var rows = comparisonRows();
    var highlight = highlightedRowName();

    var W = chartWidth(host);
    // Below ~560px the category names can't share a row with the bars without
    // being truncated, so the label moves above its own bar instead.
    var stacked = W < 560;
    var padL = stacked ? 4 : 176;
    var padR = 52, padT = 26, padB = 34;
    var rowH = stacked ? 46 : 30;
    var barH = stacked ? 14 : 18;         // <= 24px per mark spec
    var H = padT + rows.length * rowH + padB;

    var d0 = state.domain[0], d1 = 0;
    var x = function (v) { return padL + ((v - d0) / (d1 - d0)) * (W - padL - padR); };

    var accent = token("--accent");
    var quiet = token("--mark-quiet");

    clear(host);
    var root = chartRoot(W, H,
        "Bar chart comparing price sensitivity across " + rows.length +
        " groups, from " + rows[0].name + " at " + nf2.format(rows[0].value) +
        " to " + rows[rows.length - 1].name + " at " + nf2.format(rows[rows.length - 1].value) +
        ". " + highlight + " is highlighted.");

    // x gridlines
    for (var t = Math.ceil(d0); t <= 0; t += 1) {
      root.appendChild(svg("line", { x1: x(t), y1: padT - 6, x2: x(t), y2: H - padB + 2, class: "chart-grid" }));
      var tk = svg("text", { x: x(t), y: H - padB + 18, class: "chart-tick", "text-anchor": "middle" });
      tk.textContent = t === 0 ? "0" : "−" + Math.abs(t);
      root.appendChild(tk);
    }

    // break-even threshold — solid hairline, labelled (never dashed)
    var bx = x(REVENUE_BREAKEVEN);
    root.appendChild(svg("line", {
      x1: bx, y1: padT - 14, x2: bx, y2: H - padB + 2,
      stroke: token("--ink-3"), "stroke-width": 1.5
    }));
    var beTag = svg("text", { x: bx, y: padT - 18, class: "chart-strong", "text-anchor": "middle" });
    beTag.textContent = "break-even";
    root.appendChild(beTag);

    var tip = chartTooltip(host);

    rows.forEach(function (row, i) {
      var isOn = row.name === highlight;
      var top = padT + i * rowH;
      var barY = stacked ? top + 22 : top + (rowH - barH) / 2;
      var x0 = x(0), x1 = x(row.value);
      var w = Math.max(2, x0 - x1);

      if (stacked) {
        var above = svg("text", { x: 2, y: top + 13, class: isOn ? "chart-strong" : "chart-label" });
        above.textContent = row.name;
        root.appendChild(above);
      } else {
        var name = svg("text", {
          x: padL - 12, y: barY + barH / 2 + 4,
          class: isOn ? "chart-strong" : "chart-label", "text-anchor": "end"
        });
        name.textContent = row.name;
        root.appendChild(name);
      }

      // Bars grow left from the zero baseline: square at the baseline, 4px
      // rounded at the data end.
      var r = 4;
      var d = "M" + x0 + " " + barY +
        " H" + (x1 + r) + " a" + r + " " + r + " 0 0 0 " + (-r) + " " + r +
        " V" + (barY + barH - r) + " a" + r + " " + r + " 0 0 0 " + r + " " + r +
        " H" + x0 + " Z";
      root.appendChild(svg("path", { d: d, fill: isOn ? accent : quiet, opacity: isOn ? 1 : 0.85 }));

      // Value rides the data end of the bar, but never off the left edge:
      // on the stacked layout it sits with the name instead.
      var val;
      if (stacked) {
        val = svg("text", {
          x: W - 4, y: top + 13,
          class: isOn ? "chart-strong" : "chart-tick", "text-anchor": "end"
        });
      } else {
        val = svg("text", {
          x: Math.max(38, x1 - 8), y: barY + barH / 2 + 4,
          class: isOn ? "chart-strong" : "chart-tick", "text-anchor": "end"
        });
      }
      val.textContent = nf2.format(row.value);
      root.appendChild(val);

      // Hit target spans the whole row and clears the 24px minimum.
      var hit = svg("rect", {
        x: 0, y: top, width: W, height: Math.max(24, rowH), class: "chart-hit",
        tabindex: "0", role: "button", "data-focus-key": "row-" + row.name,
        "aria-label": row.name + ": price sensitivity " + nf2.format(row.value) +
          ", likely range " + nf2.format(row.ci[0]) + " to " + nf2.format(row.ci[1]) +
          (row.isOverall ? "" : ". Activate to see this category.")
      });
      var showTip = function () {
        tip.show(x1 + w / 2, barY, row.name, [
          { name: "Sensitivity", value: nf2.format(row.value), color: isOn ? accent : quiet },
          { name: "Likely range", value: nf2.format(row.ci[0]) + " to " + nf2.format(row.ci[1]) },
          { name: "Observations", value: nfInt.format(row.n) }
        ]);
      };
      hit.addEventListener("pointerenter", showTip);
      hit.addEventListener("pointerleave", tip.hide);
      hit.addEventListener("focus", showTip);
      hit.addEventListener("blur", tip.hide);
      var pick = function () {
        if (row.isOverall) setScope("all");
        else { state.category = row.name; setScope("category"); }
      };
      hit.addEventListener("click", pick);
      hit.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); }
      });
      root.appendChild(hit);
    });

    host.appendChild(root);
  }

  function renderCharts() {
    if (!state.estimates) return;
    redrawChart("#scale-chart", drawScaleChart);
    redrawChart("#scenario-chart", drawScenarioChart);
    redrawChart("#compare-chart", drawCompareChart);
  }

  /* ======================================================================
     RENDERING
     ====================================================================== */

  var VERDICT_ICONS = {
    up: "M7 14l5-5 5 5",              // price up grows revenue
    down: "M7 10l5 5 5-5",            // price down grows revenue
    unclear: "M12 8v5M12 16.5h.01"
  };

  function verdictIcon(kind) {
    var s = svg("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      "stroke-width": 2.4, "stroke-linecap": "round", "stroke-linejoin": "round" });
    s.appendChild(svg("circle", { cx: 12, cy: 12, r: 9.2, "stroke-width": 1.6, opacity: 0.35 }));
    s.appendChild(svg("path", { d: VERDICT_ICONS[kind] || VERDICT_ICONS.unclear }));
    return s;
  }

  function renderVerdict() {
    var est = currentEstimate();
    if (!est) return;
    var advice = est.advice;

    $("#verdict-scope").textContent = scopeLabel();
    $("#verdict-basis").textContent = basisLabel();

    var kind = !advice.certain ? "unclear"
      : advice.raising_price === "gains revenue" ? "up" : "down";

    var head = $("#verdict-heading");
    head.setAttribute("data-direction", kind);
    var iconHost = $("#verdict-icon");
    clear(iconHost);
    iconHost.appendChild(verdictIcon(kind));
    $("#verdict-text").textContent = advice.headline;
    $("#verdict-detail").textContent = advice.detail;
  }

  function renderScenario() {
    var est = currentEstimate();
    if (!est) return;

    var sc = buildScenario({
      elasticity: est.elasticity,
      pctPriceChange: state.change,
      price: state.price,
      cost: state.cost,
      ciLow: est.ci_low,
      ciHigh: est.ci_high
    });

    $("#scenario-sub").textContent =
      "Moving " + scopeLabel().toLowerCase() + " from " + money(state.price) +
      " to " + money(sc.newPrice) + " — a " + signedPct(state.change, 0) + " change.";

    var host = $("#scenario-tiles");
    clear(host);

    function tile(label, value, unit, sub, tone) {
      var t = el("div", "tile");
      if (tone) t.setAttribute("data-tone", tone);
      t.appendChild(el("div", "tile-label", label));
      var v = el("div", "tile-value", value);
      if (unit) { var u = el("span", "unit", unit); v.appendChild(u); }
      t.appendChild(v);
      t.appendChild(el("div", "tile-sub", sub));
      return t;
    }

    host.appendChild(tile("New price", money(sc.newPrice), null,
      "was " + money(state.price), "accent"));

    host.appendChild(tile("Units sold", signedPct(sc.pctQuantityChange), null,
      "for every 100 you sell now, about " + nfInt.format(100 * (1 + sc.pctQuantityChange / 100))));

    var revTone = sc.direction === "up" ? "good" : sc.direction === "down" ? "critical" : null;
    var revSub = sc.pctRevenueLow != null
      ? "likely between " + signedPct(sc.pctRevenueLow) + " and " + signedPct(sc.pctRevenueHigh)
      : "";
    host.appendChild(tile("Revenue", signedPct(sc.pctRevenueChange), null, revSub, revTone));

    if (sc.pctProfitChange != null) {
      var profTone = sc.pctProfitChange > 0.5 ? "good" : sc.pctProfitChange < -0.5 ? "critical" : null;
      host.appendChild(tile("Gross profit", signedPct(sc.pctProfitChange), null,
        "at " + money(state.cost) + " a unit", profTone));
    }

    // The thing a revenue-only tool can quietly get you fired for. Two cases
    // worth interrupting for: revenue and profit pointing opposite ways, and
    // revenue moving so much further than profit that the headline flatters
    // the decision.
    var note = $("#profit-note");
    var rev = sc.pctRevenueChange, prof = sc.pctProfitChange;
    var material = Math.abs(rev) > 0.5 && prof != null && Math.abs(prof) > 0.5;
    var text = null;
    var tone = "notice-info";

    if (prof != null && material && (rev > 0) !== (prof > 0)) {
      text = "Revenue and profit point opposite ways here: revenue goes " +
        (rev > 0 ? "up " : "down ") + signedPct(Math.abs(rev)) +
        " while gross profit goes " + (prof > 0 ? "up " : "down ") + signedPct(Math.abs(prof)) +
        ". Profit is usually the one to follow.";
      tone = "notice-warn";
    } else if (prof != null && Math.abs(rev) > 5 && Math.abs(rev) > Math.abs(prof) * 3) {
      text = "Revenue moves much further than profit here: " + signedPct(rev) +
        " revenue but only " + signedPct(prof) + " gross profit. At " + money(state.cost) +
        " a unit, most of the extra volume goes on covering cost.";
      tone = "notice-warn";
    } else if (prof == null && state.cost == null) {
      text = "This is revenue, not profit. Add your unit cost on the left to see whether " +
        "the money you keep moves the same way.";
    }

    note.classList.remove("notice-info", "notice-warn");
    note.classList.add(tone);
    if (text) { $("#profit-note-text").textContent = text; note.hidden = false; }
    else { note.hidden = true; }

    renderScenarioLegend();
    renderScenarioTable(est);
  }

  function renderScenarioLegend() {
    var host = $("#scenario-legend");
    clear(host);
    [["Revenue", token("--accent"), false], ["Units", token("--mark-quiet"), true]].forEach(function (s) {
      var item = el("span", "legend-item");
      var key = el("span", "legend-key");
      if (s[2]) { key.setAttribute("data-shape", "dash"); key.style.color = s[1]; }
      else { key.style.background = s[1]; }
      item.appendChild(key);
      item.appendChild(document.createTextNode(s[0]));
      host.appendChild(item);
    });
  }

  function renderScenarioTable(est) {
    var host = $("#scenario-table");
    clear(host);
    var table = el("table");
    var cap = el("caption", null,
      "Units and revenue at each price change, indexed to 100 at today's price of " + money(state.price) + ".");
    table.appendChild(cap);

    var thead = el("thead");
    var hr = el("tr");
    ["Price change", "New price", "Units index", "Revenue index"].forEach(function (h) {
      var th = el("th", null, h);
      th.setAttribute("scope", "col");
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el("tbody");
    for (var v = -40; v <= 40; v += 5) {
      var m = 1 + v / 100;
      var tr = el("tr");
      if (v === state.change) tr.setAttribute("data-current", "true");
      tr.appendChild(el("td", null, signedPct(v, 0)));
      tr.appendChild(el("td", null, money(state.price * m)));
      tr.appendChild(el("td", null, nfInt.format(quantityRatio(est.elasticity, m) * 100)));
      tr.appendChild(el("td", null, nfInt.format(revenueRatio(est.elasticity, m) * 100)));
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    host.appendChild(table);
  }

  function renderCompareTable() {
    var host = $("#compare-table");
    clear(host);
    var rows = comparisonRows();
    var highlight = highlightedRowName();

    var table = el("table");
    table.appendChild(el("caption", null,
      "Price sensitivity by category. Below −1, discounting grows revenue."));
    var thead = el("thead");
    var hr = el("tr");
    ["Group", "Sensitivity", "Likely range", "Observations"].forEach(function (h) {
      var th = el("th", null, h);
      th.setAttribute("scope", "col");
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var tbody = el("tbody");
    rows.forEach(function (r) {
      var tr = el("tr");
      if (r.name === highlight) tr.setAttribute("data-current", "true");
      tr.appendChild(el("td", null, r.name));
      tr.appendChild(el("td", null, nf3.format(r.value)));
      tr.appendChild(el("td", null, nf2.format(r.ci[0]) + " to " + nf2.format(r.ci[1])));
      tr.appendChild(el("td", null, nfInt.format(r.n)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    host.appendChild(table);
  }

  function renderEvidence() {
    var est = currentEstimate();
    if (!est) return;
    var ev = est.evidence;
    var host = $("#evidence-list");
    clear(host);

    var precisionScore = { "very precise": 4, "precise": 3, "rough": 2, "very rough": 1 }[ev.precision] || 1;
    var sampleScore = { "very strong": 4, "strong": 3, "moderate": 2, "thin": 1 }[ev.sample] || 1;
    var fitScore = { "a lot": 4, "a moderate amount": 3, "a little": 2, "very little": 1 }[ev.fit] || 1;

    function item(label, grade, score, detail, termKey) {
      var wrap = el("div", "evidence-item");
      var dt = el("dt", null, label);
      wrap.appendChild(dt);
      var g = el("div", "evidence-grade");
      g.appendChild(el("b", null, grade));
      var meter = el("div", "meter");
      meter.setAttribute("role", "img");
      meter.setAttribute("aria-label", score + " out of 4");
      for (var i = 1; i <= 4; i++) {
        var s = el("span");
        s.setAttribute("data-on", String(i <= score));
        meter.appendChild(s);
      }
      g.appendChild(meter);
      wrap.appendChild(g);
      var dd = el("dd");
      dd.appendChild(document.createTextNode(detail + " "));
      if (termKey) dd.appendChild(makeTermButton(termKey, "What's this?"));
      wrap.appendChild(dd);
      host.appendChild(wrap);
    }

    item("How much evidence", ev.sample.charAt(0).toUpperCase() + ev.sample.slice(1),
      sampleScore, ev.sample_detail, "observations");
    item("How precise", ev.precision.charAt(0).toUpperCase() + ev.precision.slice(1),
      precisionScore,
      ev.precision_detail + " The likely range runs " + nf2.format(est.ci_low) +
      " to " + nf2.format(est.ci_high) + ".", "likely-range");
    item("How much price explains", ev.fit.charAt(0).toUpperCase() + ev.fit.slice(1),
      fitScore, ev.fit_detail, "explained");
  }

  function renderCompareNote() {
    var excluded = state.estimates.excluded_categories || [];
    if (!excluded.length) { $("#compare-note").textContent = ""; return; }
    $("#compare-note").textContent =
      "Not shown: " + excluded.map(function (e) { return e.category; }).join(", ") +
      ". Those products don't share enough in common to price as one group, so they fall back to the whole-range figure.";
  }

  function renderMethod() {
    var m = state.estimates.methodology || {};
    $("#method-categories").textContent =
      "The source data ships no category field — only a free-text product description — so categories " +
      "here are assigned by keyword rules against that description. A \"Retrospot Cake Case\" lands in Kitchen " +
      "& Dining because of the word cake. It is a reasonable guess, not a merchandising hierarchy, and a " +
      "handful of products certainly sit in the wrong bucket.";

    var excluded = state.estimates.excluded_categories || [];
    $("#method-excluded").textContent = excluded.length
      ? "A category is only reported once it clears 500 weekly observations across at least 15 products. " +
        excluded.map(function (e) { return e.category; }).join(", ") + " never clears that bar."
      : "";

    var spec = $("#method-spec");
    clear(spec);
    var labels = {
      method: "Model", source_dataset: "Source", category_assignment: "Categories",
      cleaning: "Cleaning", exclusion_thresholds: "Reporting threshold", note: "Caveat"
    };
    Object.keys(labels).forEach(function (k) {
      if (!m[k]) return;
      var row = el("div");
      row.appendChild(el("dt", null, labels[k]));
      row.appendChild(el("dd", null, m[k]));
      spec.appendChild(row);
    });
  }

  function renderGlossary() {
    var host = $("#glossary-list");
    clear(host);
    GLOSSARY.forEach(function (g) {
      // dt and dd are wrapped so the grid lays out pairs, not loose cells.
      var pair = el("div");
      pair.appendChild(el("dt", null, g[0]));
      pair.appendChild(el("dd", null, g[2]));
      host.appendChild(pair);
    });
  }

  function renderAll() {
    renderVerdict();
    renderScenario();
    renderEvidence();
    renderCompareTable();
    renderCompareNote();
    renderCharts();
    writeURL();
  }

  /* ======================================================================
     TERM POPOVERS  (click / keyboard — never hover-only)
     ====================================================================== */
  var openTerm = null;

  function makeTermButton(key, label) {
    var b = el("button", "term", label || key);
    b.type = "button";
    b.setAttribute("data-term", key);
    b.setAttribute("aria-expanded", "false");
    return b;
  }

  function closeTerm() {
    if (!openTerm) return;
    openTerm.setAttribute("aria-expanded", "false");
    $("#term-pop").hidden = true;
    openTerm = null;
  }

  function toggleTerm(btn) {
    if (openTerm === btn) { closeTerm(); return; }
    closeTerm();
    var entry = GLOSSARY_BY_KEY[btn.dataset.term];
    if (!entry) return;
    var pop = $("#term-pop");
    $("#term-pop-title").textContent = entry.title;
    $("#term-pop-body").textContent = entry.body;
    pop.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    openTerm = btn;

    var r = btn.getBoundingClientRect();
    var top = r.bottom + window.scrollY + 8;
    var left = clamp(r.left + window.scrollX + r.width / 2 - pop.offsetWidth / 2,
      12, Math.max(12, document.documentElement.clientWidth - pop.offsetWidth - 12));
    pop.style.top = top + "px";
    pop.style.left = left + "px";
    $("#term-pop-close").focus();
  }

  function initTerms() {
    // index.html carries a few .term buttons of its own; give them the same
    // contract makeTermButton() applies, so none can drift.
    $$(".term").forEach(function (b) {
      if (!b.hasAttribute("aria-expanded")) b.setAttribute("aria-expanded", "false");
    });
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest ? ev.target.closest(".term") : null;
      if (btn) { ev.preventDefault(); toggleTerm(btn); return; }
      if (!ev.target.closest || !ev.target.closest("#term-pop")) closeTerm();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && openTerm) {
        var btn = openTerm;
        closeTerm();
        btn.focus();
      }
    });
    $("#term-pop-close").addEventListener("click", function () {
      var btn = openTerm;
      closeTerm();
      if (btn) btn.focus();
    });
  }

  /* ======================================================================
     CONTROLS
     ====================================================================== */
  function announce(msg) { $("#live-region").textContent = msg; }

  function setScope(scope) {
    state.scope = scope;
    $$("#controls [data-scope]").forEach(function (b) {
      b.setAttribute("aria-checked", String(b.dataset.scope === scope));
    });
    $("#field-category").hidden = scope !== "category";
    $("#field-product").hidden = scope !== "product";
    $("#scope-hint").textContent = {
      all: "Every product in the dataset, pooled into one estimate.",
      category: "One department at a time — shoppers behave differently across them.",
      product: "Products inherit their category's estimate; there isn't enough history to price each one alone."
    }[scope];

    if (scope === "category") {
      if (!state.category) state.category = state.estimates.by_category[0].category;
      $("#category-select").value = state.category;
      setPrice(state.price, true);
    } else if (scope === "product") {
      if (!state.product) selectProduct(defaultProduct(), true);
      else setPrice(state.product.price, true);
    }
    renderAll();
    announce(scopeLabel() + ". " + currentEstimate().advice.headline);
  }

  function defaultProduct() {
    // The catalogue's most recognisable SKU, and one that sits in a reported
    // category — the old build defaulted to whatever sorted first, which was an
    // inflatable globe from the excluded bucket.
    var preferred = ["85123A", "22423", "20725"];
    for (var i = 0; i < preferred.length; i++) {
      var hit = state.products.filter(function (p) { return p.id === preferred[i]; })[0];
      if (hit) return hit;
    }
    return state.products[0];
  }

  function setPrice(value, silent) {
    state.price = Math.max(0.01, value);
    $("#price-input").value = state.price.toFixed(2);
    validateCost();
    if (!silent) renderAll();
  }

  function setChange(value) {
    state.change = clamp(Math.round(value), -40, 40);
    $("#change-slider").value = String(state.change);
    $("#change-readout").textContent = signedPct(state.change, 0);
    $$(".quick-changes button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(Number(b.dataset.change) === state.change));
    });
    renderScenario();
    redrawChart("#scenario-chart", drawScenarioChart);
    writeURL();
  }

  function validateCost() {
    var input = $("#cost-input");
    var err = $("#cost-error");
    var raw = input.value.trim();
    if (raw === "") { state.cost = null; err.hidden = true; return true; }
    var v = parseFloat(raw);
    if (isNaN(v) || v < 0) {
      err.textContent = "Enter a cost of 0 or more.";
      err.hidden = false; state.cost = null; return false;
    }
    if (v >= state.price) {
      err.textContent = "Cost has to be below the current price of " + money(state.price) +
        " — otherwise there's no margin to grow.";
      err.hidden = false; state.cost = null; return false;
    }
    err.hidden = true; state.cost = v; return true;
  }

  function selectProduct(product, silent) {
    if (!product) return;
    state.product = product;
    $("#product-input").value = product.name;
    $("#product-clear").hidden = false;
    setPrice(product.price, true);
    if (!silent) { renderAll(); announce(product.name + " selected. " + currentEstimate().advice.headline); }
  }

  /* ---- product combobox -------------------------------------------------- */
  function initCombo() {
    var input = $("#product-input");
    var list = $("#product-listbox");
    var clearBtn = $("#product-clear");
    var active = -1;
    var matches = [];

    input.placeholder = "Search " + nfInt.format(state.products.length) + " products…";

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function search(q) {
      var needle = q.trim().toLowerCase();
      if (!needle) return state.products.slice(0, 40);
      var starts = [], contains = [];
      for (var i = 0; i < state.products.length; i++) {
        var p = state.products[i];
        var idx = p.name.toLowerCase().indexOf(needle);
        if (idx === 0 || p.id.toLowerCase() === needle) starts.push(p);
        else if (idx > 0) contains.push(p);
        if (starts.length + contains.length > 220) break;
      }
      return starts.concat(contains).slice(0, 40);
    }

    function highlightName(name, q) {
      var span = el("span", "combo-name");
      var needle = q.trim().toLowerCase();
      var idx = needle ? name.toLowerCase().indexOf(needle) : -1;
      if (idx < 0) { span.textContent = name; return span; }
      span.appendChild(document.createTextNode(name.slice(0, idx)));
      var mk = el("mark", null, name.slice(idx, idx + needle.length));
      span.appendChild(mk);
      span.appendChild(document.createTextNode(name.slice(idx + needle.length)));
      return span;
    }

    function open(q) {
      matches = search(q);
      clear(list);
      if (!matches.length) {
        list.appendChild(el("li", "combo-empty", "No product matches “" + q.trim() + "”."));
        list.hidden = false;
        input.setAttribute("aria-expanded", "true");
        return;
      }
      matches.forEach(function (p, i) {
        var li = el("li");
        li.id = "product-opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        li.appendChild(highlightName(p.name, q));
        li.appendChild(el("span", "combo-meta", state.currencySymbol + nf2.format(p.price)));
        li.addEventListener("mousedown", function (ev) {
          ev.preventDefault();
          selectProduct(p);
          close();
        });
        list.appendChild(li);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      setActive(-1);
    }

    function setActive(i) {
      var items = $$("li[role=option]", list);
      items.forEach(function (li) { li.setAttribute("aria-selected", "false"); });
      active = i;
      if (i >= 0 && items[i]) {
        items[i].setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", items[i].id);
        items[i].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    input.addEventListener("input", function () {
      clearBtn.hidden = !input.value;
      open(input.value);
    });
    input.addEventListener("focus", function () { open(input.value); });
    input.addEventListener("blur", function () { setTimeout(close, 120); });
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        if (list.hidden) { open(input.value); return; }
        var next = ev.key === "ArrowDown"
          ? Math.min(matches.length - 1, active + 1)
          : Math.max(0, active - 1);
        setActive(next);
      } else if (ev.key === "Enter") {
        if (!list.hidden && active >= 0) { ev.preventDefault(); selectProduct(matches[active]); close(); }
      } else if (ev.key === "Escape") {
        if (!list.hidden) { ev.preventDefault(); close(); }
      }
    });
    clearBtn.addEventListener("click", function () {
      input.value = "";
      clearBtn.hidden = true;
      input.focus();
      open("");
    });
  }

  function initControls() {
    $$("#controls [data-scope]").forEach(function (b) {
      b.addEventListener("click", function () { setScope(b.dataset.scope); });
      b.addEventListener("keydown", function (ev) {
        if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
        ev.preventDefault();
        var all = $$("#controls [data-scope]");
        var i = all.indexOf(b);
        var next = all[(i + (ev.key === "ArrowRight" ? 1 : all.length - 1)) % all.length];
        next.focus();
        setScope(next.dataset.scope);
      });
    });

    var catSelect = $("#category-select");
    state.estimates.by_category.forEach(function (r) {
      var opt = el("option", null, r.category);
      opt.value = r.category;
      catSelect.appendChild(opt);
    });
    catSelect.addEventListener("change", function () {
      state.category = catSelect.value;
      renderAll();
      announce(state.category + ". " + currentEstimate().advice.headline);
    });

    $("#price-input").addEventListener("input", function () {
      var v = parseFloat(this.value);
      if (!isNaN(v) && v > 0) { state.price = v; validateCost(); renderScenario(); writeURL(); }
    });
    $("#price-input").addEventListener("blur", function () {
      var v = parseFloat(this.value);
      setPrice(isNaN(v) || v <= 0 ? state.price : v);
    });

    var slider = $("#change-slider");
    slider.addEventListener("input", function () { setChange(Number(this.value)); });
    slider.addEventListener("change", function () {
      announce(signedPct(state.change, 0) + " price change: revenue " +
        signedPct(buildScenario({
          elasticity: currentEstimate().elasticity, pctPriceChange: state.change,
          price: state.price, cost: state.cost
        }).pctRevenueChange));
    });

    $$(".quick-changes button").forEach(function (b) {
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () { setChange(Number(b.dataset.change)); });
    });

    $("#cost-input").addEventListener("input", function () { validateCost(); renderScenario(); writeURL(); });

    $$("[data-table-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = document.getElementById(btn.dataset.tableToggle);
        var showing = btn.getAttribute("aria-expanded") === "true";
        btn.setAttribute("aria-expanded", String(!showing));
        target.hidden = showing;
        btn.textContent = showing ? "Table" : "Hide table";
      });
    });
  }

  /* ------------------------------------------------------------ resizing -- */
  function initResize() {
    var frame = null;
    var redraw = function () {
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(renderCharts);
    };
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(redraw);
      [$("#scale-chart"), $("#scenario-chart"), $("#compare-chart")].forEach(function (n) {
        if (n) ro.observe(n);
      });
    } else {
      window.addEventListener("resize", redraw);
    }
    // Archivo's metrics differ from the fallback, so re-measure once it lands.
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(redraw);
  }

  /* ================================================================ boot -- */
  function showBootError(message) {
    var box = $("#boot-error");
    $("#boot-error-detail").textContent = message;
    box.hidden = false;
    $("#layout").hidden = true;
  }

  function boot() {
    initTheme();
    initTerms();
    $("#boot-retry").addEventListener("click", function () {
      $("#boot-error").hidden = true;
      boot();
    });

    var wanted = readURL();

    Promise.all([fetchJSON("/estimates"), fetchJSON("/catalog")])
      .then(function (res) {
        state.estimates = res[0];
        state.currencySymbol = CURRENCY_SYMBOLS[res[1].currency] || "";
        $("#price-symbol").textContent = state.currencySymbol;
        $("#cost-symbol").textContent = state.currencySymbol;

        var cats = res[1].categories;
        state.products = res[1].products.map(function (row) {
          return { id: row[0], name: row[1], category: cats[row[2]], price: row[3] };
        });

        // Domain covers every estimate, padded, and always reaches 0.
        var lows = state.estimates.by_category.map(function (r) { return r.ci_low; })
          .concat([state.estimates.overall.ci_low]);
        state.domain = [Math.floor(Math.min.apply(null, lows) * 2 - 0.5) / 2, 0];

        $("#layout").hidden = false;

        if (wanted.category &&
            state.estimates.by_category.some(function (r) { return r.category === wanted.category; })) {
          state.category = wanted.category;
        }
        if (wanted.product) {
          var p = state.products.filter(function (q) { return q.id === wanted.product; })[0];
          if (p) state.product = p;
        }

        initCombo();
        initControls();
        initResize();
        renderGlossary();
        renderMethod();

        if (state.cost != null) {
          $("#cost-input").value = String(state.cost);
          $("#cost-block").open = true;
        }
        setChange(state.change);
        setScope(state.scope);
      })
      .catch(function (err) {
        showBootError(err.message + " The API may still be starting up.");
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
