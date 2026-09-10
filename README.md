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
  raw_downloads/  intermediate zip/xlsx/tsf files (gitignored)
  processed/      cleaned/merged versions for modeling (gitignored)
  manifests/      data_manifest.csv, validation_report.txt (tracked)
```

Regenerate everything downloadable without credentials:

```
python -m src.data_loader      # fetches + converts real datasets into data/csv/
python -m src.build_manifest   # profiles data/csv/*.csv, writes the manifest + report
```

### What's actually downloaded vs. what needs manual setup

Five datasets are freely downloadable (no account, no registration) and are
fetched for real by `src/data_loader.py`:

| file | source | why it's useful |
|---|---|---|
| `scanner_data.csv` | [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | 1.07M transaction rows, 5,305 SKUs, Dec 2009–Dec 2011. Stands in for the gated Kaggle `marian447/retail-scanner-data` notebook dataset — same author's dataset is very likely derived from this exact UCI source (5,242 vs. 5,305 SKUs). This is also what `src/api.py`'s stub numbers (product `85123A`, etc.) are already drawn from. |
| `monash_dominicks.csv` | [Monash "Dominick Dataset" on Zenodo](https://zenodo.org/records/4654802) | 19.1M rows, 115,704 weekly per-SKU profit series, reformatted from the Kilts Center Dominick's Finer Foods data. Anonymized (no store/UPC/category), so it's useful for time-series modeling but not for category breakdowns. |
| `usda_elasticities.csv` | [USDA ERS demand elasticities](https://www.ers.usda.gov/data-products/commodity-and-food-elasticities/documentation) | 14,173 literature-reported own-/cross-price/income elasticity estimates across 100+ countries and commodities. Pre-computed (not transaction data) — a benchmark table to sanity-check whatever the model fits from `scanner_data.csv`, not primary modeling input. Last updated 2006. |
| `fish_prices.csv` | [`wooldridge` package](https://pypi.org/project/wooldridge/) (`fish`, Graddy 1995) | 97 daily Fulton Fish Market price/quantity observations by buyer type, with wave-height/wind-speed instruments for IV elasticity estimation. Small, clean, classic textbook identification dataset — good for a demo fixture. |
| `smoking_prices.csv` | [`wooldridge` package](https://pypi.org/project/wooldridge/) (`smoke`, Mullahy 1997) | 807 individuals: state cigarette price vs. cigarettes/day with demographic controls. Individual-level rather than SKU-level elasticity data. |

The rest are genuinely blocked from this environment and are left
**undownloaded** rather than faked:

- **4 Kaggle datasets** (`retail_transactions.csv`, `retail_price_dataset.csv`, `retail_store_transactions.csv`, plus `scanner_data_kaggle.csv`) — the Kaggle API returns `403 Permission 'datasets.get' was denied` for every dataset, gated or public, without credentials. Fix: `pip install kaggle`, create a token at kaggle.com/settings, save it to `~/.kaggle/kaggle.json`, then re-run `python -m src.data_loader` — it will pick these up automatically.
- **`dominicks_combined.csv`** (raw Kilts Center Dominick's data) — requires manual academic registration at chicagobooth.edu; no API.
- **`walmart_sales_weekly.csv`** — Kaggle competition dataset; needs competition join + Kaggle auth.
- **`efood_elasticities.csv`** (Harvard Dataverse) — **not actually WAF-blocked** (re-verified: `GET /api/datasets/:persistentId/` returns clean 200 JSON with full metadata for all 23 files). The real block is a one-time Dataverse "guestbook" form (name/email/institution) required before any file downloads. Fill it once at the [dataset page](https://doi.org/10.7910/DVN/OXZ0H6), then the `.tab` files download normally — closer to free registration than a hard gate.
- **`cheese.csv`** — no verifiable public source found; the Dominick's raw data has a cheese category but the anonymized Monash reformat can't be split by category.
- **`competition_data.csv`** — no concrete URL was ever specified for this one.

### Other candidates researched and ruled out

Also checked for freely-downloadable price/quantity data and found no
better path than what's above:

- **Instacart Market Basket** — official dataset page now 404s; only survives on Kaggle (same auth wall), and it lacks a price column entirely.
- **RetailRocket e-commerce events** — Kaggle-only, and price isn't a clean field (mostly view/cart/transaction events).
- **M5 / Walmart forecasting `sell_prices.csv`** — original is behind a Kaggle *competition* join (stricter than a plain dataset); unofficial GitHub mirrors exist but weren't verified complete/correct and raise ToS questions about rehosting competition data.
- **OpenICPSR** (Billion Prices Project, markup/price-comparison papers) — landing pages return `403` to direct fetch; requires a free account for any download, same as Kaggle.

Full detail, row counts, and column notes are in
`data/manifests/data_manifest.csv` and `data/manifests/validation_report.txt`.

## Running locally

```
uvicorn src.api:app --reload      # API on :8000
streamlit run app.py              # dashboard, expects API_BASE_URL
```
