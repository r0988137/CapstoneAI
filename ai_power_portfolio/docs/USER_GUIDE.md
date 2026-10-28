# User Guide

AI Power Portfolio is an educational prototype. It does not place trades and is
not financial advice.

## Option A - Google Colab (recommended)

1. Open `notebooks/colab_quickstart.ipynb` in Colab (File > Open notebook > GitHub tab > your repo).
2. Run the cells **one by one**, in order:
   - **Repo URL + clone cells:** download the project and install packages.
   - **Drive cell:** connects Google Drive so the database is saved between sessions (accept the permission pop-up).
   - **ETL cell:** creates the database and downloads 5 years of prices from Yahoo Finance (takes a few minutes).
   - **Data + validation cells:** look at the prices and run the data-quality checks.
   - **API key cell (optional):** loads your `ANTHROPIC_API_KEY` from Colab Secrets. Without it everything still works with built-in text templates.
   - **Questionnaire + workflow cell:** asks the questions in the cell and prints the full result as text.
   - **Forecast plot cell:** draws the three scenarios.
   - **Last cell:** launches the web app. Open the link that says **Running on public URL**.
3. Keep the Colab session open while you use the app.

## Option B - your own computer

```bash
pip install -r requirements.txt
python -m src.db.init_db
python -m src.etl.load_market_data      # downloads prices (needs internet)
python -m src.app.app                   # opens http://127.0.0.1:7860
```

## Using the web app

**Tab 1 - Get my portfolio.** Fill in the form and press the button.

| Field | Meaning |
|---|---|
| Your name | Any ID. Each submission is saved under it. |
| Initial investment | Starting amount in dollars (up to $1 billion). |
| Time horizon | Whole years, 1 to 60. |
| Monthly contribution | Extra money added each month (0 if none). |
| Risk comfort / reaction to a 10-20% drop | The two risk questions (1-5 scales). |
| Main goal | preservation, income, combination or growth. |
| Include market news | Fetches headlines; a bit slower. Untick for a faster run. |

You get: your investor profile and AI explanation, **why this portfolio** fits you,
the allocation (chart + table), a forecast chart with 3 scenarios, and market news.
If an input is invalid you get a message and nothing is saved.

**Tab 2 - Dashboard.** Performance of the assets in *your* recommended portfolio only: last price and the
% change over 1 day, 1 month, 1 year and 5 years (blank if we don't have that much history), plus a price
comparison chart. It fills in after you get a portfolio in tab 1.

**Tab 3 - Market overview.** The same table and chart for every asset in the program, with a picker to choose
which assets appear in the chart.

**Tab 4 - Questionnaires saved.** Every questionnaire stored in the warehouse (latest first) and the
Investor profiles chart. **Tab 5 - Assets** lists every ETF the advisor can recommend.

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named 'src.workflow'` in Colab | Files are missing in GitHub, or Colab has an old copy: Runtime > Disconnect and delete runtime, then run again from cell 1. |
| Dashboard or Market overview says "No market data loaded yet" | Run the ETL cell first. |
| News shows "unavailable" | Yahoo did not answer in time. The rest still works; try again. |
| Explanation says `template` | No API key set. This is normal and works the same. |
| Uploaded to GitHub from the website and a folder is missing | The website skips empty files; every package file in this repo contains a comment line so none are empty. |


## What changed in version 8
The results now appear in four tabs (Profile, Portfolio, Forecast, Market context) under three summary cards.
Use the example buttons under the form to fill it in with one click. The **Assets** tab lists every ETF the
advisor can recommend and the assumptions used for its forecast.
