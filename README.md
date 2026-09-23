# Price Sensitivity Lab

A pricing tool built on public retail transaction data. You pick something you
sell, propose a price change, and it tells you what that change did to units and
revenue the last time prices moved like that — and, if you give it a unit cost,
whether the money you actually keep moves the same way.

Underneath it is a within-SKU log-log panel regression. On the surface it is a
question a price-setter can answer without knowing what any of those words mean.

Since 2.1 it also answers the question that comes straight after — *is that a
normal number?* — by fitting the same kind of estimate to eighteen other
public datasets, from 1880s rail freight to a Chicago supermarket's orange
juice shelf, and putting your catalogue among them.

Since 3.0 a business can run it on **its own sales**: sign up, upload a CSV,
and get its own estimate — fitted by the same code, with the same likely
range, the same R², the same caveats — plus recommendations written from
those numbers and nothing else, and its number placed among the same
thirteen markets. See [Accounts](#accounts-30).

```
uvicorn src.api:app --reload      # http://localhost:8000 — the public page
python -m tests.dev_stack         # the whole product, locally, no keys needed
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
    app.js                  state, interactions, and the four SVG charts
    fonts/                  self-hosted Archivo + IBM Plex Mono (OFL)
  build_elasticity_model.py fits the estimates from the raw CSV
  data_loader.py            downloads the source datasets
  build_manifest.py         profiles data/csv/*.csv into the manifest
  reference_datasets.py     the 18 external datasets, their licences and citations
  panel_fit.py              the estimators: within, clustered OLS, 2SLS, conditional logit
  build_benchmarks.py       fits one benchmark per external dataset
  stats_engine.py           THE estimator: weekly rollup, within-product regression,
                            category bar. Used by the public build and every account
  account/                  sign-in, uploads, per-account estimates and insights
    routes.py               /api/* — auth, onboarding, uploads, account estimates
    pages.py                /login, /onboarding, /dashboard/* (gated server-side)
    ingest.py               CSV -> column mapping -> clean -> weekly panel -> fit
    pipeline.py             upload -> Storage -> data_sources -> observations -> runs
    insights.py             recommendations, and the check on every number in them
    llm.py                  the only file that knows about Gemini
    supabase.py             Auth / Data / Storage over plain HTTP
    session.py              httpOnly cookie sessions, refreshed server-side
    results.py              stored runs -> the shapes the page already draws
  web/
    partials/               sections shared by the public page and the dashboard
    account/                dashboard shell and page bodies
    account.css, dash.js    what only a signed-in business needs
supabase/migrations/        the schema, RLS policies, grants and storage bucket
examples/                   two synthetic sales CSVs to try the uploader with
tests/                      API contract, shared math, estimators, browser + a11y,
                            RLS, end-to-end accounts, insights grounding
data/
  processed/                elasticity_results.json, products.json, benchmarks.json
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
| `GET /benchmarks` | the same question asked of 13 other markets, plus this site's own estimate in the same shape |

`/estimates` exists because the dashboard used to issue one `/elasticity` request
per category on every interaction — eleven identical round-trips per keystroke,
for data that never changes.

Account endpoints, added in 3.0 (cookie session; `401` signed out, `503` when
Supabase isn't configured):

| endpoint | what it gives you |
|---|---|
| `POST /api/auth/signup` · `/login` · `/logout` · `/session` | cookie sessions over Supabase Auth |
| `GET /api/me` · `POST /api/account` | who's signed in; onboarding |
| `POST /api/uploads/inspect` · `POST /api/uploads` · `GET /api/uploads` | column mapping, synchronous upload-and-fit, history |
| `GET /api/account/estimates` · `/catalog` · `/benchmarks` | the latest upload, in the same shapes as the three public ones |
| `GET` · `POST /api/account/insights` | grounded recommendations, their trace, and the run-over-run check |

Interactive docs at `/docs`.

## Accounts (3.0)

The public page answers "what did price do to one UK catalogue". The signed-in
product asks the same question of a business's own sales history, and keeps
the three things that made the public answer worth trusting:

1. **Every number has a real confidence interval and R², fitted, never
   generated.** Uploads go through `src/stats_engine.py` — the *same* function
   the public estimate comes from, not a re-implementation.
   `tests/test_stats_engine.py` freezes the 2.1.0 code as an oracle and
   requires identical published figures; `tests/test_account_e2e.py` refits
   each account's stored observations and requires the stored estimate back
   exactly.
2. **The plain-English method and glossary apply to the account's results.**
   The same verdict, evidence grades, "three things this can't tell you" and
   glossary, reworded for "your sales" rather than "a UK wholesaler".
3. **The thirteen public markets stay on the dashboard** as context
   (`/dashboard/benchmarks`), with the business drawn among them.

### How it fits together

```
browser ──same origin only──▶ FastAPI on Vercel (one Python function)
                                 │  pages + /api/*, cookie session
                                 │  CSV → ingest → stats_engine → runs
                                 │  runs (six numbers each) → Gemini → validator
                                 ▼
                              Supabase: Auth · Postgres + RLS · Storage
```

- **No framework, no CDN, still.** The dashboard is the public page's own
  `app.js` pointed at `/api/account/*`, plus `dash.js` for what only an
  account has. Shared sections live once in `src/web/partials/`. Each page is
  one self-contained response; the browser never talks to Supabase or Google.
- **Tenant isolation is the database's job.** Every table carries
  `account_id` under row-level security. The server reads with the user's own
  token, so RLS — not app code — decides what they see. Computed results
  (observations, runs, insights) are written only by the server's service
  role: an account cannot insert an estimate it didn't fit, or file an upload
  as `ready`. Uploads go to Storage with the user's token, so the bucket
  policy decides who may write (`owner`/`manage` only).
- **Uploads are synchronous.** A catalogue of weekly sales fits in one
  request. The browser gzips the CSV (Vercel caps request bodies at 4.5 MB;
  CSV compresses 5–10×). Columns are matched by alias; anything not matched
  exactly — including dates that read either way round, 03/04 — is put to the
  user rather than guessed. Every failure is recorded with a reason on the
  Data page.
- **Categories follow the public rule**: at least 500 product-weeks across 15
  products, otherwise excluded with the reason shown. Rows with no category
  count towards the whole-range estimate, like "Other/Uncategorized".

### Insights, and why they can't make numbers up

The model is shown one thing: the list of six-field run objects —
`category, coefficient, ci_low, ci_high, r_squared, n_observations`. No sales
rows, no product names, nothing to compute a new number from. Every numeric
token in the reply must equal one of those values (as written, with its sign
dropped, or r_squared as a percentage); spelled-out quantities ("ten
percent", "twice") are refused. One stricter retry names what was wrong;
after that a deterministic template writes the recommendations instead,
held to the same validator by a property test. What's stored links each
number to the run and field it came from, and the Insights page lets anyone
select a number and see its source.

`src/account/llm.py` is the only file that knows the model. Moving to
Gemini's **paid tier** is a billing switch in AI Studio, not code — same key,
same endpoint; set `GEMINI_TIER=paid` so the page stops telling people their
numbers may be used to improve Google's products. `GEMINI_MODEL` pins a model
instead of the rolling `gemini-flash-latest` alias. With no key, the
template writes them and the page says so.

The first step of the feedback loop is in: each upload's estimates are
checked against the previous upload's intervals ("did the last estimate
hold?"), derived from the stored runs.

### Setting it up

1. **Database.** Apply `supabase/migrations/*.sql` to the Supabase project —
   `supabase db push`, or paste it into the SQL editor. It creates the
   tables, policies, grants (explicit, since new projects no longer grant
   `public` tables automatically), the `sales-uploads` bucket and its policies.
2. **Environment** (Vercel → Project Settings → Environment Variables, or a
   local `.env.local` — see `.env.example`): `NEXT_PUBLIC_SUPABASE_URL`,
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` (anon or `sb_publishable_` key),
   `SUPABASE_SERVICE_ROLE_KEY` (service_role or `sb_secret_` key),
   `GEMINI_API_KEY`. All are read server-side only.
3. **Auth redirect.** Supabase → Authentication → URL Configuration: add
   `https://<your-domain>/login` to the redirect URLs, so the confirmation
   email lands back on the sign-in page. (If it lands on `/` instead, the
   public page forwards it.)

Without step 2 the public page is unchanged and `/login` says accounts
aren't switched on.

### Running it locally without any of that

```
python -m tests.dev_stack        # http://127.0.0.1:8000, demo@example.com / demo-password
```

Starts a throwaway Postgres with the real migration, real PostgREST, and a
small stand-in for Supabase Auth and Storage (`tests/supabase_gateway.py`),
then seeds a demo business. Needs the Postgres server binaries and a
PostgREST binary on `PATH` (or at `.tools/postgrest`).

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
python -m src.build_benchmarks        # fits the other-market comparison
```

21 of the 30 datasets in the manifest are downloaded with no account of any
kind. The other nine are behind a Kaggle token or an academic registration
and are left undownloaded rather than faked.

### The primary dataset, and the four that check it

| file | source | why it's useful |
|---|---|---|
| `scanner_data.csv` | [UCI Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) | 1.07M transaction rows, 5,305 SKUs, Dec 2009–Dec 2011. Stands in for the gated Kaggle `marian447/retail-scanner-data` notebook dataset — same author's dataset is very likely derived from this exact UCI source (5,242 vs. 5,305 SKUs). |
| `monash_dominicks.csv` | [Monash "Dominick Dataset" on Zenodo](https://zenodo.org/records/4654802) | 19.1M rows, 115,704 weekly per-SKU profit series, reformatted from the Kilts Center Dominick's Finer Foods data. Anonymized (no store/UPC/category), so it's useful for time-series modeling but not for category breakdowns. |
| `usda_elasticities.csv` | [USDA ERS demand elasticities](https://www.ers.usda.gov/data-products/commodity-and-food-elasticities/documentation) | 14,173 literature-reported own-/cross-price/income elasticity estimates across 100+ countries and commodities. Pre-computed (not transaction data) — a benchmark table to sanity-check whatever the model fits from `scanner_data.csv`, not primary modeling input. Last updated 2006. |
| `fish_prices.csv` | [`wooldridge` package](https://pypi.org/project/wooldridge/) (`fish`, Graddy 1995) | 97 daily Fulton Fish Market price/quantity observations, with wave-height and wind-speed instruments. Downloaded since 1.0 and unused until now; it is fitted as a benchmark below, and the storm instrument makes it one of only three causal estimates on the site. |
| `smoking_prices.csv` | [`wooldridge` package](https://pypi.org/project/wooldridge/) (`smoke`, Mullahy 1997) | 807 individuals: state cigarette price vs. cigarettes/day with demographic controls. Also fitted below — as a deliberate null, since state prices barely move within one year. |

The rest are genuinely blocked from this environment and are left
**undownloaded** rather than faked:

- **4 Kaggle datasets** (`retail_transactions.csv`, `retail_price_dataset.csv`, `retail_store_transactions.csv`, plus `scanner_data_kaggle.csv`) — the Kaggle API returns `403 Permission 'datasets.get' was denied` for every dataset, gated or public, without credentials. Fix: `pip install kaggle`, create a token at kaggle.com/settings, save it to `~/.kaggle/kaggle.json`, then re-run `python -m src.data_loader` — it will pick these up automatically.
- **`dominicks_combined.csv`** (raw Kilts Center Dominick's data) — requires manual academic registration at chicagobooth.edu; no API.
- **`walmart_sales_weekly.csv`** — Kaggle competition dataset; needs competition join + Kaggle auth.
- **`efood_elasticities.csv`** (Harvard Dataverse) — **not actually WAF-blocked** (re-verified: `GET /api/datasets/:persistentId/` returns clean 200 JSON with full metadata for all 23 files). The real block is a one-time Dataverse "guestbook" form (name/email/institution) required before any file downloads. Fill it once at the [dataset page](https://doi.org/10.7910/DVN/OXZ0H6), then the `.tab` files download normally — closer to free registration than a hard gate.
- **`cheese.csv`** — no verifiable public source found; the Dominick's raw data has a cheese category but the anonymized Monash reformat can't be split by category.
- **`competition_data.csv`** — no concrete URL was ever specified for this one.

### The eighteen benchmark datasets (added in 2.1)

Everything above answers "what does *this* catalogue do". None of it answers
"is that a normal number", because a single catalogue has nothing to be
compared against. So `src/reference_datasets.py` collects eighteen external
price/quantity datasets that need **no account at all** — they ship inside
CRAN and PyPI packages, and are mirrored as plain CSVs by
[Rdatasets](https://github.com/vincentarelbundock/Rdatasets) or as package
data on the read-only CRAN GitHub mirror.

They were found by scanning the header row of all 3,648 Rdatasets datasets
and keeping the ones carrying both a price-like and a quantity-like column,
rather than by guessing at names — which is how `AER::CartelStability` and
`AER::NaturalGas` turned up, neither of which matches an obvious keyword.

| what's being priced | dataset | licence | rows |
|---|---|---|---|
| Orange juice, 83 Chicago stores | `bayesm::orangeJuice` | GPL (≥2) | 106,139 store-brand-weeks |
| Cigarettes, 46 US states | `Ecdat::Cigar` | GPL (≥2) | 1,380 state-years |
| Cigarettes, tax-instrumented | `AER::CigarettesSW` | GPL-2 \| GPL-3 | 96 |
| Motor fuel, 18 OECD countries | `AER::OECDGas` | GPL-2 \| GPL-3 | 342 |
| Residential natural gas | `AER::NaturalGas` | GPL-2 \| GPL-3 | 138 |
| Rail freight, 1880s grain routes | `AER::CartelStability` | GPL-2 \| GPL-3 | 328 weeks |
| Whiting, Fulton Fish Market | `wooldridge::fish` | GPL-3 | 97 days |
| Cigarettes, individual smokers | `wooldridge::smoke` | GPL-3 | 807 |
| Journal subscriptions | `AER::Journals` | GPL-2 \| GPL-3 | 180 |
| Hass avocados, California | `causaldata::avocado` | MIT | 169 weeks |
| Ice cream | `Ecdat::Icecream` | GPL (≥2) | 30 |
| Motor fuel, US national | `AER::USGasG` | GPL-2 \| GPL-3 | 36 years |
| Boating trips, Lake Somerville | `AER::RecreationDemand` | GPL-2 \| GPL-3 | 659 |
| Ketchup / catsup / tuna / yogurt / cracker brands | `Ecdat::Ketchup` and four siblings | GPL (≥2) | 27,163 purchase occasions |

The one worth singling out is **`bayesm::orangeJuice`**. The manifest has
listed the raw Kilts Center Dominick's archive as `manual_required` since
1.0, because it needs academic registration. bayesm redistributes an
83-store, 11-brand extract of that same scanner archive on CRAN under GPL:
106,139 store-brand-weeks with log units moved, every brand's price on the
shelf that week, and display and feature-ad flags. That is the
category-labelled, promotion-flagged scanner panel the manifest said was
unobtainable, and it is a plain HTTPS GET away.

**Nothing here is redistributed by this repository.** `data/csv/` stays
gitignored, `src/reference_datasets.py` re-fetches from source, and the only
thing committed is `data/processed/benchmarks.json` — the fitted
coefficients, each with its licence and citation attached. A regression
coefficient is not a copy of the dataset it came from.

### What the benchmarks are fitted with

One estimator per dataset, chosen by what the design supports, and named in
the payload so nothing is blurred (`src/panel_fit.py`, tested against
simulated data with known coefficients in `tests/test_panel_fit.py`):

- **`within`** — log-log with fixed effects absorbed by alternating
  projections, standard errors clustered on the panel unit. Two-way FE on a
  106k-row panel would otherwise need a 106k × 1,000 dummy matrix.
- **`iv`** — two-stage least squares where a real instrument exists: a state
  sales tax, wave height off Long Island, the collapse of a railroad cartel.
  Reported with its first-stage F, because a weak instrument produces a
  confident-looking number that means nothing.
- **`logit`** — conditional logit on the household brand-choice panels,
  converted to an own-price elasticity at sample shares. Those measure
  switching between brands rather than category volume, so they are kept in
  a separate bucket and never drawn on the same axis.

Every record carries `identification`: `instrumented` where there's a
defensible causal claim, `descriptive` everywhere else — the same caveat
this site's own headline estimates carry.

Three of the fits land almost exactly where the literature does, which is
the useful part of doing this at all: Porter's rail cartel at −0.87 (his
paper: ≈ −0.8), Graddy's fish market at −0.81, and `AER::Journals` at −0.53,
the textbook value. The state cigarette panels come out more elastic (≈ −1.0)
than the −0.4 consensus for *smoking*, for a reason the payload states: they
count packs sold in a state, not cigarettes smoked by its residents, and
when one state raises tax, buyers drive across the line.

### Examined and rejected

Not every dataset with a price column can answer this question, and
`src/reference_datasets.py` documents each rejection rather than staying
quiet about it:

- **`gt::pizzaplace`** — 49,574 real pizza orders with SKU-level prices, and
  exactly zero within-SKU price variation across the year (91 SKUs, 91
  distinct prices). Nothing to regress.
- **`Stat2Data::Grocery`** — looks like a promotion experiment until you
  check: `Price` correlates 0.98 with `Sales`, because it is derived from
  it. It fitted at **+3.3** before that was caught, which is what the
  mistake looks like from the outside. `tests/test_api.py` now fails on any
  upward-sloping benchmark.
- **`hdm::BLP`** — 2,217 car models with prices and market shares, but OLS
  on log share is biased toward zero by unobserved quality. That bias is the
  entire reason the BLP method exists; publishing the OLS number beside
  honest estimates would mislead.
- **`ISLR::Carseats`** — simulated. Fine for teaching regression, not
  evidence about a market.
- **`Ecdat::BudgetFood`, `Ecdat::Tobacco`** — budget shares with no prices.

### Other candidates researched and ruled out

Also checked for freely-downloadable price/quantity data and found no
better path than what's above:

- **Instacart Market Basket** — official dataset page now 404s; only survives on Kaggle (same auth wall), and it lacks a price column entirely.
- **RetailRocket e-commerce events** — Kaggle-only, and price isn't a clean field (mostly view/cart/transaction events).
- **M5 / Walmart forecasting `sell_prices.csv`** — original is behind a Kaggle *competition* join (stricter than a plain dataset); unofficial GitHub mirrors exist but weren't verified complete/correct and raise ToS questions about rehosting competition data.
- **OpenICPSR** (Billion Prices Project, markup/price-comparison papers) — landing pages return `403` to direct fetch; requires a free account for any download, same as Kaggle.

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
  direction of an effect usually travels; the exact numbers don't — which is
  what the other-market benchmarks are for.

Categories are assigned by keyword rules against the free-text product description,
because the source data ships no category field. A category is only reported once
it clears 500 weekly observations across at least 15 products.

## Tests

```
pytest                         # everything
pytest tests/test_api.py       # API contract only, no browser needed
pytest tests/test_panel_fit.py # the estimators, against known answers
pytest tests/test_rls.py       # row-level security, by result set
```

The account tests need more than Python, and skip cleanly without it:

- `tests/test_rls.py` runs the migration on a throwaway local Postgres and
  checks every policy by what each role actually gets back — an UPDATE with
  no SELECT policy "succeeds" on zero rows, so no test here trusts the
  absence of an error. It runs twice, under Supabase's current no-auto-grant
  default and the old grant-everything one, and was mutation-tested:
  loosening any read policy, letting members upload, or re-granting the
  `status` column each turns it red.
- `tests/test_account_e2e.py` signs up, confirms, onboards and uploads through
  the real app against real PostgREST, with both key styles. Two synthetic
  businesses (`tests/synthetic_sales.py`, known elasticities) must come back
  with different, correct answers, and a second account's real token must
  get nothing back from any tenant table.
- `tests/test_insights.py` holds the validator to its promise, and the
  template to the validator across random inputs.
- `tests/test_dashboard_browser.py` drives onboarding, the mapping step and
  number tracing in Chromium, and every dashboard page at 360px.

`tests/test_panel_fit.py` checks each estimator against simulated data with a
coefficient chosen in advance — including a dataset built so that OLS is
knowably wrong, where the 2SLS implementation has to recover the true value
that OLS misses. A quietly broken IV implementation still returns
plausible-looking numbers; it just returns the biased ones.

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
`pyproject.toml`, and installs from its `[project] dependencies` — not from
`requirements.txt`. numpy and pandas are there for uploads, but imported only
when a file arrives, so the public page's cold start doesn't pay for them
(a test checks). `.python-version` pins 3.12. Everything the page
needs is inlined or served from the same origin, so there is no build step and no
static asset pipeline.

Set `PEP_DEV_RELOAD=1` locally to re-read `src/web/*` on every request instead of
caching them at startup.

---

A research and portfolio project built on public data. It is not pricing advice.
