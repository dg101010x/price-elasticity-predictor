# Price Sensitivity Lab

A pricing tool built on public retail transaction data. You pick something you
sell, propose a price change, and it tells you what that change did to units and
revenue the last time prices moved like that — and, if you give it a unit cost,
whether the money you actually keep moves the same way.

Underneath it is a within-SKU log-log panel regression. On the surface it is a
question a price-setter can answer without knowing what any of those words mean.

```
uvicorn src.api:app --reload      # http://localhost:8000
```

## What's here

```
src/
  api.py                    FastAPI app: serves the page and the JSON API
  elasticity_math.py        the revenue/profit arithmetic (mirrored in app.js)
  dashboard.py              inlines src/web/* into one self-contained response
  web/
    index.html              markup
    app.css                 design system + both themes
    app.js                  state, interactions, and the three SVG charts
    fonts/                  self-hosted Archivo + IBM Plex Mono (OFL)
  build_elasticity_model.py fits the estimates from the raw CSV
  data_loader.py            downloads the source datasets
  build_manifest.py         profiles data/csv/*.csv into the manifest
tests/                      API contract, shared math, browser + a11y
data/
  processed/                elasticity_results.json, products.json (gitignored)
  manifests/                data_manifest.csv, validation_report.txt (tracked)
```

The page ships as a single response with **no external requests at all** — no CDN,
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

`/estimates` exists because the dashboard used to issue one `/elasticity` request
per category on every interaction — eleven identical round-trips per keystroke,
for data that never changes.

Interactive docs at `/docs`.

## The one number that matters

Revenue is flat in price at exactly **elasticity = −1**. More negative than that
and a price rise loses more in units than it gains per unit, so discounting grows
revenue. Less negative and it's the other way round. Everything the interface
says is built on which side of that line an estimate falls, and whether its
confidence interval is narrow enough to be sure.

`src/elasticity_math.py` is the canonical implementation. `src/web/app.js`
carries a JavaScript mirror so the price slider responds without a round-trip;
`tests/` pins both against the same expectations so they can't drift.

## Data

Datasets live in `data/csv/` (gitignored — regenerate locally, don't commit) and
are documented in `data/manifests/data_manifest.csv`.

```
python -m src.data_loader             # fetches + converts real datasets
python -m src.build_manifest          # profiles them, writes the manifest
python -m src.build_elasticity_model  # fits the estimates the API serves
```

### What's actually downloaded vs. what needs manual setup

Of the ten datasets originally scoped, two are freely downloadable (no account,
no registration) and are fetched for real by `src/data_loader.py`:

| file | source | why it substitutes |
|---|---|---|
| `scanner_data.csv` | [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | 1.07M transaction rows, 5,305 SKUs, Dec 2009–Dec 2011. Stands in for the gated Kaggle `marian447/retail-scanner-data` notebook dataset — same author's dataset is very likely derived from this exact UCI source (5,242 vs. 5,305 SKUs). |
| `monash_dominicks.csv` | [Monash "Dominick Dataset" on Zenodo](https://zenodo.org/records/4654802) | 19.1M rows, 115,704 weekly per-SKU profit series, reformatted from the Kilts Center Dominick's Finer Foods data. Anonymized (no store/UPC/category), so it's useful for time-series modeling but not for category breakdowns. |

The rest are genuinely blocked from this environment and are left
**undownloaded** rather than faked:

- **4 Kaggle datasets** (`retail_transactions.csv`, `retail_price_dataset.csv`, `retail_store_transactions.csv`, plus the scanner data above) — the Kaggle API returns `403 Permission 'datasets.get' was denied` for every dataset, gated or public, without credentials. Fix: `pip install kaggle`, create a token at kaggle.com/settings, save it to `~/.kaggle/kaggle.json`, then re-run `python -m src.data_loader` — it will pick these up automatically.
- **`dominicks_combined.csv`** (raw Kilts Center Dominick's data) — requires manual academic registration at chicagobooth.edu; no API.
- **`walmart_sales_weekly.csv`** — Kaggle competition dataset; needs competition join + Kaggle auth.
- **`efood_elasticities.csv`** (Harvard Dataverse) — `dataverse.harvard.edu` sits behind a WAF bot-challenge that blocks non-browser requests. Download manually via the DOI.
- **`cheese.csv`** — no verifiable public source found; the Dominick's raw data has a cheese category but the anonymized Monash reformat can't be split by category.
- **`competition_data.csv`** — no concrete URL was ever specified for this one.

Full detail, row counts, and column notes are in
`data/manifests/data_manifest.csv` and `data/manifests/validation_report.txt`.

## Method, and what it isn't

Transactions are rolled up to one row per SKU per week, then `log(quantity)` and
`log(price)` are demeaned **within each SKU** before pooling. That removes each
product's baseline popularity and price level, so the slope reflects how changes
in a product's *own* price relate to changes in its *own* volume, rather than the
cross-sectional fact that expensive things sell in smaller numbers.

Three things it can't tell you, all stated on the page itself:

- **It's a pattern, not a promise.** Nobody ran a pricing experiment. Prices moved
  for reasons — promotions, seasons, clearance — and those reasons moved sales too.
- **Revenue is not profit.** A discount that grows revenue can still shrink what
  you keep.
- **One catalogue, one market.** UK wholesale gift and homeware, in GBP. The
  direction of an effect usually travels; the exact numbers don't.

Categories are assigned by keyword rules against the free-text product description,
because the source data ships no category field. A category is only reported once
it clears 500 weekly observations across at least 15 products.

## Tests

```
pytest                    # everything
pytest tests/test_api.py  # API contract only, no browser needed
```

`tests/test_frontend.py` drives a real Chromium through Playwright: responsive
behaviour at five widths, keyboard and screen-reader affordances, the combobox,
the scenario math as rendered, theming, and URL state. It skips itself when no
browser is available, so `pytest` still works on a bare machine.

Several of those tests are named as regression guards for specific defects found
in the build this replaced — a `[hidden]` attribute that CSS silently overrode,
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
