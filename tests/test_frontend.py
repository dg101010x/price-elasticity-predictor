"""
Browser tests: the interactions, the responsive behaviour, and the
accessibility guarantees the redesign is supposed to hold.

Several of these are regression guards for defects found in the build this
replaced -- they are marked as such.
"""

import pytest

pytestmark = pytest.mark.browser


# ------------------------------------------------------------ page renders --

def test_page_loads_without_script_errors(page):
    assert page.errors == [], f"console/page errors: {page.errors}"
    assert page.text_content("#verdict-text").strip()


def test_the_page_leads_with_a_decision_not_a_coefficient(page):
    """The headline used to be 'log-log panel regression'; now it's the call."""
    verdict = page.text_content("#verdict-text").lower()
    assert any(w in verdict for w in ("revenue", "price")), verdict
    heading = page.text_content("h1")
    for jargon in ("log-log", "regression", "r²", "sku-week", "coefficient"):
        assert jargon not in heading.lower()


def test_all_three_charts_render_as_inline_svg(page):
    for host in ("#scale-chart", "#scenario-chart", "#compare-chart"):
        svg = page.query_selector(f"{host} svg")
        assert svg is not None, f"{host} rendered nothing"
        assert svg.get_attribute("role") == "img"
        assert (svg.get_attribute("aria-label") or "").strip(), f"{host} svg has no label"


def test_no_external_requests_are_attempted(browser, base_url):
    """Regression: the old build hard-depended on cdn.plot.ly and threw
    'Plotly is not defined' whenever that host was blocked."""
    context = browser.new_context()
    page = context.new_page()
    external = []
    page.on("request", lambda r: external.append(r.url)
            if not r.url.startswith((base_url, "data:")) else None)
    page.goto(base_url, wait_until="networkidle")
    page.wait_for_selector("#compare-chart svg")
    context.close()
    assert external == [], f"page reached off-origin: {external}"


# ------------------------------------------------------------- responsive --

@pytest.mark.parametrize("width,height", [(1440, 900), (1024, 800), (834, 1112), (390, 844), (320, 700)])
def test_no_horizontal_overflow(browser, base_url, width, height):
    """Regression: the old tooltip was a fixed 280px pseudo-element that
    pushed the mobile document to 480px wide inside a 390px viewport."""
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector("#compare-chart svg", timeout=20000)
    metrics = page.evaluate(
        "() => ({s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth})"
    )
    context.close()
    assert metrics["s"] <= metrics["c"] + 1, f"{width}px viewport scrolls to {metrics['s']}px"


def test_category_labels_are_not_clipped_on_a_phone(mobile_page):
    """Narrow screens move each bar's label above its own bar rather than
    truncating it into a left gutter."""
    texts = mobile_page.eval_on_selector_all(
        "#compare-chart text", "els => els.map(e => e.textContent)"
    )
    assert "Jewelry & Accessories" in texts
    assert "Christmas & Seasonal" in texts


def test_controls_meet_the_touch_target_minimum(mobile_page):
    selectors = ["#price-input", "#change-slider", ".segmented button",
                 ".quick-changes button", "#cost-block > summary"]
    for sel in selectors:
        box = mobile_page.eval_on_selector(
            sel, "e => { const r = e.getBoundingClientRect(); return {w: r.width, h: r.height}; }"
        )
        assert box["h"] >= 30, f"{sel} is only {box['h']}px tall"
        assert box["w"] >= 44, f"{sel} is only {box['w']}px wide"


# ----------------------------------------------------- scenario arithmetic --

def test_browser_math_matches_the_python_module(page):
    """The JS mirror of src/elasticity_math.py must produce identical numbers.

    Same expectations as tests/test_elasticity_math.py, read out of the
    rendered UI rather than called directly.
    """
    page.fill("#price-input", "10.00")
    page.dispatch_event("#price-input", "blur")
    page.click('.quick-changes button[data-change="10"]')

    tiles = page.eval_on_selector_all(
        ".tile", "els => Object.fromEntries(els.map(e => ["
                 "e.querySelector('.tile-label').textContent,"
                 "e.querySelector('.tile-value').textContent]))"
    )
    assert tiles["New price"].endswith("11.00")
    assert tiles["Units sold"] == "−16.6%"       # python: -16.58
    assert tiles["Revenue"] == "−8.2%"           # python: -8.24


def test_a_price_cut_flips_the_revenue_tile(page):
    page.click('.quick-changes button[data-change="-10"]')
    value = page.text_content(".tile[data-tone] .tile-value")
    revenue = page.eval_on_selector_all(
        ".tile", "els => els.filter(e => e.querySelector('.tile-label').textContent === 'Revenue')"
                 ".map(e => ({v: e.querySelector('.tile-value').textContent, tone: e.dataset.tone}))[0]"
    )
    assert revenue["v"].startswith("+"), revenue
    assert revenue["tone"] == "good"
    assert value is not None


def test_slider_and_quick_buttons_stay_in_sync(page):
    page.click('.quick-changes button[data-change="20"]')
    assert page.input_value("#change-slider") == "20"
    assert page.text_content("#change-readout") == "+20%"
    assert page.get_attribute('.quick-changes button[data-change="20"]', "aria-pressed") == "true"
    assert page.get_attribute('.quick-changes button[data-change="10"]', "aria-pressed") == "false"


def test_unit_cost_adds_a_profit_tile_and_can_disagree_with_revenue(page):
    page.fill("#price-input", "10.00")
    page.dispatch_event("#price-input", "blur")
    page.click('.quick-changes button[data-change="-20"]')
    page.click("#cost-block > summary")
    page.fill("#cost-input", "6")

    labels = page.eval_on_selector_all(
        ".tile .tile-label", "els => els.map(e => e.textContent)")
    assert "Gross profit" in labels

    values = page.eval_on_selector_all(
        ".tile", "els => Object.fromEntries(els.map(e => ["
                 "e.querySelector('.tile-label').textContent,"
                 "e.querySelector('.tile-value').textContent]))")
    assert values["Revenue"].startswith("+")
    assert values["Gross profit"].startswith("−")
    assert not page.is_hidden("#profit-note")


def test_cost_above_price_is_rejected_next_to_the_field(page):
    page.fill("#price-input", "10.00")
    page.dispatch_event("#price-input", "blur")
    page.click("#cost-block > summary")
    page.fill("#cost-input", "12")
    assert page.is_visible("#cost-error")
    assert "below the current price" in page.text_content("#cost-error")
    labels = page.eval_on_selector_all(".tile .tile-label", "els => els.map(e => e.textContent)")
    assert "Gross profit" not in labels


def test_a_discount_that_barely_moves_profit_is_called_out(page):
    """A 20% cut on a 2.95 t-light holder grows revenue ~22% and profit ~1%.
    Both go up, so a sign check alone would stay silent -- but the headline
    would badly flatter the decision."""
    page.click('[data-scope="product"]')
    page.fill("#product-input", "white hanging heart t-light holder")
    page.wait_for_selector("#product-listbox li[role=option]")
    page.press("#product-input", "ArrowDown")
    page.press("#product-input", "Enter")
    page.click('.quick-changes button[data-change="-20"]')
    page.click("#cost-block > summary")
    page.fill("#cost-input", "1.20")

    values = page.eval_on_selector_all(
        ".tile", "els => Object.fromEntries(els.map(e => ["
                 "e.querySelector('.tile-label').textContent,"
                 "e.querySelector('.tile-value').textContent]))")
    assert values["Revenue"].startswith("+")
    assert values["Gross profit"].startswith("+")

    assert not page.is_hidden("#profit-note")
    text = page.text_content("#profit-note-text")
    assert "moves much further than profit" in text
    assert "notice-warn" in page.get_attribute("#profit-note", "class")


def test_revenue_not_profit_is_stated_when_no_cost_is_given(page):
    assert not page.is_hidden("#profit-note")
    assert "revenue, not profit" in page.text_content("#profit-note-text")


# ------------------------------------------------------------ scope + pick --

def test_scope_switch_shows_only_the_relevant_control(page):
    """Regression: .field { display: flex } used to beat the UA [hidden] rule,
    so every panel stayed on screen at once."""
    assert page.is_hidden("#field-category") and page.is_hidden("#field-product")

    page.click('[data-scope="category"]')
    assert page.is_visible("#field-category") and page.is_hidden("#field-product")

    page.click('[data-scope="product"]')
    assert page.is_hidden("#field-category") and page.is_visible("#field-product")

    page.click('[data-scope="all"]')
    assert page.is_hidden("#field-category") and page.is_hidden("#field-product")


def test_default_product_is_a_real_one_from_a_reported_category(page):
    """Regression: the old build defaulted to the alphabetically-first SKU,
    an 'Inflatable Political Globe' from the excluded catch-all bucket."""
    page.click('[data-scope="product"]')
    name = page.input_value("#product-input")
    assert name and "Inflatable Political Globe" not in name
    assert "no separate estimate" not in page.text_content("#verdict-basis").lower()


def test_product_search_filters_and_selects_by_keyboard(page):
    """Regression: 4,896 products used to sit in a plain <select> capped at 500."""
    page.click('[data-scope="product"]')
    page.click("#product-input")
    page.fill("#product-input", "cakestand")
    page.wait_for_selector("#product-listbox li[role=option]")

    options = page.eval_on_selector_all(
        "#product-listbox li[role=option] .combo-name", "els => els.map(e => e.textContent)")
    assert options and all("cakestand" in o.lower() for o in options)

    page.press("#product-input", "ArrowDown")
    assert page.get_attribute("#product-input", "aria-activedescendant") == "product-opt-0"
    page.press("#product-input", "Enter")

    assert "cakestand" in page.input_value("#product-input").lower()
    assert page.is_hidden("#product-listbox")


def test_selecting_a_product_autofills_its_real_price(page):
    page.click('[data-scope="product"]')
    page.fill("#product-input", "regency cakestand 3 tier")
    page.wait_for_selector("#product-listbox li[role=option]")
    page.press("#product-input", "ArrowDown")
    page.press("#product-input", "Enter")
    assert float(page.input_value("#price-input")) == pytest.approx(12.75, abs=0.01)


def test_escape_closes_the_product_list(page):
    page.click('[data-scope="product"]')
    page.click("#product-input")
    page.fill("#product-input", "bag")
    page.wait_for_selector("#product-listbox li[role=option]")
    page.press("#product-input", "Escape")
    assert page.is_hidden("#product-listbox")


def test_unmatched_search_says_so(page):
    page.click('[data-scope="product"]')
    page.click("#product-input")
    page.fill("#product-input", "zzzzzz-not-a-product")
    page.wait_for_selector("#product-listbox .combo-empty")
    assert "No product matches" in page.text_content("#product-listbox .combo-empty")


def test_choosing_a_category_updates_the_verdict_scope(page):
    page.click('[data-scope="category"]')
    page.select_option("#category-select", "Jewelry & Accessories")
    assert page.text_content("#verdict-scope") == "Jewelry & Accessories"


def test_clicking_a_bar_in_the_comparison_chart_selects_that_category(page):
    bars = page.query_selector_all("#compare-chart rect.chart-hit")
    assert bars, "comparison chart has no hit targets"
    target = next(b for b in bars if "Toys & Games" in (b.get_attribute("aria-label") or ""))
    target.click()
    assert page.text_content("#verdict-scope") == "Toys & Games"


# --------------------------------------------------------------- url state --

def test_selection_is_shareable_through_the_url(page, base_url):
    page.click('[data-scope="category"]')
    page.select_option("#category-select", "Bath & Body")
    page.click('.quick-changes button[data-change="-20"]')

    url = page.url
    assert "scope=category" in url and "Bath" in url and "change=-20" in url

    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#layout:not([hidden])")
    assert page.text_content("#verdict-scope") == "Bath & Body"
    assert page.input_value("#change-slider") == "-20"


# ------------------------------------------------------------ table views --

@pytest.mark.parametrize("button,table", [
    ('[data-table-toggle="scenario-table"]', "#scenario-table"),
    ('[data-table-toggle="compare-table"]', "#compare-table"),
])
def test_every_chart_has_a_table_twin(page, button, table):
    """Values must never be gated behind a hover."""
    assert page.is_hidden(table)
    assert page.get_attribute(button, "aria-expanded") == "false"
    page.click(button)
    assert page.is_visible(table)
    assert page.get_attribute(button, "aria-expanded") == "true"
    assert page.query_selector_all(f"{table} tbody tr")
    page.click(button)
    assert page.is_hidden(table)


def test_comparison_table_carries_every_group_and_its_range(page):
    page.click('[data-table-toggle="compare-table"]')
    rows = page.eval_on_selector_all(
        "#compare-table tbody tr td:first-child", "els => els.map(e => e.textContent)")
    assert "Whole range" in rows
    assert "Jewelry & Accessories" in rows
    assert len(rows) == 12          # 11 reported categories + the pooled figure
    headers = page.eval_on_selector_all("#compare-table thead th", "els => els.map(e => e.textContent)")
    assert "Likely range" in headers


# --------------------------------------------------------- accessibility --

def test_landmarks_and_a_skip_link_exist(page):
    assert page.query_selector("header.masthead")
    assert page.query_selector("main#main")
    assert page.query_selector("a.skip-link[href='#main']")


def test_skip_link_becomes_visible_on_focus(page):
    before = page.eval_on_selector(".skip-link", "e => e.getBoundingClientRect().top")
    page.focus(".skip-link")
    page.wait_for_timeout(250)          # the link slides in over 140ms
    after = page.eval_on_selector(".skip-link", "e => e.getBoundingClientRect().top")
    assert before < 0 <= after


def test_definitions_open_on_click_and_close_on_escape(page):
    """Regression: definitions used to be a :hover-only ::after pseudo-element,
    unreachable by keyboard, screen reader, or any touch device."""
    term = page.query_selector(".term")
    assert term.get_attribute("aria-expanded") == "false"
    term.click()
    assert term.get_attribute("aria-expanded") == "true"
    assert page.is_visible("#term-pop")
    assert page.text_content("#term-pop-body").strip()
    page.keyboard.press("Escape")
    assert page.is_hidden("#term-pop")
    assert term.get_attribute("aria-expanded") == "false"


def test_definitions_are_reachable_by_keyboard_alone(page):
    page.focus(".term")
    page.keyboard.press("Enter")
    assert page.is_visible("#term-pop")


def test_every_definition_also_lives_in_the_glossary(page):
    """Touch users get the same content without any popover at all."""
    glossary = page.eval_on_selector_all("#glossary-list dt", "els => els.map(e => e.textContent)")
    assert len(glossary) >= 6
    pairs = page.eval_on_selector_all(
        "#glossary-list > div", "els => els.map(e => [!!e.querySelector('dt'), !!e.querySelector('dd')])")
    assert all(dt and dd for dt, dd in pairs), "glossary terms lost their definitions"


def test_combobox_exposes_the_full_aria_contract(page):
    page.click('[data-scope="product"]')
    attrs = page.eval_on_selector("#product-input", """e => ({
        role: e.getAttribute('role'),
        expanded: e.getAttribute('aria-expanded'),
        controls: e.getAttribute('aria-controls'),
        autocomplete: e.getAttribute('aria-autocomplete'),
        labelled: !!document.querySelector('label[for=product-input]')
    })""")
    assert attrs["role"] == "combobox"
    assert attrs["controls"] == "product-listbox"
    assert attrs["autocomplete"] == "list"
    assert attrs["labelled"]
    assert page.get_attribute("#product-listbox", "role") == "listbox"


def test_scope_control_is_a_real_radiogroup(page):
    assert page.get_attribute(".segmented", "role") == "radiogroup"
    checked = page.eval_on_selector_all(
        ".segmented button", "els => els.map(e => e.getAttribute('aria-checked'))")
    assert checked.count("true") == 1


def test_every_form_control_has_a_label(page):
    page.click('[data-scope="category"]')
    unlabelled = page.evaluate("""() => {
        const fields = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')];
        return fields.filter(f => {
            if (f.closest('[hidden]')) return false;
            if (f.getAttribute('aria-label')) return false;
            if (f.getAttribute('aria-labelledby')) return false;
            return !(f.id && document.querySelector(`label[for="${f.id}"]`));
        }).map(f => f.id || f.outerHTML.slice(0, 60));
    }""")
    assert unlabelled == [], f"unlabelled controls: {unlabelled}"


def test_the_result_region_announces_itself(page):
    assert page.get_attribute("#verdict-heading", "aria-live") == "polite"
    assert page.get_attribute("#live-region", "role") == "status"


def test_chart_marks_are_focusable_and_described(page):
    hits = page.query_selector_all("#compare-chart rect.chart-hit")
    assert len(hits) == 12
    for hit in hits[:3]:
        assert hit.get_attribute("tabindex") == "0"
        label = hit.get_attribute("aria-label")
        assert "price sensitivity" in label and "likely range" in label


def test_scenario_chart_is_keyboard_explorable(page):
    page.click('.quick-changes button[data-change="10"]')
    # re-query: every change redraws the chart and detaches the old node
    hit = page.query_selector("#scenario-chart rect.chart-hit")
    assert hit.get_attribute("tabindex") == "0"
    hit.focus()
    page.keyboard.press("ArrowRight")
    assert page.input_value("#change-slider") == "11"
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    assert page.input_value("#change-slider") == "9"


def test_status_colour_is_never_the_only_signal(page):
    """Every toned tile carries a readable label and value, not just a hue."""
    tiles = page.eval_on_selector_all(
        ".tile[data-tone]", "els => els.map(e => ({"
        "tone: e.dataset.tone,"
        "label: e.querySelector('.tile-label').textContent.trim(),"
        "value: e.querySelector('.tile-value').textContent.trim()}))")
    assert tiles
    for t in tiles:
        assert t["label"] and t["value"]


def test_heading_order_never_skips_a_level(page):
    levels = page.eval_on_selector_all(
        "h1, h2, h3, h4",
        "els => els.filter(e => !e.closest('[hidden]')).map(e => Number(e.tagName[1]))")
    assert levels[0] <= 2
    for prev, nxt in zip(levels, levels[1:]):
        assert nxt - prev <= 1, f"heading jumped from h{prev} to h{nxt}"


# ---------------------------------------------------------------- theming --

def test_theme_toggle_switches_and_persists(page):
    page.click('[data-theme-set="dark"]')
    assert page.get_attribute("html", "data-theme") == "dark"
    assert page.get_attribute('[data-theme-set="dark"]', "aria-pressed") == "true"

    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#layout:not([hidden])")
    assert page.get_attribute("html", "data-theme") == "dark"

    page.click('[data-theme-set="light"]')
    assert page.get_attribute("html", "data-theme") == "light"
    page.click('[data-theme-set="system"]')
    assert page.get_attribute("html", "data-theme") is None


def test_charts_repaint_for_the_active_theme(page):
    def bar_fill():
        return page.eval_on_selector("#compare-chart path", "e => e.getAttribute('fill')")

    page.click('[data-theme-set="light"]')
    light = bar_fill()
    page.click('[data-theme-set="dark"]')
    page.wait_for_timeout(120)
    assert bar_fill() != light, "dark mode reused the light-mode mark colour"


def test_dark_mode_is_honoured_from_the_system_setting(browser, base_url):
    context = browser.new_context(color_scheme="dark", viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector("#compare-chart svg")
    bg = page.eval_on_selector("body", "e => getComputedStyle(e).backgroundColor")
    context.close()
    r, g, b = [int(x) for x in bg.replace("rgb(", "").replace(")", "").split(",")[:3]]
    assert r + g + b < 200, f"body stayed light under prefers-color-scheme: dark ({bg})"
