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

# Default ticker universe covering each planned asset_class.
# Extend this list as the portfolio recommendation engine (Week 8) needs more coverage.
TICKER_UNIVERSE = [
    # ticker, asset_name, asset_class
    ("VTI",  "Vanguard Total Stock Market ETF", "equity_etf"),
    ("VXUS", "Vanguard Total International Stock ETF", "equity_etf"),
    ("BND",  "Vanguard Total Bond Market ETF", "equity_etf"),
    ("QQQ",  "Invesco QQQ Trust", "equity_etf"),
    ("BTC-USD", "Bitcoin", "crypto"),
    ("ETH-USD", "Ethereum", "crypto"),
    ("GLD",  "SPDR Gold Shares", "metal"),
    ("SLV",  "iShares Silver Trust", "metal"),
]

# How much history to pull on each ETL run.
DEFAULT_LOOKBACK_PERIOD = "5y"   # yfinance period string
DEFAULT_INTERVAL = "1d"
