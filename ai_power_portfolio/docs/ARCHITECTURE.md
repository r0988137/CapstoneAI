# Architecture and Method

## Data flow

```
Questionnaire (form / CLI)
   -> validate_answers            src/questionnaire/schema.py
   -> risk score + profile        src/profiling/risk_scoring.py   -> fact_user_profile
   -> AI explanation              src/ai/explain_profile.py       -> fact_user_profile.ai_explanation
   -> model portfolio             src/portfolio/allocation.py     -> fact_recommendation
   -> "why this portfolio"        src/portfolio/rationale.py
   -> market news + context       src/news/market_news.py         (shown, not stored)
   -> scenario forecast           src/forecast/projection.py      -> fact_forecast
Everything chained by src/workflow/run_workflow.py; shown by src/app/ (Gradio).
Prices:  Yahoo Finance -> src/etl/ -> fact_market_price (read by forecast + dashboard).
```

## Data warehouse
Star schema in SQLite (see `star_schema.md`): 5 dimensions (date, asset, user,
profile type, scenario) and 4 facts (market price, user profile, recommendation,
forecast). Inputs and outputs of every run are stored, so the history can be analysed.

## Risk profiling
Weighted average of four inputs, rescaled to 0-100: risk tolerance 30%, reaction to a
10-20% loss 30%, time horizon 25%, main goal 15%. Thresholds: <25 Conservative,
<50 Moderate, <75 Growth, otherwise Aggressive. Amount and monthly contribution do
not affect the score (they are used by the forecast).

## Portfolio engine
A fixed, transparent model portfolio per profile (not an optimizer), in percent. The 13 assets and their
planning assumptions live in one place, `ASSET_CATALOG` in `src/config/settings.py`; the ETL, portfolios,
forecast, explanations and charts all read from it.

| Asset | Conservative | Moderate | Growth | Aggressive |
|---|---|---|---|---|
| VTI (U.S. stocks) | 10 | 22 | 28 | 28 |
| QQQ (U.S. stocks) | 0 | 5 | 15 | 28 |
| SCHD (U.S. stocks) | 8 | 8 | 5 | 0 |
| VXUS (International stocks) | 4 | 7 | 10 | 10 |
| VWO (International stocks) | 0 | 3 | 5 | 6 |
| BND (Bonds) | 30 | 22 | 11 | 0 |
| VTIP (Bonds) | 8 | 6 | 2 | 0 |
| SHV (Bonds) | 12 | 5 | 0 | 0 |
| VNQ (Real estate) | 3 | 4 | 4 | 3 |
| BTC-USD (Crypto) | 0 | 2 | 5 | 12 |
| ETH-USD (Crypto) | 0 | 0 | 2 | 5 |
| GLD (Gold / silver) | 10 | 8 | 6 | 4 |
| SLV (Gold / silver) | 0 | 0 | 1 | 1 |
| CASH (Cash) | 15 | 8 | 6 | 3 |

**Short-horizon rule:** under 3 years, crypto moves to cash and QQQ is halved into bonds.

## Forecast method
- Expected return per asset = 50% its own price history + 50% a long-run assumption
  (so a recent hot streak is not extrapolated for decades). Assets with under 120 days
  of data use the assumption only.
- Portfolio volatility = 50% historical + 50% assumption-based (flat 0.6 correlation).
- "Expected" compounds at the expected return. Conservative / optimistic shift it by
  -/+1.28 x volatility / sqrt(years) (roughly the 10th / 90th percentile band), so the
  range is wide early and narrows with time.
- Monthly contributions are added at the end of each month.

## AI usage
An optional Anthropic model writes the profile explanation, the portfolio rationale and
news summaries. It is given the exact numbers. With no key, or on any failure, a
deterministic template is used, so the app never breaks. Each result records its
`source` (`llm`, `template`, `headlines-only`).

## Quality checks
154 automated tests (`pytest tests`): ETL, data validation, scoring, allocation,
forecast math, news parsing, form handling, charts, dashboard queries, the web
handlers end to end, and a sweep of all 700 questionnaire combinations. Week 13 added
limits on inputs (no nan/inf/booleans, amount <= $1B, horizon <= 60 years), a time-out
for slow news requests, and tests for partial or bad price data.

## Limitations (be upfront in the demo)
- Educational prototype: no trades, not financial advice, forecasts are illustrative.
- Model portfolios are fixed rules; no personalised optimisation or tax/fee modelling.
- Forecast assumptions are simple (no regime changes, flat correlation, no inflation).
- News is shown but not stored; summaries depend on an optional API key.
- BND is stored as `equity_etf` because the schema has no bond class; the forecast uses
  per-ticker assumptions, so results are not affected.
- Needs internet for Yahoo Finance (prices and news). SQLite is single-user; a hosted
  database would be the next step for real use.
