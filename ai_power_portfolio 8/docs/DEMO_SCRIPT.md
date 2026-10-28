# Final Demo Script (about 8 minutes)

**Before you start (5 minutes earlier):** open the Colab notebook, run the clone, Drive and ETL cells so the
database has prices, then run the last cell and keep the app link open. Optional: add
`ANTHROPIC_API_KEY` in Colab Secrets so the explanations come from the AI.

| Time | What to show | What to say |
|---|---|---|
| 0:00 | Title slide / README | The problem: people don't know their risk profile or how an investment could grow. Our prototype guides them from questionnaire to forecast. |
| 0:45 | Architecture (docs/ARCHITECTURE.md data flow) | Six steps, one star-schema warehouse, Python ETL from Yahoo Finance, optional LLM for explanations. |
| 1:30 | Dashboard tab | Real market data loaded by the ETL: returns by asset, price comparison. Mention the data-quality checks. |
| 2:30 | Tab 1: fill the form as a **Growth** investor ($10,000, 10 years, $200/month, risk 4, reaction 4, goal growth) | These are the questions from the proposal. |
| 3:30 | Results: profile + explanation + "why this portfolio" | Score, profile, plain-language reasons. Point out the source label (AI or template). |
| 4:30 | Pie + table, forecast chart | Diversified across stocks, bonds, crypto, gold/silver, cash. Three scenarios; the dotted line is the money put in. Range narrows over time. |
| 5:30 | News section | Headlines for the biggest holdings; the AI says why they matter. |
| 6:00 | Run a 2nd user: **Conservative**, 2 years, goal preservation | Crypto disappears (short-horizon rule), more bonds and cash, lower forecast range. Shows the engine reacts to the answers. |
| 6:45 | Try an invalid input (horizon 500) | Friendly message and nothing is saved: Week 13 edge-case handling. |
| 7:15 | Dashboard again | Both users are stored with inputs and outputs: the stored history from the proposal. |
| 7:45 | Limitations + next steps | Educational only; fixed model portfolios; next: hosted database, richer models, real-time data. |

## If something goes wrong
- **News unavailable:** say it times out safely; the rest still works (untick "Include market news").
- **App link lost:** re-run the last cell for a new link.
- **No internet for Yahoo:** the app still works with built-in assumptions; the dashboard shows what is already in the database.
