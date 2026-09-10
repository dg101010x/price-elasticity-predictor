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
    assert tiles["Takings"] == "−8.2%"           # python: -8.24


def test_a_price_cut_flips_the_revenue_tile(page):
    page.click('.quick-changes button[data-change="-10"]')
    value = page.text_content(".tile[data-tone] .tile-value")
    revenue = page.eval_on_selector_all(
        ".tile", "els => els.filter(e => e.querySelector('.tile-label').textContent === 'Takings')"
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
    assert "Money you keep" in labels

    values = page.eval_on_selector_all(
        ".tile", "els => Object.fromEntries(els.map(e => ["
                 "e.querySelector('.tile-label').textContent,"
                 "e.querySelector('.tile-value').textContent]))")
    assert values["Takings"].startswith("+")
    assert values["Money you keep"].startswith("−")
    assert not page.is_hidden("#profit-note")


def test_cost_above_price_is_rejected_next_to_the_field(page):
    page.fill("#price-input", "10.00")
    page.dispatch_event("#price-input", "blur")
    page.click("#cost-block > summary")
    page.fill("#cost-input", "12")
    assert page.is_visible("#cost-error")
    assert "below the current price" in page.text_content("#cost-error")
    labels = page.eval_on_selector_all(".tile .tile-label", "els => els.map(e => e.textContent)")
    assert "Money you keep" not in labels


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
    assert values["Takings"].startswith("+")
    assert values["Money you keep"].startswith("+")

    assert not page.is_hidden("#profit-note")
    text = page.text_content("#profit-note-text")
    assert "move much further than your profit" in text
    assert "notice-warn" in page.get_attribute("#profit-note", "class")


def test_revenue_not_profit_is_stated_when_no_cost_is_given(page):
    assert not page.is_hidden("#profit-note")
    assert "takings, not profit" in page.text_content("#profit-note-text")


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
    ('[data-table-toggle="bench-table"]', "#bench-table"),
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


def test_every_radiogroup_has_exactly_one_selection(page):
    """The page carries several: scope, catalogue, and the comparison span."""
    assert page.get_attribute(".segmented", "role") == "radiogroup"

    groups = page.eval_on_selector_all(
        "[role='radiogroup']",
        "els => els.map(e => ({"
        "  label: e.getAttribute('aria-label') || e.id,"
        "  checked: [...e.querySelectorAll('[role=radio]')]"
        "    .map(r => r.getAttribute('aria-checked'))"
        "}))"
    )
    assert len(groups) >= 3, groups
    for group in groups:
        assert group["checked"].count("true") == 1, group


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


# ------------------------------------------------------ the money answer --
# Percentages are the honest unit; money is the one a price-setter thinks in.
# The till restates the same scenario over a hundred-unit week.

def test_the_till_states_the_answer_in_money(page):
    page.fill("#price-input", "10.00")
    page.dispatch_event("#price-input", "blur")
    page.click('.quick-changes button[data-change="10"]')

    rows = page.eval_on_selector_all(
        "#till-roll tbody tr",
        "els => Object.fromEntries(els.map(e => ["
        "e.querySelector('th').textContent,"
        "[...e.querySelectorAll('td')].map(t => t.textContent)]))"
    )
    # 100 units at £10 = £1,000 now; at -16.6% units and +10% price = £917.62
    assert rows["Takings"][0] == "£1,000.00"
    assert rows["Takings"][1] == "£917.62"
    assert rows["Takings"][2] == "−8.2%"


def test_till_units_agree_with_their_own_percentage(page):
    """Regression: an earlier anchor of £100 gave '10 → 8' beside '−16.6%'.

    Rounding a ten-unit base made the arithmetic visibly disagree with itself.
    Anchoring on a hundred units keeps the row whole and self-consistent.
    """
    page.fill("#price-input", "10.00")
    page.dispatch_event("#price-input", "blur")
    page.click('.quick-changes button[data-change="10"]')

    units = page.eval_on_selector_all(
        "#till-roll tbody tr",
        "els => els.filter(e => e.querySelector('th').textContent === 'Units sold')"
        ".map(e => [...e.querySelectorAll('td')].map(t => t.textContent))[0]"
    )
    now, after, change = int(units[0]), int(units[1]), units[2]
    assert now == 100
    assert change == "−16.6%"
    assert after == round(now * (1 - 0.166)), (units, "units row contradicts its own percentage")


def test_till_shows_money_kept_only_once_a_cost_is_given(page):
    labels = page.eval_on_selector_all(
        "#till-roll tbody tr th", "els => els.map(e => e.textContent)")
    assert "Money you keep" not in labels

    page.click("#cost-block summary")
    page.fill("#cost-input", "6.00")
    page.dispatch_event("#cost-input", "blur")

    labels = page.eval_on_selector_all(
        "#till-roll tbody tr th", "els => els.map(e => e.textContent)")
    assert "Money you keep" in labels


def test_till_can_show_takings_falling_while_money_kept_rises(page):
    """The whole reason the profit row exists, in money rather than percent."""
    page.fill("#price-input", "10.00")
    page.dispatch_event("#price-input", "blur")
    page.click("#cost-block summary")
    page.fill("#cost-input", "6.00")
    page.dispatch_event("#cost-input", "blur")
    page.click('.quick-changes button[data-change="10"]')

    tones = page.eval_on_selector_all(
        "#till-roll tbody tr",
        "els => Object.fromEntries(els.map(e => ["
        "e.querySelector('th').textContent,"
        "e.querySelector('.till-delta').dataset.tone || '']))"
    )
    assert tones["Takings"] == "critical"
    assert tones["Money you keep"] == "good"


# ---------------------------------------------------------- other trades --

def test_other_trades_ladder_renders_as_inline_svg(page):
    svg = page.query_selector("#bench-chart svg")
    assert svg is not None
    assert svg.get_attribute("role") == "img"
    assert "Ketchup" in (svg.get_attribute("aria-label") or "")


def test_every_benchmark_dot_is_focusable_and_described(page):
    dots = page.eval_on_selector_all(
        "#bench-chart circle[tabindex='0']", "els => els.map(e => e.getAttribute('aria-label'))")
    assert len(dots) == 10, "ten usable benchmarks should each be reachable"
    for label in dots:
        assert label and "break-even" in label


def test_the_two_unusable_benchmarks_are_named_on_the_page(page):
    text = page.text_content("#bench-flagged")
    assert "Household natural gas" in text
    assert "Theatre tickets (Broadway)" in text
    tags = page.eval_on_selector_all(
        "#bench-flagged .bench-flag-tag", "els => els.map(e => e.textContent)")
    assert sorted(tags) == ["can't tell", "wrong sign"]


def test_flagged_markets_are_kept_out_of_the_ladder(page):
    """They would read as 'theatre tickets are barely price-sensitive', which
    is exactly the wrong lesson to draw from a confounded slope."""
    label = page.get_attribute("#bench-chart svg", "aria-label")
    assert "Theatre tickets" not in label
    assert "natural gas" not in label


def test_benchmark_table_carries_the_source_for_every_market(page):
    page.click('[data-table-toggle="bench-table"]')
    rows = page.eval_on_selector_all(
        "#bench-table tbody tr", "els => els.map(e => e.children.length)")
    assert len(rows) == 12
    sources = page.eval_on_selector_all(
        "#bench-table tbody tr td:last-child", "els => els.map(e => e.textContent.trim())")
    assert all(sources), "every market must name where it came from"
    assert any("Playbill" in s for s in sources)


def test_the_method_section_accounts_for_the_reference_markets(page):
    """Provenance is read off the data, so the copy can't drift from it."""
    text = page.text_content("#method-benchmarks")
    assert "5,960" in text and "26" in text
    assert "12" in text, "the roster size should come from the payload"
    assert "2 more" in text and "labelled" in text


# ---------------------------------------------- two catalogues, and the blend --

def test_the_catalogue_picker_offers_both_shops(page):
    names = page.eval_on_selector_all(
        ".market-option .market-name", "els => els.map(e => e.textContent)")
    assert len(names) == 2
    assert any("Walmart" in n for n in names)
    checked = page.eval_on_selector_all(
        ".market-option", "els => els.map(e => e.getAttribute('aria-checked'))")
    assert checked.count("true") == 1


def test_switching_catalogue_changes_the_money_and_the_departments(page):
    assert page.text_content("#price-symbol") == "£"
    page.click('.market-option[data-market="walmart"]')
    page.wait_for_function(
        "() => document.querySelector('#price-symbol').textContent === '$'", timeout=8000)

    options = page.eval_on_selector_all(
        "#category-select option", "els => els.map(e => e.textContent)")
    assert set(options) == {"Foods", "Hobbies", "Household"}
    assert "market=walmart" in page.url


def test_switching_catalogue_flips_the_verdict(page):
    """Giftware is elastic, grocery is not. The headline should follow."""
    assert "Cutting the price" in page.text_content("#verdict-text")
    page.click('.market-option[data-market="walmart"]')
    page.wait_for_function(
        "() => document.querySelector('#verdict-text').textContent.includes('Raising')",
        timeout=8000)


def test_the_comparison_can_stack_both_catalogues(page):
    one = page.eval_on_selector_all(
        "#compare-chart .chart-hit", "els => els.length")
    page.click('#compare-span [data-span="both"]')
    page.wait_for_timeout(400)
    both = page.eval_on_selector_all("#compare-chart .chart-hit", "els => els.length")
    assert both > one, (one, both)

    labels = page.eval_on_selector_all(
        "#compare-chart text", "els => els.map(e => e.textContent)")
    assert "Foods" in labels, "Walmart groups should appear once stacked"
    assert "Kitchen & Dining" in labels, "UK groups should stay"
    assert "Both, pooled" in labels


def test_the_stacked_view_says_it_is_a_union_and_not_a_join(page):
    page.click('#compare-span [data-span="both"]')
    page.wait_for_timeout(400)
    text = page.text_content("#blend-note")
    assert "stacked, not joined" in text
    assert "share no product, no shop and no currency" in text
    assert "midpoint" in text, "the heterogeneity caveat must sit with the pooled figure"


def test_the_pooled_row_has_no_observation_count_of_its_own(page):
    page.click('#compare-span [data-span="both"]')
    page.click('[data-table-toggle="compare-table"]')
    row = page.eval_on_selector_all(
        "#compare-table tbody tr",
        "els => els.filter(e => e.children[0].textContent === 'Both, pooled')"
        ".map(e => e.children[3].textContent)[0]"
    )
    assert row == "n/a", "the pooled row summarises the others, so it has no count"
