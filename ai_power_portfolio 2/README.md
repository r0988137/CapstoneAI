# AI Power Portfolio

Academic prototype of an AI-powered financial advisor: questionnaire → risk
profiling → portfolio recommendation → market news context → forecasting,
backed by a SQL star-schema data warehouse.

This repo covers the **full 14-week build**:

- Week 1 — repo/environment setup
- Week 2 — data warehouse design (star schema)
- Week 3 — ETL pipeline pulling historical price data from Yahoo Finance
- Week 4 — data quality validation on the loaded market data
- Week 5 — investor questionnaire (collects + validates answers)
- Week 6 — risk scoring/classification (Conservative/Moderate/Growth/Aggressive)
- Week 7 — AI explanation of the profile (Anthropic LLM, or built-in template if no key)
- Week 8 — portfolio engine (model portfolio per profile, saved to `fact_recommendation`)
- Week 9 — market news context for the recommended assets (yfinance headlines)
- Week 10 — scenario forecast (conservative / expected / optimistic, saved to `fact_forecast`)
- Weeks 11–12 — web app (Gradio): questionnaire form, results, and a dashboard
- Week 13 — integration testing and edge cases (stricter input validation, news time-outs, "why this portfolio" explanation)
- Week 14 — final documentation and demo materials (see `docs/`)

**Start here:** [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) (how to run and use it),
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (how it works, assumptions, limitations) and
[`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) (step-by-step final demo).

## Project layout

```
ai_power_portfolio/
├── README.md
├── requirements.txt
├── .env.example
├── src/
│   ├── config/
│   │   └── settings.py        # env vars, paths and ASSET_CATALOG (every ETF/asset the app can recommend)
│   ├── db/
│   │   ├── schema.sql          # star schema DDL (SQLite-compatible)
│   │   └── init_db.py          # creates warehouse.db from schema.sql
│   ├── etl/
│   │   ├── fetch_market_data.py     # pulls OHLCV history via yfinance
│   │   ├── load_market_data.py      # transforms + loads into the warehouse
│   │   └── validate_market_data.py  # Week 4: data quality checks
│   ├── questionnaire/
│   │   ├── schema.py           # Week 5: question definitions + validation
│   │   ├── collect.py          # Week 5: interactive input() collector
│   │   ├── store.py            # Weeks 5-6: validate + score + save to warehouse
│   │   └── run.py              # Weeks 5-6: CLI entrypoint
│   ├── profiling/
│   │   └── risk_scoring.py     # Week 6: risk score + profile classification
│   ├── ai/
│   │   ├── llm.py              # Week 7: optional Anthropic call (None on any failure)
│   │   └── explain_profile.py  # Week 7: LLM or template explanation
│   ├── portfolio/
│   │   ├── allocation.py       # Week 8: model portfolios + save recommendation
│   │   └── rationale.py        # Week 13: why this portfolio fits the user
│   ├── news/
│   │   └── market_news.py      # Week 9: headlines + relevance summary
│   ├── forecast/
│   │   └── projection.py       # Week 10: scenario projections
│   ├── workflow/
│   │   └── run_workflow.py
│   └── app/
│       ├── views.py            # Weeks 11-12: charts, tables, dashboard queries (testable)
│       └── app.py              # Weeks 11-12: the Gradio web app     # Weeks 5-10 chained: the one call the front-end will use
├── data/                        # warehouse.db lives here (gitignored)
├── tests/
│   ├── test_etl.py
│   ├── test_validate_market_data.py
│   ├── test_questionnaire.py
│   ├── test_risk_scoring.py
│   ├── test_explain_profile.py
│   ├── test_allocation.py
│   ├── test_market_news.py
│   ├── test_projection.py
│   ├── test_workflow.py
│   ├── test_app_views.py
│   └── test_edge_cases.py
└── docs/
    ├── star_schema.md           # schema explanation / ERD notes
    ├── USER_GUIDE.md            # how to run and use the app
    ├── ARCHITECTURE.md          # design, method, assumptions, limitations
    └── DEMO_SCRIPT.md           # final demo walkthrough
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # fill in ALPHA_VANTAGE_API_KEY if you'll use it later
```

## Run it

```bash
# 1. Create the warehouse (tables only, no data yet)
python -m src.db.init_db

# 2. Pull + load historical prices for the default ticker universe
python -m src.etl.load_market_data
```

This populates `data/warehouse.db` (SQLite) with `dim_date`, `dim_asset`, and
`fact_market_price` rows. `fact_recommendation` and `fact_forecast` stay empty
until the workflow (Weeks 8, 10) writes to them.

```bash
# 3. Check the loaded market data for gaps, bad prices, and outliers
python -m src.etl.validate_market_data

# 4. Run the investor questionnaire (prompts you interactively, then scores
#    and saves the result to fact_user_profile)
python -m src.questionnaire.run --user-id your-name

# 5. Weeks 7-10: full workflow (questionnaire -> profile -> AI explanation ->
#    portfolio -> news -> forecast). Add --no-news to skip the news step.
python -m src.workflow.run_workflow --user-id your-name

# 6. Weeks 11-12: web app (opens at http://127.0.0.1:7860)
python -m src.app.app
```

In Colab use the last cell of the notebook (`launch(share=True)`) and open the
public link it prints. Tab 1 is the questionnaire + results; tab 2 is the
dashboard (your recommended assets, market overview, saved questionnaires).

### Optional: AI explanations and news summaries

Without a key everything still works: the explanation uses a built-in template
and news shows plain headlines. To use the LLM, set `ANTHROPIC_API_KEY`
(in `.env`, or in Colab via the Secrets panel / `google.colab.userdata`).

### How the forecast works (assumptions)

Expected return per asset = 50% its own price history + 50% a long-run
assumption; volatility blended the same way. The three scenarios are the
expected path plus/minus a ~10th/90th percentile band that narrows as the
horizon grows. Monthly contributions are added at the end of each month.
These are illustrative estimates, not predictions.

## Why SQLite for now

SQLite keeps the prototype dependency-free and easy to demo. The schema is
plain ANSI SQL with no SQLite-only syntax beyond `AUTOINCREMENT`, so porting
to Postgres/MySQL later is a schema-only change — no ETL code changes needed.

## Notes on data source

The ETL defaults to `yfinance` (no API key required) for historical daily
OHLCV data. Alpha Vantage support is stubbed in `settings.py` for a future
switch if rate limits become an issue.

## Running in Google Colab

Open `notebooks/colab_quickstart.ipynb` in Colab (upload it, or open directly
from GitHub via File → Open notebook → GitHub tab). It:

1. Mounts your Google Drive so `warehouse.db` persists between sessions
   (Colab wipes local VM files when a runtime disconnects)
2. Clones this repo and installs `requirements.txt`
3. Points `WAREHOUSE_DB_PATH` at Drive instead of the ephemeral VM disk
4. Runs `src.db.init_db` and `src.etl.load_market_data`
5. Runs the test suite
6. Weeks 7–10: runs the full workflow (optional `ANTHROPIC_API_KEY` from Colab Secrets)

Update `REPO_URL` in the first code cell to point at your GitHub repo before
running.

## Running the ETL on GitHub Actions

`.github/workflows/etl.yml` runs the pipeline daily on GitHub's own runners
(which have normal outbound internet access — Yahoo Finance is reachable
from there). It also runs on every push that touches `src/etl/` or `src/db/`.

Note: GitHub Actions runners are ephemeral, so each run starts from an empty
`warehouse.db` — the workflow uploads the resulting file as a build artifact
(kept 7 days) rather than persisting it long-term. For real continuity, swap
the warehouse for a hosted database (Supabase/Neon Postgres) once you're past
the prototype stage, or have the workflow commit `data/warehouse.db` back to
the repo / push it to Drive.


## Version 8 - bigger ETF universe and a cleaner app
- **13 assets instead of 8.** New: SCHD (dividend stocks), VWO (emerging markets), VTIP (inflation-protected
  bonds), SHV (short-term Treasuries) and VNQ (real estate). They live in `ASSET_CATALOG` in
  `src/config/settings.py`.
- **To add another ETF:** add one entry to `ASSET_CATALOG`, give it a weight in `MODEL_PORTFOLIOS`
  (`src/portfolio/allocation.py`), and re-run the ETL. Tests check that every profile still sums to 100%.
- **New app layout:** summary cards, tabs for Profile / Portfolio / Forecast / Market context, a donut by asset
  type plus a bar per ETF, a shaded forecast range, one-click examples, and an Assets tab.
- **Tabs:** Get my portfolio, Dashboard (only *your* recommended assets), Market overview (every asset),
  Questionnaires saved (latest questionnaires + investor profiles chart), Assets. Performance tables show
  last price and 1D / 1M / 1Y / 5Y %.
- **Admin password** on the Questionnaires saved tab (`ADMIN_PASSWORD` in Colab Secrets or `.env`; never in the code).
  It is a simple lock for a prototype, not full security; see docs/USER_GUIDE.md.
- No database schema changes. 157 tests.
- The notebook's last cell now reloads the newest code and prints a clear message if the app cannot start.
