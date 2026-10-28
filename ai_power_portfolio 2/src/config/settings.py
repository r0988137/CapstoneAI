"""
Central config for AI Power Portfolio.
Loads from .env if present; otherwise falls back to sensible defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE_DB_PATH = PROJECT_ROOT / os.getenv("WAREHOUSE_DB_PATH", "data/warehouse.db")
SCHEMA_SQL_PATH = PROJECT_ROOT / "src" / "db" / "schema.sql"

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

# Optional: only needed for the AI-written explanations/news summaries (Weeks 7 and 9).
# Without a key the project falls back to template text, so everything still runs.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

# ---------------------------------------------------------------------------
# ASSET CATALOG - the single place that defines what the system can recommend.
# To add an ETF: add one line here, give it a weight in a profile in
# src/portfolio/allocation.py (MODEL_PORTFOLIOS), and re-run the ETL.
# Everything else (database rows, forecast assumptions, explanations, charts) reads from here.
#
# fields: ticker, name, asset_class (must match the dim_asset CHECK), group (shown to the user),
#         annual return and volatility (long-run planning assumptions), why it is in the portfolio
# ---------------------------------------------------------------------------
ASSET_CATALOG = [
    # --- U.S. stocks
    dict(ticker="VTI", name="Vanguard Total Stock Market ETF", asset_class="equity_etf", group="U.S. stocks",
         ret=0.07, vol=0.16, why="Core holding: broad U.S. stock market exposure for long-term growth and diversification."),
    dict(ticker="QQQ", name="Invesco QQQ Trust", asset_class="equity_etf", group="U.S. stocks",
         ret=0.08, vol=0.22, why="Tilts toward large technology-oriented companies for higher growth potential (and higher swings)."),
    dict(ticker="SCHD", name="Schwab U.S. Dividend Equity ETF", asset_class="equity_etf", group="U.S. stocks",
         ret=0.065, vol=0.15, why="Quality U.S. companies that pay steady dividends, a calmer way to own stocks."),
    # --- International stocks
    dict(ticker="VXUS", name="Vanguard Total International Stock ETF", asset_class="equity_etf", group="International stocks",
         ret=0.06, vol=0.17, why="Adds international stocks so the portfolio isn't tied to the U.S. market alone."),
    dict(ticker="VWO", name="Vanguard FTSE Emerging Markets ETF", asset_class="equity_etf", group="International stocks",
         ret=0.07, vol=0.21, why="Emerging-market stocks add higher growth potential from developing economies, with bigger swings."),
    # --- Bonds and near-cash
    dict(ticker="BND", name="Vanguard Total Bond Market ETF", asset_class="equity_etf", group="Bonds",
         ret=0.035, vol=0.06, why="Bonds tend to move less than stocks, which helps cushion the portfolio in down markets."),
    dict(ticker="VTIP", name="Vanguard Short-Term Inflation-Protected Securities ETF", asset_class="equity_etf", group="Bonds",
         ret=0.032, vol=0.035, why="Short-term TIPS: bonds whose value adjusts with inflation, to protect buying power."),
    dict(ticker="SHV", name="iShares Short Treasury Bond ETF", asset_class="equity_etf", group="Bonds",
         ret=0.03, vol=0.005, why="Very short-term U.S. Treasuries: stable and easy to sell, like cash that earns interest."),
    # --- Real estate
    dict(ticker="VNQ", name="Vanguard Real Estate ETF", asset_class="equity_etf", group="Real estate",
         ret=0.06, vol=0.20, why="Real-estate companies add a different source of returns, including rental income."),
    # --- Crypto
    dict(ticker="BTC-USD", name="Bitcoin", asset_class="crypto", group="Crypto",
         ret=0.10, vol=0.65, why="Small higher-risk slice: Bitcoin is very volatile, so it is limited to what the profile can tolerate."),
    dict(ticker="ETH-USD", name="Ethereum", asset_class="crypto", group="Crypto",
         ret=0.10, vol=0.75, why="Small higher-risk slice: Ethereum adds crypto exposure with similarly large swings."),
    # --- Gold / silver
    dict(ticker="GLD", name="SPDR Gold Shares", asset_class="metal", group="Gold / silver",
         ret=0.04, vol=0.15, why="Gold is often used as a diversifier that does not always move with stocks."),
    dict(ticker="SLV", name="iShares Silver Trust", asset_class="metal", group="Gold / silver",
         ret=0.04, vol=0.28, why="Silver adds a small precious-metals position with more volatility than gold."),
]

CASH_TICKER = "CASH"
CASH_ASSET = dict(ticker=CASH_TICKER, name="Cash / money market", asset_class="cash", group="Cash",
                  ret=0.03, vol=0.0, why="Cash keeps part of the money stable and available, and reduces overall volatility.")

# The three views the rest of the code uses, all derived from the catalog above.
TICKER_UNIVERSE = [(a["ticker"], a["name"], a["asset_class"]) for a in ASSET_CATALOG]   # tickers the ETL downloads
ASSET_INFO = {a["ticker"]: a for a in ASSET_CATALOG + [CASH_ASSET]}
GROUP_ORDER = ["U.S. stocks", "International stocks", "Bonds", "Real estate", "Crypto", "Gold / silver", "Cash"]

# How much history to pull on each ETL run.
DEFAULT_LOOKBACK_PERIOD = "5y"   # yfinance period string
DEFAULT_INTERVAL = "1d"
