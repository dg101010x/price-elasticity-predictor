/* ============================================================================
   Price Sensitivity Lab — signed-in pages

   app.js draws everything the public page draws (verdict, break-even scale,
   scenario curve, category chart, other markets, evidence, method) against
   whatever estimates PSL_CONFIG points it at. This file adds what only a
   signed-in business has: sign-in and onboarding, the uploader and its
   column-mapping step, the headline ticket, recommendations whose every
   number can be traced to the estimate it came from, and upload history.

   Same rules as app.js: no framework, no CDN, textContent (never innerHTML)
   for anything that came from a server or a file.
   ========================================================================== */
(function () {
  "use strict";

  var CONFIG = window.PSL_CONFIG || (window.PSL_CONFIG = {});
  var PAGE = document.body.getAttribute("data-page");

  /* ------------------------------------------------------------- helpers -- */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function show(node, on) { if (node) node.hidden = !on; }

  var nfInt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  var dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
  var dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

  // Stored figures are shown with exactly the digits they were stored with --
  // the same digits a recommendation is allowed to quote -- with a real minus.
  function fig(v) {
    if (v == null) return "—";
    if (Number.isInteger(v) && Math.abs(v) >= 1000) return (v < 0 ? "−" : "") + nfInt.format(Math.abs(v));
    return String(v).replace(/^-/, "−");
  }
  function plural(n, one, many) { return nfInt.format(n) + " " + (n === 1 ? one : many); }
  function when(iso) { try { return dateTime.format(new Date(iso)); } catch (e) { return iso; } }
  function day(iso) { try { return dateOnly.format(new Date(iso + "T00:00:00")); } catch (e) { return iso; } }

  function api(method, url, body, raw) {
    var opts = { method: method, credentials: "same-origin", headers: {} };
    if (raw) { opts.body = raw; opts.headers["Content-Type"] = "application/octet-stream"; }
    else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (r.status === 401 && PAGE !== "login") {
          location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
          return new Promise(function () {});
        }
        if (!r.ok) {
          var err = new Error(typeof data.detail === "string" ? data.detail : "Something went wrong (" + r.status + ").");
          err.status = r.status;
          throw err;
        }
        return data;
      });
    });
  }

  /* ------------------------------------------------------ theme + shell -- */
  // app.js owns the theme on pages that draw charts; the rest need it too.
  function initTheme() {
    function apply(pref) {
      if (pref === "system") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", pref);
      document.body.setAttribute("data-theme-pref", pref);
      $$(".theme-toggle button").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.dataset.themeSet === pref));
      });
      try { localStorage.setItem("pep-theme", pref); } catch (e) { /* private mode */ }
    }
    var saved = "system";
    try { saved = localStorage.getItem("pep-theme") || "system"; } catch (e) { /* ignore */ }
    apply(saved);
    $$(".theme-toggle button").forEach(function (b) {
      b.addEventListener("click", function () { apply(b.dataset.themeSet); });
    });
  }

  function initShell() {
    if (!CONFIG.lab) initTheme();
    var signout = $("[data-signout]");
    if (signout) {
      signout.addEventListener("click", function () {
        signout.disabled = true;
        api("POST", "/api/auth/logout").then(function () { location.href = "/login"; },
                                             function () { location.href = "/login"; });
      });
    }
  }

  function showEmpty() {
    show($("#empty-state"), true);
    show($("#layout"), false);
    show($("#boot-error"), false);
    return true;
  }

  // The lab pages have no estimate to draw until something has been uploaded.
  CONFIG.onBootError = function (err) {
    if (err && err.status === 404) return showEmpty();
    if (err && err.status === 401) {
      location.href = "/login?next=" + encodeURIComponent(location.pathname);
      return true;
    }
    return false;
  };

  /* ================================================================ login == */
  function initLogin() {
    var mode = "signin";
    var form = $("#auth-form");
    var errorBox = $("#auth-error");
    var message = $("#auth-message");
    var submit = $("#auth-submit");
    var next = CONFIG.next || "/dashboard";

    function setError(text) { errorBox.textContent = text || ""; show(errorBox, !!text); }
    function setMessage(text) { message.textContent = text || ""; show(message, !!text); }

    if (!CONFIG.configured) {
      show($("#auth-unavailable"), true);
      $$("#auth-form input, #auth-form button, [data-auth-mode]").forEach(function (n) { n.disabled = true; });
      return;
    }

    function setMode(m) {
      mode = m;
      $$("[data-auth-mode]").forEach(function (b) { b.setAttribute("aria-checked", String(b.dataset.authMode === m)); });
      $("#auth-heading").textContent = m === "signin" ? "Sign in" : "Create an account";
      submit.textContent = m === "signin" ? "Sign in" : "Create account";
      $("#auth-password").setAttribute("autocomplete", m === "signin" ? "current-password" : "new-password");
      show($("#password-hint"), m === "signup");
      setError(""); setMessage("");
    }
    $$("[data-auth-mode]").forEach(function (b) {
      b.addEventListener("click", function () { setMode(b.dataset.authMode); });
      b.addEventListener("keydown", function (ev) {
        if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
        ev.preventDefault();
        var other = $('[data-auth-mode="' + (b.dataset.authMode === "signin" ? "signup" : "signin") + '"]');
        other.focus(); setMode(other.dataset.authMode);
      });
    });

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var email = $("#auth-email").value.trim();
      var password = $("#auth-password").value;
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError("Enter the email address you sign in with."); $("#auth-email").focus(); return; }
      if (password.length < (mode === "signup" ? 6 : 1)) {
        setError(mode === "signup" ? "Use a password of at least 6 characters." : "Enter your password.");
        $("#auth-password").focus(); return;
      }
      setError(""); setMessage("");
      submit.disabled = true;
      api("POST", mode === "signin" ? "/api/auth/login" : "/api/auth/signup", { email: email, password: password })
        .then(function (res) {
          if (res.signed_in) { location.href = mode === "signin" ? next : (res.next || "/onboarding"); return; }
          setMessage(res.message);
          setMode("signin");
          setMessage(res.message);
          $("#auth-email").value = email;
        })
        .catch(function (err) { setError(err.message); })
        .then(function () { submit.disabled = false; });
    });

    // Back from a confirmation email: Supabase hands the new session over
    // in the URL fragment. Exchange it for cookies, then drop it from the URL.
    var hash = new URLSearchParams(location.hash.replace(/^#/, ""));
    if (hash.get("error_description")) {
      setError(hash.get("error_description").replace(/\+/g, " ") + " Sign in with your password instead.");
      history.replaceState(null, "", location.pathname + location.search);
    } else if (hash.get("access_token") && hash.get("refresh_token")) {
      setMessage("Email confirmed. Signing you in…");
      history.replaceState(null, "", location.pathname + location.search);
      api("POST", "/api/auth/session", {
        access_token: hash.get("access_token"), refresh_token: hash.get("refresh_token"),
        expires_in: Number(hash.get("expires_in")) || 3600
      }).then(function (res) { location.href = res.next || "/onboarding"; },
              function (err) { setMessage(""); setError(err.message); });
    }
  }

  /* ============================================================ uploader == */
  var FIELD_ORDER = ["product_key", "description", "category", "date", "units", "price", "revenue"];
  var HEAD_BYTES = 256 * 1024;
  var MAX_COMPRESSED = 4.4 * 1024 * 1024;     // Vercel refuses request bodies over 4.5 MB

  function gzip(blob) {
    if (!window.CompressionStream) return Promise.resolve(blob);
    return new Response(blob.stream().pipeThrough(new CompressionStream("gzip"))).blob();
  }

  function headOf(file) {
    // Enough rows to recognise the columns, cut at a line break so the last
    // row isn't half a row.
    return file.slice(0, HEAD_BYTES).text().then(function (text) {
      if (file.size <= HEAD_BYTES) return text;
      var cut = text.lastIndexOf("\n");
      return cut > 0 ? text.slice(0, cut + 1) : text;
    });
  }

  function initUploader(onDone) {
    var root = $("#uploader");
    if (!root) return;
    var input = $("#file-input");
    var zone = $("#dropzone");
    var mapping = $("#mapping");
    var errorBox = $("#upload-error");
    var progress = $("#upload-progress");
    var result = $("#upload-result");
    var button = $("#upload-button");
    var current = { file: null, proposal: null };

    function setError(text) { errorBox.textContent = text || ""; show(errorBox, !!text); }

    function reset() {
      current = { file: null, proposal: null };
      input.value = "";
      show(zone, true); show(mapping, false); show(progress, false); show(result, false);
      setError("");
    }

    function busy(text) {
      $("#progress-text").textContent = text;
      show(progress, true);
      button.disabled = true;
    }
    function idle() { show(progress, false); button.disabled = false; }

    function choose(file) {
      if (!file) return;
      reset();
      if (!/\.(csv|txt)$/i.test(file.name) && file.type && file.type.indexOf("csv") < 0) {
        show(mapping, false);
        showResultNotice("critical", "That isn't a CSV file. Export your sales as CSV (most tills and spreadsheets have “Save as CSV”) and choose it again.");
        return;
      }
      current.file = file;
      show(zone, false);
      busy("Reading the columns…");
      headOf(file).then(function (text) {
        return gzip(new Blob([text], { type: "text/csv" }));
      }).then(function (body) {
        return api("POST", "/api/uploads/inspect", undefined, body);
      }).then(function (proposal) {
        idle();
        current.proposal = proposal;
        renderMapping(file, proposal);
      }).catch(function (err) {
        idle();
        show(zone, true);
        showResultNotice("critical", err.message);
      });
    }

    function renderMapping(file, proposal) {
      $("#file-line").textContent = file.name + " · " + (file.size / 1024 < 1024
        ? nfInt.format(Math.ceil(file.size / 1024)) + " KB"
        : (file.size / 1048576).toFixed(1) + " MB") + " · " + proposal.columns.length + " columns";

      var rows = $("#mapping-rows");
      clear(rows);
      var byField = {};
      proposal.fields.forEach(function (f) { byField[f.field] = f; });

      FIELD_ORDER.forEach(function (key) {
        var f = byField[key];
        if (!f) return;
        var tr = el("tr");
        var needsCheck = !f.confident && (f.required || f.column);
        tr.setAttribute("data-check", String(!!needsCheck));
        var what = el("td");
        what.appendChild(document.createTextNode(f.label));
        if (needsCheck) what.appendChild(el("span", "map-flag", "check"));
        what.appendChild(el("span", "map-optional",
          f.required ? "Required" : f.one_of ? "This or the other price field" : "Optional"));
        tr.appendChild(what);

        var cell = el("td");
        var select = el("select");
        select.setAttribute("data-field", key);
        select.setAttribute("aria-label", "Column for " + f.label);
        var none = el("option", null, "— not in this file —");
        none.value = "";
        select.appendChild(none);
        proposal.columns.forEach(function (c) {
          var o = el("option", null, c);
          o.value = c;
          select.appendChild(o);
        });
        select.value = f.column || "";
        cell.appendChild(select);
        tr.appendChild(cell);

        var sample = el("td", "t-sample");
        function refreshSample() {
          var col = select.value;
          sample.textContent = col
            ? proposal.sample.slice(0, 3).map(function (r) { return r[col]; }).filter(function (v) { return v !== "" && v != null; }).join(" · ")
            : "";
        }
        refreshSample();
        select.addEventListener("change", function () {
          refreshSample();
          tr.setAttribute("data-check", "false");
          var flag = $(".map-flag", what);
          if (flag) flag.remove();
        });
        tr.appendChild(sample);
        rows.appendChild(tr);
      });

      var dateField = $("#date-order-field");
      $$('input[name="date-order"]').forEach(function (r) { r.checked = false; });
      show(dateField, !proposal.date_order_certain);

      var warn = !!proposal.needs_confirmation;
      $("#mapping-warning-text").textContent = !proposal.date_order_certain
        ? "The dates could be read either way round, and some columns may need checking. Settle both below before uploading."
        : "Some columns couldn't be matched by name for certain. Check the rows marked “check” before uploading.";
      show($("#mapping-warning"), warn);
      button.textContent = warn ? "Confirm columns and upload" : "Upload and fit";
      show(mapping, true);
      (warn ? $("tr[data-check=true] select", rows) || button : button).focus();
    }

    function chosenMapping() {
      var map = {};
      $$("#mapping-rows select").forEach(function (s) { map[s.dataset.field] = s.value || null; });
      return map;
    }

    function validate(map) {
      var labels = {};
      current.proposal.fields.forEach(function (f) { labels[f.field] = f.label; });
      var missing = ["product_key", "date", "units"].filter(function (k) { return !map[k]; });
      if (missing.length) return "Choose a column for " + missing.map(function (k) { return labels[k]; }).join(", ") + ".";
      if (!map.price && !map.revenue) return "Choose a unit price column or a sales amount column.";
      var used = Object.keys(map).map(function (k) { return map[k]; }).filter(Boolean);
      if (new Set(used).size !== used.length) return "The same column is chosen twice. Each column can only fill one field.";
      if (!current.proposal.date_order_certain && !$('input[name="date-order"]:checked'))
        return "Say how the dates are written — day first or month first.";
      return null;
    }

    function upload() {
      var map = chosenMapping();
      var problem = validate(map);
      if (problem) { setError(problem); return; }
      setError("");
      var order = current.proposal.date_order_certain
        ? current.proposal.date_order
        : $('input[name="date-order"]:checked').value;
      var started = Date.now();
      busy("Compressing…");
      var timer = null;
      gzip(current.file).then(function (body) {
        if (body.size > MAX_COMPRESSED) {
          throw new Error("That file is too large to send, even compressed. Roll it up to one row per " +
                          "product per week, or upload a shorter period.");
        }
        busy("Uploading and fitting your estimate…");
        timer = setInterval(function () {
          $("#progress-text").textContent = "Uploading and fitting your estimate… " +
            Math.round((Date.now() - started) / 1000) + "s";
        }, 1000);
        var q = new URLSearchParams({
          filename: current.file.name, mapping: JSON.stringify(map),
          currency: $("#currency-select").value
        });
        if (order) q.set("date_order", order);
        return api("POST", "/api/uploads?" + q.toString(), undefined, body);
      }).then(function (res) {
        clearInterval(timer);
        idle();
        show(mapping, false);
        renderResult(res);
        if (onDone) onDone(res);
      }).catch(function (err) {
        clearInterval(timer);
        idle();
        setError(err.message);
        // The server checks the chosen date column too, and won't guess.
        if (/either way round/.test(err.message)) {
          current.proposal.date_order_certain = false;
          show($("#date-order-field"), true);
          $('input[name="date-order"]').focus();
        }
      });
    }

    function showResultNotice(tone, text) {
      clear(result);
      var p = el("p", "notice notice-" + tone);
      p.setAttribute("role", tone === "critical" ? "alert" : "status");
      p.appendChild(el("span", null, text));
      result.appendChild(p);
      show(result, true);
    }

    function renderResult(res) {
      var ds = res.data_source;
      var report = ds.report || {};
      clear(result);
      if (ds.status !== "ready") {
        showResultNotice("critical", ds.status_reason || "This file couldn't be fitted.");
        var again = el("button", "btn btn-quiet", "Choose a different file");
        again.type = "button";
        again.addEventListener("click", reset);
        result.appendChild(again);
        return;
      }
      var cats = res.runs.filter(function (r) { return r.category !== null; }).length;
      var tiles = el("div", "tiles");
      [["Products", nfInt.format(report.products)],
       ["Product-weeks", nfInt.format(report.product_weeks)],
       ["Weeks of history", nfInt.format(report.weeks)],
       ["Categories estimated", nfInt.format(cats)]].forEach(function (t) {
        var tile = el("div", "tile");
        tile.appendChild(el("div", "tile-label", t[0]));
        tile.appendChild(el("div", "tile-value", t[1]));
        tiles.appendChild(tile);
      });
      var head = el("p", "notice notice-info");
      head.setAttribute("role", "status");
      head.appendChild(el("span", null, "Fitted. " + ds.filename + " is now the basis for every page."));
      result.appendChild(head);
      result.appendChild(tiles);
      var notes = describeReport(report);
      if (notes.length) {
        var ul = el("ul", "caveat-list");
        notes.forEach(function (n) { ul.appendChild(el("li", null, n)); });
        result.appendChild(ul);
      }
      var go = el("a", "btn btn-primary", "See your results");
      go.href = "/dashboard";
      result.appendChild(go);
      show(result, true);
      go.focus();
    }

    input.addEventListener("change", function () { choose(input.files[0]); });
    ["dragenter", "dragover"].forEach(function (t) {
      zone.addEventListener(t, function (ev) { ev.preventDefault(); zone.setAttribute("data-drag", "true"); });
    });
    ["dragleave", "drop"].forEach(function (t) {
      zone.addEventListener(t, function () { zone.removeAttribute("data-drag"); });
    });
    zone.addEventListener("drop", function (ev) {
      ev.preventDefault();
      if (ev.dataTransfer && ev.dataTransfer.files.length) choose(ev.dataTransfer.files[0]);
    });
    button.addEventListener("click", upload);
    $("#upload-cancel").addEventListener("click", reset);
  }

  function describeReport(report) {
    var out = [];
    var dropped = report.dropped || {};
    var total = Object.keys(dropped).reduce(function (s, k) { return s + dropped[k]; }, 0);
    if (total) {
      out.push(nfInt.format(total) + " of " + nfInt.format(report.rows_read) + " rows were left out: " +
        Object.keys(dropped).map(function (k) { return nfInt.format(dropped[k]) + " with " + k; }).join("; ") + ".");
    }
    (report.excluded_categories || []).forEach(function (e) {
      out.push(e.category + " has no estimate of its own: " + friendlyReason(e.reason) + ".");
    });
    if (report.category_conflicts) {
      out.push(nfInt.format(report.category_conflicts) + " products appeared under more than one category; " +
        "each was counted under the one it was sold under most.");
    }
    if (report.fractional_units_rounded) {
      out.push(nfInt.format(report.fractional_units_rounded) + " product-weeks had fractional units and were rounded to whole units.");
    }
    return out;
  }

  function friendlyReason(reason) {
    var m = /insufficient data \((\d+) obs across (\d+) SKUs; need >=(\d+) obs and >=(\d+) SKUs\)/.exec(reason || "");
    if (m) {
      return nfInt.format(+m[1]) + " product-weeks across " + m[2] + " products, and a category needs at least " +
        nfInt.format(+m[3]) + " across " + m[4];
    }
    return reason;
  }

  /* ========================================================== onboarding == */
  function initOnboarding() {
    function toUpload() {
      show($("#step-name"), false);
      show($("#step-upload"), true);
      $("#step-marker-1").removeAttribute("aria-current");
      $("#step-marker-1").setAttribute("data-done", "true");
      $("#step-marker-2").setAttribute("aria-current", "step");
    }
    if (CONFIG.account) toUpload();

    $("#name-form").addEventListener("submit", function (ev) {
      ev.preventDefault();
      var name = $("#business-name").value.trim();
      var err = $("#name-error");
      if (!name) { err.textContent = "Enter your business's name."; show(err, true); return; }
      show(err, false);
      $("#name-submit").disabled = true;
      api("POST", "/api/account", { name: name })
        .then(function () { toUpload(); $("#file-input").focus(); })
        .catch(function (e) { err.textContent = e.message; show(err, true); })
        .then(function () { $("#name-submit").disabled = false; });
    });

    initUploader(function (res) {
      if (res.data_source.status === "ready") $("#step-marker-2").setAttribute("data-done", "true");
    });
  }

  /* ================================================================ data == */
  function initData() {
    if (CONFIG.account && !CONFIG.account.can_upload) {
      show($("#member-note"), true);
      show($("#uploader"), false);
    } else {
      initUploader(function () { loadHistory(); });
    }
    loadHistory();
  }

  function loadHistory() {
    var host = $("#history");
    api("GET", "/api/uploads").then(function (res) {
      host.removeAttribute("aria-busy");
      clear(host);
      if (!res.uploads.length) {
        host.appendChild(el("p", "hint table-empty", "Nothing uploaded yet."));
        return;
      }
      var table = el("table");
      table.appendChild(el("caption", null, "Newest first. The newest upload marked Ready is the one every page uses."));
      var thead = el("thead");
      var hr = el("tr");
      ["File", "Uploaded", "Status", "Rows used", "Products", "Notes"].forEach(function (h) {
        var th = el("th", null, h); th.setAttribute("scope", "col"); hr.appendChild(th);
      });
      thead.appendChild(hr);
      table.appendChild(thead);
      var tbody = el("tbody");
      var basisMarked = false;
      res.uploads.forEach(function (u) {
        var tr = el("tr");
        if (u.status === "ready" && !basisMarked) { tr.setAttribute("data-current", "true"); basisMarked = true; }
        tr.appendChild(el("td", "t-market", u.filename));
        tr.appendChild(el("td", null, when(u.uploaded_at)));
        var st = el("td");
        var pill = el("span", "status", { ready: "Ready", failed: "Failed", processing: "Processing", pending: "Pending" }[u.status] || u.status);
        pill.setAttribute("data-status", u.status);
        st.appendChild(pill);
        tr.appendChild(st);
        tr.appendChild(el("td", null, u.rows_used != null ? nfInt.format(u.rows_used) + " of " + nfInt.format(u.row_count) : "—"));
        tr.appendChild(el("td", null, u.products != null ? nfInt.format(u.products) : "—"));
        var note = u.status === "failed" ? (u.status_reason || "")
          : u.status === "ready" ? (u.date_range ? day(u.date_range[0]) + " to " + day(u.date_range[1]) : "") +
            ((u.excluded_categories || []).length ? " · " + plural(u.excluded_categories.length, "category", "categories") + " left out" : "")
          : "Still being fitted.";
        tr.appendChild(el("td", "t-reason", note));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      host.appendChild(table);
    }).catch(function (err) {
      host.removeAttribute("aria-busy");
      clear(host);
      host.appendChild(el("p", "field-error", err.message));
    });
  }

  /* ======================================================= number tags == */
  var FIELD_LABELS = {
    coefficient: "Price sensitivity", ci_low: "Likely range, low end", ci_high: "Likely range, high end",
    r_squared: "Explained variation (R²)", n_observations: "Product-weeks", category: "Category name"
  };
  var FORM_LABELS = {
    exact: "exactly as fitted", absolute: "without its minus sign",
    percent: "as a percentage", name: "part of the category's name"
  };

  var trace = { pop: null, button: null, runs: {}, source: null };

  function tracePop() {
    if (trace.pop) return trace.pop;
    var pop = el("div", "term-pop trace-pop");
    pop.id = "trace-pop";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-labelledby", "trace-pop-title");
    pop.hidden = true;
    document.body.appendChild(pop);
    document.addEventListener("click", function (ev) {
      if (!trace.button) return;
      if (ev.target.closest && (ev.target.closest(".num-tag") || ev.target.closest("#trace-pop"))) return;
      closeTrace();
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && trace.button) { var b = trace.button; closeTrace(); b.focus(); }
    });
    trace.pop = pop;
    return pop;
  }

  function closeTrace() {
    if (!trace.button) return;
    trace.button.setAttribute("aria-expanded", "false");
    trace.pop.hidden = true;
    trace.button = null;
    $$("[data-lit]").forEach(function (n) { n.removeAttribute("data-lit"); });
  }

  function openTrace(button, number) {
    var pop = tracePop();
    if (trace.button === button) { closeTrace(); return; }
    closeTrace();
    var src = number.sources[0];
    var run = trace.runs[src.run_id] || {};
    clear(pop);
    var h = el("h4", null, "Where " + number.text + " comes from");
    h.id = "trace-pop-title";
    pop.appendChild(h);
    pop.appendChild(el("p", null,
      FIELD_LABELS[src.field] + " of the " + (src.category ? src.category + " estimate" : "whole-range estimate") +
      ", " + FORM_LABELS[src.form] + "."));
    var dl = el("dl");
    [["Estimate", run.category || "Whole range", null],
     ["Sensitivity", fig(run.coefficient), "coefficient"],
     ["Likely range", fig(run.ci_low) + " to " + fig(run.ci_high), src.field === "ci_low" || src.field === "ci_high" ? src.field : null],
     ["R²", fig(run.r_squared), "r_squared"],
     ["Product-weeks", fig(run.n_observations), "n_observations"]].forEach(function (row) {
      dl.appendChild(el("dt", null, row[0]));
      var dd = el("dd", null, row[1]);
      if (row[2] && (row[2] === src.field)) dd.setAttribute("data-lit", "true");
      dl.appendChild(dd);
    });
    pop.appendChild(dl);
    pop.appendChild(el("p", "trace-note",
      "Fitted from " + (trace.source ? "“" + trace.source.filename + "”, uploaded " + when(trace.source.uploaded_at) : "your latest upload") +
      ". Run " + String(src.run_id).slice(0, 8) + "." +
      (number.sources.length > 1 ? " The same value also appears in " + (number.sources.length - 1) + " other place(s) in your estimates." : "")));
    var close = el("button", "term-pop-close");
    close.type = "button";
    close.setAttribute("aria-label", "Close");
    close.textContent = "×";
    close.addEventListener("click", function () { var b = trace.button; closeTrace(); if (b) b.focus(); });
    pop.appendChild(close);

    pop.hidden = false;
    button.setAttribute("aria-expanded", "true");
    trace.button = button;
    var r = button.getBoundingClientRect();
    pop.style.top = (r.bottom + window.scrollY + 8) + "px";
    pop.style.left = Math.min(Math.max(12, r.left + window.scrollX + r.width / 2 - pop.offsetWidth / 2),
      Math.max(12, document.documentElement.clientWidth - pop.offsetWidth - 12)) + "px";
    number.sources.forEach(function (s) {
      $$('[data-run-id="' + s.run_id + '"][data-field="' + s.field + '"]').forEach(function (cell) {
        cell.setAttribute("data-lit", "true");
      });
    });
    close.focus();
  }

  function renderItem(item) {
    var li = el("li");
    // One wrapper for the sentence, so the text and its tags flow as prose
    // in the list's second grid column instead of each becoming a cell.
    var body = el("span", "insight-body");
    li.appendChild(body);
    var text = item.text;
    var at = 0;
    (item.numbers || []).slice().sort(function (a, b) { return a.start - b.start; }).forEach(function (n) {
      var start = text.indexOf(n.text, Math.max(at, n.start - 2));
      if (start < 0) return;
      body.appendChild(document.createTextNode(text.slice(at, start)));
      var b = el("button", "num-tag", n.text);
      b.type = "button";
      b.setAttribute("aria-expanded", "false");
      b.setAttribute("aria-haspopup", "dialog");
      var src = n.sources[0];
      b.setAttribute("aria-label", n.text + " — " + FIELD_LABELS[src.field].toLowerCase() + ", " +
        (src.category || "whole range") + ". Show where it comes from.");
      b.addEventListener("click", function (ev) { ev.stopPropagation(); openTrace(b, n); });
      body.appendChild(b);
      at = start + n.text.length;
    });
    body.appendChild(document.createTextNode(text.slice(at)));
    return li;
  }

  function renderInsightList(host, insight, limit) {
    clear(host);
    host.removeAttribute("aria-busy");
    (insight.items || []).slice(0, limit || 5).forEach(function (item) { host.appendChild(renderItem(item)); });
  }

  function provenance(payload) {
    var ins = payload.insight;
    if (!ins) return "";
    if (ins.source === "llm") {
      var rewritten = (ins.attempts || []).length > 1
        ? " Its first draft quoted a number that isn't in your estimates, so it was rejected and rewritten." : "";
      var tier = ins.tier === "paid"
        ? " Sent on Gemini's paid tier: Google doesn't use it to improve its products."
        : " Sent on Gemini's free tier, where Google may use what it's sent — the table below — to improve its products.";
      return "Written by " + ins.model + " on " + when(ins.created_at) + ", from the estimates below; every number " +
        "in it was checked against them before it was shown." + rewritten + tier;
    }
    var why = "";
    var last = (ins.attempts || [])[(ins.attempts || []).length - 1];
    if (last && /GEMINI_API_KEY/.test(last.problem || "")) why = " No AI model is set up for this site yet.";
    else if (last && /unavailable/.test(last.problem || "")) why = " The AI model couldn't be reached.";
    else if (last) why = " The AI model's drafts quoted numbers that aren't in your estimates, so they weren't shown.";
    return "Written from a fixed template, not an AI model, on " + when(ins.created_at) + "." + why +
      " Every number is copied from the estimates below.";
  }

  function loadInsights() {
    return api("GET", "/api/account/insights").then(function (payload) {
      if (payload.insight) return payload;
      return api("POST", "/api/account/insights");
    }).then(function (payload) {
      trace.runs = {};
      payload.runs.forEach(function (r) { trace.runs[r.id] = r; });
      trace.source = payload.data_source;
      return payload;
    });
  }

  function renderSince(payload) {
    var since = payload.since_last_upload;
    var card = $("#since-card");
    if (!card || !since || !since.comparisons.length) return;
    var prev = since.previous_upload;
    $("#since-sub").textContent = "“" + prev.filename + "” (uploaded " + when(prev.uploaded_at) + ") against your latest upload. " +
      "An estimate held if the new figure landed inside the earlier likely range — the check a recommendation " +
      "written from that earlier estimate would have needed to pass.";
    var host = $("#since-table");
    clear(host);
    var table = el("table");
    var thead = el("thead");
    var hr = el("tr");
    ["Estimate", "Earlier upload", "Latest upload", "Result"].forEach(function (h) {
      var th = el("th", null, h); th.setAttribute("scope", "col"); hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = el("tbody");
    since.comparisons.forEach(function (c) {
      var tr = el("tr");
      tr.appendChild(el("td", null, c.category || "Whole range"));
      tr.appendChild(el("td", null, fig(c.previous.coefficient) + " (" + fig(c.previous.ci_low) + " to " + fig(c.previous.ci_high) + ")"));
      tr.appendChild(el("td", null, fig(c.current.coefficient) + " (" + fig(c.current.ci_low) + " to " + fig(c.current.ci_high) + ")"));
      var cell = el("td");
      var pill = el("span", "status", c.held ? "Held" : "Moved");
      pill.setAttribute("data-status", c.held ? "held" : "moved");
      cell.appendChild(pill);
      tr.appendChild(cell);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    host.appendChild(table);
    show(card, true);
  }

  /* ============================================================ overview == */
  function initOverview() {
    CONFIG.onReady = function (state) {
      var est = state.estimates;
      var o = est.overall;
      var ds = est.data_source || {};

      var advice = o.advice || {};
      var dir = !advice.certain ? "unclear" : advice.raising_price === "gains revenue" ? "up" : "down";
      var ticket = el("div", "ticket");
      ticket.id = "headline-ticket";
      ticket.setAttribute("data-direction", dir);
      ticket.appendChild(el("span", "ticket-label", "Price sensitivity"));
      var figure = el("span", "ticket-figure", fig(o.elasticity));
      ticket.appendChild(figure);
      ticket.appendChild(el("span", "ticket-range", "likely " + fig(o.ci_low) + " to " + fig(o.ci_high)));
      var meta = el("span", "ticket-meta");
      meta.appendChild(el("span", null, "R² " + fig(o.r_squared)));
      meta.appendChild(el("span", null, nfInt.format(o.n_observations) + " product-weeks"));
      if (o.n_skus) meta.appendChild(el("span", null, nfInt.format(o.n_skus) + " products"));
      ticket.appendChild(meta);
      var card = $(".card-verdict");
      var old = $("#headline-ticket");
      if (old) old.remove();
      card.insertBefore(ticket, $(".verdict", card));

      var facts = $("#data-facts");
      clear(facts);
      var dropped = Object.keys(ds.dropped || {}).reduce(function (s, k) { return s + ds.dropped[k]; }, 0);
      [["File", ds.filename],
       ["Uploaded", ds.uploaded_at ? when(ds.uploaded_at) : "—"],
       ["Period", ds.date_range ? day(ds.date_range[0]) + " – " + day(ds.date_range[1]) : "—"],
       ["Products", ds.products != null ? nfInt.format(ds.products) : "—"],
       ["Product-weeks", ds.product_weeks != null ? nfInt.format(ds.product_weeks) : "—"],
       ["Rows left out", nfInt.format(dropped)],
       ["Categories estimated", nfInt.format(est.by_category.length) +
         ((est.excluded_categories || []).length ? " · " + nfInt.format(est.excluded_categories.length) + " left out" : "")],
       ["Currency", ds.currency || "—"]].forEach(function (f) {
        var d = el("div");
        d.appendChild(el("dt", null, f[0]));
        d.appendChild(el("dd", null, f[1]));
        facts.appendChild(d);
      });

      var src = $("#method-source");
      if (src && ds.filename) {
        src.textContent = ", “" + ds.filename + "”" + (ds.date_range ? " (" + day(ds.date_range[0]) + " to " + day(ds.date_range[1]) + ")" : "");
      }

      var status = $("#overview-insights-status");
      status.textContent = "Writing recommendations from your estimates…";
      loadInsights().then(function (payload) {
        status.textContent = "";
        renderInsightList($("#overview-insights"), payload.insight, 3);
        renderSince(payload);
      }).catch(function (err) {
        status.textContent = "Recommendations aren't available right now: " + err.message;
        $("#overview-insights").removeAttribute("aria-busy");
      });
    };
  }

  /* ============================================================ products == */
  function initProducts() {
    CONFIG.onCategoryPick = function (name) {
      location.href = "/dashboard/simulator" + (name ? "?scope=category&category=" + encodeURIComponent(name) : "");
    };
    CONFIG.onReady = function (state) {
      var excluded = state.estimates.excluded_categories || [];
      var list = $("#excluded-list");
      clear(list);
      excluded.forEach(function (e) {
        var d = el("div");
        d.appendChild(el("dt", null, e.category));
        d.appendChild(el("dd", null, friendlyReason(e.reason).replace(/^./, function (c) { return c.toUpperCase(); }) + "."));
        list.appendChild(d);
      });
      show($("#excluded-card"), excluded.length > 0);
    };
  }

  /* ============================================================ insights == */
  function initInsights() {
    var list = $("#insight-list");
    var status = $("#insight-status");
    status.textContent = "Writing recommendations from your estimates…";

    function render(payload) {
      status.textContent = "";
      show($("#layout"), true);
      renderInsightList(list, payload.insight);
      $("#insight-provenance").textContent = provenance(payload);
      renderGrounding(payload);
      renderSince(payload);
      var regen = $("#regenerate");
      show(regen, !!payload.can_regenerate);
    }

    show($("#layout"), true);
    loadInsights().then(render).catch(function (err) {
      if (err.status === 404) { showEmpty(); return; }
      status.textContent = err.message;
      list.removeAttribute("aria-busy");
    });

    $("#regenerate").addEventListener("click", function () {
      var b = this;
      b.disabled = true;
      closeTrace();
      status.textContent = "Writing them again…";
      api("POST", "/api/account/insights?regenerate=true").then(function (payload) {
        trace.runs = {};
        payload.runs.forEach(function (r) { trace.runs[r.id] = r; });
        render(payload);
      }).catch(function (err) { status.textContent = err.message; })
        .then(function () { b.disabled = false; });
    });
  }

  function renderGrounding(payload) {
    var host = $("#grounding-table");
    clear(host);
    var table = el("table");
    table.appendChild(el("caption", null, "Each row is one stored estimate. Selecting a number in a recommendation lights up the figure it was copied from."));
    var thead = el("thead");
    var hr = el("tr");
    ["Estimate", "Sensitivity", "Likely range", "R²", "Product-weeks", "Run"].forEach(function (h) {
      var th = el("th", null, h); th.setAttribute("scope", "col"); hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = el("tbody");
    var runs = payload.runs.slice().sort(function (a, b) {
      return (a.category === null ? -1 : 0) - (b.category === null ? -1 : 0) || a.coefficient - b.coefficient;
    });
    runs.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(el("td", null, r.category || "Whole range"));
      function cell(text, field) {
        var td = el("td", null, text);
        td.setAttribute("data-run-id", r.id);
        td.setAttribute("data-field", field);
        return td;
      }
      tr.appendChild(cell(fig(r.coefficient), "coefficient"));
      var range = el("td");
      var lo = el("span", null, fig(r.ci_low)); lo.setAttribute("data-run-id", r.id); lo.setAttribute("data-field", "ci_low");
      var hi = el("span", null, fig(r.ci_high)); hi.setAttribute("data-run-id", r.id); hi.setAttribute("data-field", "ci_high");
      range.appendChild(lo); range.appendChild(document.createTextNode(" to ")); range.appendChild(hi);
      range.setAttribute("data-run-id", r.id);
      range.setAttribute("data-field", "range");
      tr.appendChild(range);
      tr.appendChild(cell(fig(r.r_squared), "r_squared"));
      tr.appendChild(cell(nfInt.format(r.n_observations), "n_observations"));
      tr.appendChild(el("td", null, String(r.id).slice(0, 8)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    host.appendChild(table);
  }

  /* ================================================================ boot == */
  initShell();
  var pages = {
    login: initLogin, onboarding: initOnboarding, data: initData, overview: initOverview,
    products: initProducts, insights: initInsights
  };
  if (pages[PAGE]) {
    if (document.readyState === "loading" && !CONFIG.lab) {
      document.addEventListener("DOMContentLoaded", pages[PAGE]);
    } else {
      pages[PAGE]();
    }
  }
})();
