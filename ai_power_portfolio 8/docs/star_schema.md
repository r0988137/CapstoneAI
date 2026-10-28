# Star Schema — Design Notes

## Dimensions

| Table | Purpose |
|---|---|
| `dim_date` | Standard date dimension (day/month/quarter/year, trading-day flag) |
| `dim_asset` | One row per tradeable instrument (ticker, asset class, currency) |
| `dim_user` | One row per user/session — kept minimal, no PII by design |
| `dim_investor_profile_type` | The 4 fixed investor categories (seeded) |
| `dim_scenario` | The 3 fixed forecast scenarios (seeded) |

## Facts

| Table | Grain | Populated in |
|---|---|---|
| `fact_market_price` | one row per (asset, date) | Week 3 (loaded), Week 4 (validated) |
| `fact_user_profile` | one row per completed questionnaire | Weeks 5–7 (answers, score, AI explanation) |
| `fact_recommendation` | one row per (profile, asset) allocation line | Week 8 |
| `fact_forecast` | one row per (profile, scenario, horizon_year) | Week 10 |

## Why this shape

- **Star, not snowflake** — dimensions are denormalized (e.g. `dim_asset`
  carries `asset_class` directly rather than a separate lookup table). This
  keeps query joins simple for the eventual BI dashboard (Weeks 11–12, built as a web dashboard).
- **`fact_user_profile` sits between two fact tables** — `fact_recommendation`
  and `fact_forecast` both reference `user_profile_key` rather than
  `user_key` directly, since a single user could in principle re-run the
  questionnaire and get a new profile over time. This makes "profile" the
  actual grain of a recommendation/forecast, which matches the workflow
  (Step 2 → Step 4 → Step 6 in the project description).
- **`ai_explanation` lives on `fact_user_profile`** rather than a separate
  table — it's a 1:1 attribute of a single profile record, not a repeating
  fact, so a separate table would just add a join for no benefit.
- **SQLite now, portable later** — no SQLite-only types are used beyond
  `AUTOINCREMENT`; switching the warehouse to Postgres/MySQL later should
  only require changing `init_db.py`'s connection logic, not the schema
  itself or any ETL/query code.

## Known simplifications (intentional, for a prototype)

- `dim_user` has no auth/PII — `external_id` is meant to be an anonymous
  session identifier.
- `is_trading_day` on `dim_date` currently defaults to 1 for every date
  inserted (only dates with actual price data get inserted by the ETL, so
  in practice every row *is* a trading day for now). A calendar-based
  dimension load can be added later if non-trading-day rows are needed.
