"""
Fetch step of the ETL pipeline: pulls historical OHLCV data for the
configured ticker universe using yfinance.

This module has no database dependency — it just returns clean DataFrames,
so it can be tested or reused independently of the loader.
"""
from typing import Dict
import pandas as pd
import yfinance as yf

from src.config.settings import TICKER_UNIVERSE, DEFAULT_LOOKBACK_PERIOD, DEFAULT_INTERVAL


def fetch_ticker_history(
    ticker: str,
    period: str = DEFAULT_LOOKBACK_PERIOD,
    interval: str = DEFAULT_INTERVAL,
) -> pd.DataFrame:
    """
    Fetch OHLCV history for a single ticker.

    Returns a DataFrame with columns:
        date, open, high, low, close, adj_close, volume, ticker
    Empty DataFrame (with the same columns) on failure, so callers can
    skip a bad ticker without crashing the whole run.
    """
    columns = ["date", "open", "high", "low", "close", "adj_close", "volume", "ticker"]
    try:
        raw = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    except Exception as e:
        print(f"[fetch] WARNING: failed to fetch {ticker}: {e}")
        return pd.DataFrame(columns=columns)

    if raw.empty:
        print(f"[fetch] WARNING: no data returned for {ticker}")
        return pd.DataFrame(columns=columns)

    raw = raw.reset_index()
    raw = raw.rename(columns={
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    })
    # Some tickers (e.g. crypto) don't return an Adj Close column.
    if "adj_close" not in raw.columns:
        raw["adj_close"] = raw["close"]

    raw["ticker"] = ticker
    raw["date"] = pd.to_datetime(raw["date"]).dt.tz_localize(None).dt.date
    return raw[columns]


def fetch_all(period: str = DEFAULT_LOOKBACK_PERIOD, interval: str = DEFAULT_INTERVAL) -> Dict[str, pd.DataFrame]:
    """Fetch history for every ticker in the configured universe."""
    results = {}
    for ticker, _name, _asset_class in TICKER_UNIVERSE:
        print(f"[fetch] pulling {ticker} ({period}, {interval}) ...")
        results[ticker] = fetch_ticker_history(ticker, period=period, interval=interval)
    return results


if __name__ == "__main__":
    data = fetch_all()
    for ticker, df in data.items():
        print(f"{ticker}: {len(df)} rows")
