# Price Elasticity Predictor

FastAPI + Streamlit app estimating price elasticity of demand from public
retail transaction data. `src/api.py` serves the estimates (currently from a
stub `elasticity_results.json`-equivalent pending a model fit against
`data/csv/scanner_data.csv`); `app.py` / `src/dashboard.py` render them.

## Data

Datasets live in `data/csv/` (gitignored — regenerate locally, don't commit;
see below) and are documented in `data/manifests/data_manifest.csv`.

```
data/
  csv/            regenerable dataset CSVs (gitignored)
  raw_downloads/  intermediate zip/xlsx/tsf/rds files (gitignored)
  processed/      cleaned/merged versions for modeling (gitignored)
  manifests/      data_manifest.csv, validation_report.txt (tracked)
```

Regenerate everything downloadable without credentials:

```
python -m src.data_loader      # fetches + converts real datasets into data/csv/
python -m src.build_manifest   # profiles data/csv/*.csv, writes the manifest + report
```

Together that's **26 datasets / ~42.9M rows**, all fetched over plain HTTPS
with no account, token or registration. Expect ~510 MB in `data/csv/` and
~75 MB in `data/raw_downloads/`.

### Retail transaction & scanner data

The core sets: real price *and* quantity at the product level.

| file | rows | source | why it's here |
|---|---|---|---|
| `scanner_data.csv` | 1.07M | [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | UK online retailer, 5,305 SKUs, Dec 2009–Dec 2011. What `src/api.py`'s figures (product `85123A` etc.) are drawn from. No category field. |
| `completejourney_transactions.csv` | 1.47M | [dunnhumby / 84.51° "The Complete Journey"](https://github.com/bradleyboehmke/completejourney) | 2,469 households, a full year of US grocery baskets. Carries `quantity`, `sales_value` **and** the discounts taken off it, so both paid and shelf price are recoverable — promotion-driven price variation, which identifies elasticity far better than list prices alone. |
| `completejourney_products.csv` | 92,331 | same | Real `department` / `product_category` / `product_type` / national-vs-private-brand labels. This is what the UCI data lacks — `src/build_elasticity_model.py` currently guesses categories from keywords. |
| `completejourney_promotions.csv` | 20.9M | same | Display and mailer placement per product/store/week — the controls needed to separate a price cut from the display that shipped with it. Large (~390 MB CSV). |
| `olist_order_items.csv` | 112,650 | [olist/work-at-olist-data](https://github.com/olist/work-at-olist-data) (official) | Brazilian marketplace, Sep 2016–Sep 2018, joined here into one row per unit sold with timestamp, price, freight and 71 English category labels. |
| `pizza_pos_sales.csv` | 49,574 | Rdatasets (`gt/pizzaplace`) | A year of pizzeria POS lines; price varies by size and over time. Transaction-level elasticity outside the gift-retail domain. |

### Store/product weekly panels

| file | rows | source | why it's here |
|---|---|---|---|
| `dominicks_oj.csv` | 28,947 | Kilts Center DFF extract ([mirror](https://raw.githubusercontent.com/gchoi/Dataset/master/oj.csv)) | 83 Chicago stores × 3 OJ brands × 121 weeks with shelf price, `feat` promotion flag and store demographics. The store-level, cross-brand panel `monash_dominicks.csv` can't provide. Falls back to a reduced 4-column mirror if the primary is gone. |
| `monash_dominicks.csv` | 19.1M | [Monash "Dominick Dataset"](https://zenodo.org/records/4654802) | 115,704 weekly per-SKU profit series, anonymized (no store/UPC/category/date), so: time-series modeling yes, category breakdowns no. |
| `grocery_promo_experiment.csv` | 36 | Rdatasets (`Stat2Data/Grocery`) | Tiny, but the price variation is *experimental* — the one genuinely causal elasticity in the set. |

### Household brand-choice panels (cross-price)

Each purchase occasion records the price of **every** competing brand, not
just the one bought — which is what makes cross-price elasticity estimable.

`brandchoice_crackers.csv` (3,292) · `brandchoice_yogurt.csv` (2,412) ·
`brandchoice_catsup.csv` (2,798) · `brandchoice_ketchup.csv` (4,956) ·
`brandchoice_tuna.csv` (13,705) · `oj_brand_choice.csv` (1,070, Dominick's
CH-vs-MM with discounts and a loyalty score). Crackers, yogurt and catsup also
carry per-brand display/feature flags.

### Benchmark demand curves

Small, canonical datasets with *published* elasticities — the point is having
a known answer to check a model against, and fixtures small enough to use as
regression tests.

| file | rows | what |
|---|---|---|
| `cigarettes_state_panel.csv` | 1,380 | 46 states × 30 years: sales, price, income, and the cheapest neighbouring-state price (bootlegging substitute) |
| `cigarettes_sw_panel.csv` | 96 | Stock & Watson's panel with the two tax instruments — the reference for *instrumented* (causal) elasticity |
| `journals_subscriptions.csv` | 180 | 180 economics journals; the textbook log-log demand curve |
| `fulton_fish_market.csv` | 97 | Daily price/quantity with weather-at-sea supply shifters; the canonical demand-identification example |
| `avocado_weekly.csv` | 169 | Weekly US Hass avocado price and volume |
| `icecream_demand.csv` | 30 | Consumption, price, income, temperature |
| `gasoline_oecd_panel.csv` | 342 | 18 OECD countries 1960–78; short- vs long-run elasticity |
| `gasoline_us_substitutes.csv` | 36 | US gasoline with substitute/complement price indices already in the file |
| `natural_gas_us_panel.csv` | 138 | US residential gas with electricity, oil and LPG prices |
| `budget_shares_italy.csv` | 1,729 | Expenditure shares + a price index per group — the shape an AIDS/QUAIDS demand system wants |
| `carseats_competitor_price.csv` | 400 | The only readily available file with an explicit competitor price column (simulated — a fixture, not evidence) |

Sanity check — a plain log-log fit on each of these lands where the
literature says it should, which is the point of keeping them around:

```
dominicks_oj / dominicks              -3.38     journals_subscriptions   -0.53
dominicks_oj / minute.maid            -3.32     cigarettes_state_panel   -0.76
dominicks_oj / tropicana              -2.71     avocado_weekly           -0.68
completejourney (within-product)      -0.89     fulton_fish (OLS)        -0.49
```

(The Fulton figure is the well-known OLS understatement; instrumenting price
with wave height moves it to about −0.9. `journals` reproduces the published
−0.53 exactly.)

### Still blocked, and why

Left **undownloaded** rather than faked. `data_loader.py` declares each one so
the manifest keeps saying so, and `download_kaggle_dataset()` is a real
function that starts working the moment credentials exist.

- **Kaggle** (`scanner_data_kaggle.csv`, `retail_transactions.csv`, `retail_price_dataset.csv`, `retail_store_transactions.csv`, `walmart_sales_weekly.csv`, `m5_sell_prices.csv`, `tafeng_transactions.csv`) — the API returns `403 Permission 'datasets.get' was denied` for every dataset, gated or public, without credentials. Fix: `pip install kaggle`, create a token at kaggle.com/settings, save it to `~/.kaggle/kaggle.json`, then re-run `python -m src.data_loader` — it picks these up automatically. M5's `sell_prices.csv` is ~200 MB, over GitHub's file limit, so no raw mirror exists to fall back on.
- **`dominicks_combined.csv`** (raw Kilts Center Dominick's, all 29 categories) — manual academic registration at chicagobooth.edu; no API. `dominicks_oj.csv` above is one category of it.
- **`efood_elasticities.csv`** (Harvard Dataverse) — `dataverse.harvard.edu` sits behind a WAF bot-challenge that blocks non-browser requests. Download manually via the DOI.
- **`cheese.csv`** — no verifiable public source found; it appears to be `bayesm::cheese`, which ships inside a CRAN source tarball rather than as a standalone file.
- **`competition_data.csv`** — no concrete URL was ever specified. `carseats_competitor_price.csv` has the same shape (own price + competitor price + advertising) if you need a fixture.

A dataset can also come back **`unreachable`**: the source is fine but this
machine can't reach it (restricted network, egress policy). Each fetch is
independent, so one blocked host doesn't abort the run, and
`build_manifest.py` carries a previous run's profile forward rather than
erasing numbers it couldn't re-measure. Full detail, row counts and column
notes are in `data/manifests/data_manifest.csv` and
`data/manifests/validation_report.txt`.

## Running locally

```
uvicorn src.api:app --reload      # API on :8000
streamlit run app.py              # dashboard, expects API_BASE_URL
```
