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

Of the ten datasets originally scoped, two are freely downloadable (no
account, no registration) and are fetched for real by `src/data_loader.py`:

| file | source | why it substitutes |
|---|---|---|
| `scanner_data.csv` | [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | 1.07M transaction rows, 5,305 SKUs, Dec 2009–Dec 2011. Stands in for the gated Kaggle `marian447/retail-scanner-data` notebook dataset — same author's dataset is very likely derived from this exact UCI source (5,242 vs. 5,305 SKUs). This is also what `src/api.py`'s stub numbers (product `85123A`, etc.) are already drawn from. |
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

## Running locally

```
uvicorn src.api:app --reload      # API on :8000
streamlit run app.py              # dashboard, expects API_BASE_URL
```
