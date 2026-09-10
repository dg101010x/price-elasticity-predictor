# Price Sensitivity Lab

A pricing tool built on public retail transaction data. You pick something you
sell, propose a price change, and it tells you what that change did to units and
revenue the last time prices moved like that. Give it a unit cost too and it will
tell you whether the money you actually keep moves the same way.

Underneath it is a within-SKU log-log panel regression. On the surface it is a
question a price-setter can answer without knowing what any of those words mean.

```
uvicorn src.api:app --reload      # http://localhost:8000
```

## What's here

```
src/
  api.py                       FastAPI app: serves the page and the JSON API
  elasticity_math.py           the revenue/profit arithmetic (mirrored in app.js)
  panel_regression.py          the estimator, shared by both model builders
  dashboard.py                 inlines src/web/* into one self-contained response
  web/
    index.html                 markup
    app.css                    design system + both themes
    app.js                     state, interactions, and the four SVG charts
    fonts/                     self-hosted Archivo + IBM Plex Mono (OFL)
  build_elasticity_model.py    fits the UK catalogue's departments
  build_walmart_catalogue.py   fits the Walmart catalogue
  build_reference_benchmarks.py fits the twelve outside markets
  build_blended_catalogue.py   stacks the two catalogues and pools them
  data_loader.py               downloads the originally-scoped datasets
  walmart_data.py              downloads and verifies the M5 release
  reference_data.py            downloads the twelve reference markets
  screen_archives.py           the search that produced that roster
  build_manifest.py            profiles data/csv/*.csv into the manifest
tests/                         API contract, estimator, shared math, browser + a11y
data/
  processed/                   elasticity_results.json, products.json,
                               reference_benchmarks.json
  manifests/                   data_manifest.csv, validation_report.txt,
                               archive_screen.json (tracked)
```

The page ships as a single response with **no external requests at all**: no CDN,
no webfont host, no analytics. That is enforced by a test, not a convention.
`tests/test_api.py::test_dashboard_is_self_contained` fails the build if a
remote subresource appears.

## API

Record-level endpoints, unchanged since 1.0:

| endpoint | what it gives you |
|---|---|
| `GET /elasticity` | one estimate, by `category` or `product_id`, with a `price` echo |
| `GET /categories` | reported and excluded category names |
| `GET /products` | product directory; filter with `category`, search with `q` |
| `GET /methodology` | how the estimates were fitted, and the caveats |
| `GET /health` | liveness, plus whether stub data is in play |

Decision-level endpoints, added for the current UI:

| endpoint | what it gives you |
|---|---|
| `GET /estimates` | every estimate in one payload, each with `advice` + `evidence` |
| `GET /scenario` | units, revenue and gross profit at a given `pct_price_change` |
| `GET /catalog` | the whole product directory in the shape the search box wants |
| `GET /benchmarks` | twelve outside markets on the same scale, with provenance |
| `GET /markets` | the catalogues you can price against, and how big each is |
| `GET /blended` | both catalogues stacked into one table, and pooled |

Every endpoint above takes `?market=uk` or `?market=walmart`. Omitting it
gives you `uk`, so nothing that already called this API sees a change.

`/estimates` exists because the dashboard used to issue one `/elasticity` request
per category on every interaction. That was eleven identical round-trips per
keystroke, for data that never changes.

Interactive docs at `/docs`.

## The one number that matters

Revenue is flat in price at exactly **elasticity = -1**. More negative than that
and a price rise loses more in units than it gains per unit, so discounting grows
revenue. Less negative and it's the other way round. Everything the interface
says is built on which side of that line an estimate falls, and whether its
confidence interval is narrow enough to be sure.

`src/elasticity_math.py` is the canonical implementation. `src/web/app.js`
carries a JavaScript mirror so the price slider responds without a round-trip;
`tests/` pins both against the same expectations so they can't drift.

The estimator itself lives in `src/panel_regression.py`, called by both model
builders, so a category from the gift catalogue and a benchmark from Broadway
are the same measurement and belong on the same axis.

## Data

Datasets live in `data/csv/` (gitignored: regenerate locally, don't commit) and
are documented in `data/manifests/data_manifest.csv`.

```
python -m src.data_loader                 # the originally-scoped datasets
python -m src.walmart_data                # the M5 Walmart release
python -m src.reference_data              # the twelve reference markets
python -m src.build_manifest              # profiles them, writes the manifest
python -m src.build_elasticity_model      # fits the UK catalogue
python -m src.build_walmart_catalogue     # fits the Walmart catalogue
python -m src.build_reference_benchmarks  # fits the outside markets
python -m src.build_blended_catalogue     # stacks the two and pools them
```

Twenty datasets are profiled in `data/manifests/`, **27,126,883 CSV rows**;
9 more are documented and blocked, for 29 documented in total. All
twenty fetch with no account, though not all of them from any one network:
this project's own CI reaches GitHub and PyPI but not ers.usda.gov, UCI or
Zenodo, so those keep the figures from the run that last saw them.

That row count understates the largest one. The M5 sales file ships wide, one
row per store-item and one column per day, so its 30,490 rows carry
**59,181,090 daily unit-sales records**.

### What's actually downloaded vs. what needs manual setup

Of the ten datasets originally scoped, five are freely downloadable (no
account, no registration) and are fetched for real by `src/data_loader.py`:

| file | source | why it's useful |
|---|---|---|
| `scanner_data.csv` | [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | 1.07M transaction rows, 5,305 SKUs, Dec 2009-Dec 2011. Stands in for the gated Kaggle `marian447/retail-scanner-data` notebook dataset. That one is very likely derived from this exact UCI source (5,242 vs. 5,305 SKUs). |
| `monash_dominicks.csv` | [Monash "Dominick Dataset" on Zenodo](https://zenodo.org/records/4654802) | 19.1M rows, 115,704 weekly per-SKU profit series, reformatted from the Kilts Center Dominick's Finer Foods data. Anonymized (no store/UPC/category), so it's useful for time-series modeling but not for category breakdowns. |
| `usda_elasticities.csv` | [USDA ERS demand elasticities](https://www.ers.usda.gov/data-products/commodity-and-food-elasticities/documentation) | 14,173 literature-reported own-/cross-price/income elasticity estimates across 100+ countries and commodities. Pre-computed rather than transaction data, so it is a benchmark table to sanity-check whatever the model fits from `scanner_data.csv`, not primary modeling input. Last updated 2006. |
| `fish_prices.csv` | [`wooldridge` package](https://pypi.org/project/wooldridge/) (`fish`, Graddy 1995) | 97 daily Fulton Fish Market price/quantity observations by buyer type, with wave-height/wind-speed instruments for IV elasticity estimation. Small, clean, classic textbook identification dataset, good for a demo fixture. |
| `smoking_prices.csv` | [`wooldridge` package](https://pypi.org/project/wooldridge/) (`smoke`, Mullahy 1997) | 807 individuals: state cigarette price vs. cigarettes/day with demographic controls. Individual-level rather than SKU-level elasticity data. |

The rest are genuinely blocked from this environment and are left
**undownloaded** rather than faked:

- **4 Kaggle datasets** (`retail_transactions.csv`, `retail_price_dataset.csv`, `retail_store_transactions.csv`, plus `scanner_data_kaggle.csv`). The Kaggle API returns `403 Permission 'datasets.get' was denied` for every dataset, gated or public, without credentials. Fix: `pip install kaggle`, create a token at kaggle.com/settings, save it to `~/.kaggle/kaggle.json`, then re-run `python -m src.data_loader` and it will pick these up automatically.
- **`dominicks_combined.csv`** (raw Kilts Center Dominick's data). Requires manual academic registration at chicagobooth.edu, and there is no API.
- **`walmart_sales_weekly.csv`**. A Kaggle competition dataset, so it needs a competition join plus Kaggle auth.
- **`efood_elasticities.csv`** (Harvard Dataverse). **Not actually WAF-blocked**, contrary to what this file said until recently: `GET /api/datasets/:persistentId/` returns clean 200 JSON with full metadata for all 23 files. The real block is a one-time Dataverse guestbook form (name, email, institution) required before any file downloads. Fill it once at the [dataset page](https://doi.org/10.7910/DVN/OXZ0H6) and the `.tab` files download normally, which is closer to free registration than a hard gate.
- **`cheese.csv`**. No verifiable public source found. The Dominick's raw data has a cheese category, but the anonymized Monash reformat can't be split by category.
- **`competition_data.csv`**. No concrete URL was ever specified for this one.

### Other candidates researched and ruled out

Also checked for freely-downloadable price/quantity data and found no
better path than what's above:

- **Instacart Market Basket**. The official dataset page now 404s, it only survives on Kaggle behind the same auth wall, and it lacks a price column entirely.
- **RetailRocket e-commerce events**. Kaggle-only, and price isn't a clean field (mostly view/cart/transaction events).
- **M5 / Walmart** was ruled out here on an earlier pass and has since been **adopted** as the second catalogue. The original is behind a Kaggle competition join, and the GitHub mirrors are unofficial. The completeness worry is now settled: `src/walmart_data.py` checks every file against the published M5 shape (1,969 calendar days ending 2016-06-19, 6,841,121 prices, 10 stores, 3,049 items, 1,941 day columns) and refuses to write anything that does not match. The redistribution question is a judgement call rather than a technical one: the data is published by the M Open Forecasting Center, the organisers' own `Mcompetitions/M5-methods` repo is public, and the CSVs are widely mirrored. If that is not a comfortable basis, drop `walmart_data.py` and the catalogue falls back to UK-only cleanly.
- **OpenICPSR** (Billion Prices Project, markup and price-comparison papers). Landing pages return `403` to a direct fetch, and any download requires a free account, same as Kaggle.

Full detail, row counts, and column notes are in
`data/manifests/data_manifest.csv` and `data/manifests/validation_report.txt`.

### The second catalogue: Walmart, 2011 to 2016

The original catalogue is one UK wholesaler over two years, and its
departments are guessed from words in the product name. The M5 release fixes
both problems:

| | UK catalogue | Walmart catalogue |
|---|---|---|
| what | gift and homeware wholesale | food, household, hobbies |
| when | Dec 2009 to Dec 2011 | Jan 2011 to Jun 2016 |
| where | one online shop | 10 stores, CA / TX / WI |
| money | GBP | USD |
| departments | guessed from product names | the retailer's own |
| scale | 194,489 SKU-weeks | 3,999,586 store-item-weeks |
| behind it | 1.07M transactions | 59,181,090 daily records |

The source is the [M5 Forecasting Accuracy](https://github.com/Mcompetitions/M5-methods)
dataset from the M Open Forecasting Center. That repository holds the
competition's code but not its data, so `src/walmart_data.py` pulls the CSVs
from a public mirror and checks them against the published M5 shape before
writing anything: 1,969 calendar days ending 2016-06-19, 6,841,121 weekly
prices, 10 stores, 3,049 items, 30,490 series of 1,941 days. A mirror that
does not match fails loudly.

Daily units are rolled up to the Walmart week that shelf prices are quoted
in, then **inner joined** to `sell_prices` on `store_id + item_id +
wm_yr_wk`. Inner is deliberate: a missing price row means the store was not
carrying that item yet, so those weeks have to disappear rather than be
filled. That drops 8,476,220 store-item-weeks to 6,719,161, of which
5,110,257 had at least one sale.

Grocery comes out where the literature says it should. Overall **-0.65**
against the UK catalogue's -1.90, with Foods at -0.72, Hobbies at -0.62 and
Household at -0.47. California is the least price-sensitive state at -0.21,
Wisconsin the most at -1.04.

### Blending the two

**A union, not a join.** The two catalogues share no match key at all: no
product ids, no stores, no category names, not even a currency. An inner join
returns zero rows; an outer join returns a table of nulls. So
`src/build_blended_catalogue.py` does a vertical `UNION ALL` onto one
harmonised schema.

Stacking works across currencies because of what the estimator does. Every
figure is a within-entity log-log slope, and demeaning log price inside an
entity removes any constant multiplicative factor. An exchange rate is
exactly that. The slopes are already the same dimensionless unit, so no
conversion is needed or wanted.

The stacked rows are pooled with **random effects**, not fixed. Walmart
brings twenty times the observations, so anything weighted by sample size or
by inverse variance alone is not a blend, it is the Walmart number wearing a
blend's clothes:

| | pooled elasticity |
|---|---|
| fixed effect | **-0.94** (sits on top of Walmart) |
| random effects | **-1.71** (the headline) |
| UK alone | -2.00 across 11 departments |
| Walmart alone | -0.64 across 13 groups |

And the number worth reading first is the disagreement: Cochran's Q is
**14,890** on 13 degrees of freedom, giving **I squared of 99.9%**. Almost
none of the spread between these groups is sampling noise. On the stacked
chart you can see it: every UK department sits left of break-even, every
Walmart category sits right of it, and the pooled figure lands in the empty
gap between the two clusters. It is a midpoint between two different trades,
not one answer covering both.

### The twelve reference markets

Eight of the ten originally-scoped datasets are gated, which left the product
estimating exactly one market: UK wholesale gift and homeware. Nobody asking
"should I put this price up?" is necessarily in that trade, and a single
market gives you nothing to judge your own category against.

So the coverage was found somewhere reachable. `src/screen_archives.py` clones
three public archives and profiles every CSV in them for a positive numeric
price column beside a non-negative numeric quantity column:

| archive | files | rows | candidates |
|---|---:|---:|---:|
| [Rdatasets](https://github.com/vincentarelbundock/Rdatasets) | 3,701 | 15,958,347 | 21 |
| [TidyTuesday](https://github.com/rfordatascience/tidytuesday) | 1,175 | 38,752,758 | 2 |
| [plotly/datasets](https://github.com/plotly/datasets) | 1,084 | 9,791,644 | 3 |
| **total** | **5,960** | **64,502,749** | **26** |

That is 656,584,040 individual values read to find 26 files worth a second
look. The screen is mechanical on purpose, and it is not the last word. Each of the 26
was then read against its own documentation, which is the only step that could
catch these three:

| rejected | its own docs say |
|---|---|
| `ISLR/Carseats` | "A simulated data set containing sales of child car seats at 400 different stores." |
| `Stat2Data/Grocery` | "These data are not real, though they are simulated to approximate an actual study." |
| `sem/Kmenta` | "The endogenous variables P and Q were generated by simulation." |

All three carry a price column, a quantity column, and a plausible retail
story. All three would have fit beautifully and meant nothing.

Twelve real markets survived, 77,868 rows, most of them from published
papers:

| market | rows | source |
|---|---:|---|
| Theatre tickets (Broadway) | 47,524 | Playbill weekly grosses, 1,122 shows, 1985 to 2020 |
| Canned tuna | 13,705 | Kim, Blattberg & Rossi (1995) |
| Ketchup | 4,956 | Kim, Blattberg & Rossi (1995) |
| Crackers | 3,292 | Jain, Vilcassim & Chintagunta (1994) |
| Catsup | 2,798 | Jain, Vilcassim & Chintagunta (1994) |
| Yogurt | 2,412 | Jain, Vilcassim & Chintagunta (1994) |
| Cigarettes (46 states, 1963 to 1992) | 1,380 | Baltagi & Levin (1992) |
| Orange juice | 1,070 | Stine, Foster & Waterman (1998) |
| Rail freight (grain, 1880s) | 328 | Porter (1983) |
| Avocados (California) | 169 | Hass Avocado Board, 2015 to 2018 |
| Household natural gas | 138 | Baltagi (2002) |
| Cigarettes (48 states, 1985 & 1995) | 96 | Stock & Watson (2007) |

They land where the literature says they should. The Stock & Watson cigarette
panel comes out at **-1.15**, against their published IV estimates of roughly
-0.94 to -1.28. Brand-level scanner elasticities run **-1.4 to -3.2**, steep in
the way brand switching implies. A shopper leaving Heinz usually arrives at
Hunt's, two feet away.

### The two that came out unusable

Both are reported and labelled rather than quietly dropped, because between
them they are the best evidence on the page for the caveat everything else
rests on.

**Household natural gas** returns -0.001 with an interval of -0.030 to
+0.028. The dataset ships no price index, so those are nominal prices across
twenty-two inflationary years. The interval spans zero: this data cannot tell
you the sign, let alone the size.

**Broadway** returns **+0.074**, higher prices going with *more* seats sold, on
47,361 observations and a tight interval. That is not a demand curve. Hit
shows raise prices *because* they are selling out, so what the regression
picks up is the demand shock, not the price response. It is the largest
dataset in the roster and it produces the wrong sign, which is precisely why
it is worth showing.

## Method, and what it isn't

Transactions are rolled up to one row per SKU per week, then `log(quantity)` and
`log(price)` are demeaned **within each SKU** before pooling. That removes each
product's baseline popularity and price level, so the slope reflects how changes
in a product's *own* price relate to changes in its *own* volume, rather than the
cross-sectional fact that expensive things sell in smaller numbers.

Three things it can't tell you, all stated on the page itself:

- **It's a pattern, not a promise.** Nobody ran a pricing experiment. Prices moved
  for reasons, promotions, seasons, clearance, and those reasons moved sales too.
- **Revenue is not profit.** A discount that grows revenue can still shrink what
  you keep.
- **One catalogue, one market.** UK wholesale gift and homeware, in GBP. The
  direction of an effect usually travels; the exact numbers don't. This is what
  the twelve reference markets are for. They put the catalogue's categories next
  to trades measured the same way.

Categories are assigned by keyword rules against the free-text product description,
because the source data ships no category field. A category is only reported once
it clears 500 weekly observations across at least 15 products.

## Tests

```
pytest                              # everything (123 tests)
pytest tests/test_api.py            # API contract only, no browser needed
pytest tests/test_reference_data.py # the estimator and the dataset roster
```

`tests/test_reference_data.py` builds panels with a known slope and checks the
estimator recovers it to within 0.01, including one where big sellers are also
expensive, so a naive regression reports *upward*-sloping demand and the
within-entity transform has to be unmoved by it. It also pins that the
estimator returns nothing, rather than a number, when a slope isn't
identified.

`tests/test_frontend.py` drives a real Chromium through Playwright: responsive
behaviour at five widths, keyboard and screen-reader affordances, the combobox,
the scenario math as rendered, theming, and URL state. It skips itself when no
browser is available, so `pytest` still works on a bare machine.

Several of those tests are named as regression guards for specific defects found
in the build this replaced, a `[hidden]` attribute that CSS silently overrode,
a 280px chart floor that gave phones a horizontal scrollbar, hover-only tooltips
no keyboard could reach, and a product picker that capped a 4,896-item catalogue
at 500 entries in a plain `<select>`.

## Deploying

Vercel builds `src.api:app` from the `[tool.vercel]` entrypoint in
`pyproject.toml`, which pins only `fastapi` and `pydantic`. Everything the page
needs is inlined or served from the same origin, so there is no build step and no
static asset pipeline.

Set `PEP_DEV_RELOAD=1` locally to re-read `src/web/*` on every request instead of
caching them at startup.

---

A research and portfolio project built on public data. It is not pricing advice.
