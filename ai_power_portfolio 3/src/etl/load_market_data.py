"""
Load step of the ETL pipeline: takes fetched OHLCV data and loads it into
the warehouse's dim_date, dim_asset, and fact_market_price tables.

Usage:
    python -m src.etl.load_market_data
"""
import sqlite3
from datetime import date, timedelta

import pandas as pd

from src.config.settings import WAREHOUSE_DB_PATH, TICKER_UNIVERSE, DEFAULT_LOOKBACK_PERIOD, DEFAULT_INTERVAL
from src.etl.fetch_market_data import fetch_all


def _date_key(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def upsert_dim_assets(conn: sqlite3.Connection) -> dict:
    """Ensure every ticker in TICKER_UNIVERSE exists in dim_asset. Returns {ticker: asset_key}."""
    cur = conn.cursor()
    for ticker, name, asset_class in TICKER_UNIVERSE:
        cur.execute(
            """
            INSERT INTO dim_asset (ticker, asset_name, asset_class)
            VALUES (?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET asset_name = excluded.asset_name
            """,
            (ticker, name, asset_class),
        )
    conn.commit()

    cur.execute("SELECT ticker, asset_key FROM dim_asset")
    return dict(cur.fetchall())


def upsert_dim_dates(conn: sqlite3.Connection, dates: pd.Series) -> None:
    """Ensure every date present in the fetched data exists in dim_date."""
    cur = conn.cursor()
    unique_dates = sorted(set(dates))
    for d in unique_dates:
        d = pd.Timestamp(d).date()
        cur.execute(
            """
            INSERT INTO dim_date (date_key, full_date, day, month, quarter, year, day_of_week, is_trading_day)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(date_key) DO NOTHING
            """,
            (
                _date_key(d),
                d.isoformat(),
                d.day,
                d.month,
                (d.month - 1) // 3 + 1,
                d.year,
                d.strftime("%A"),
            ),
        )
    conn.commit()


def load_fact_market_price(conn: sqlite3.Connection, df: pd.DataFrame, asset_key: int) -> int:
    """Upsert one ticker's OHLCV rows into fact_market_price. Returns rows written."""
    cur = conn.cursor()
    rows_written = 0
    for _, row in df.iterrows():
        cur.execute(
            """
            INSERT INTO fact_market_price
                (date_key, asset_key, open, high, low, close, adj_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date_key, asset_key) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                adj_close = excluded.adj_close,
                volume = excluded.volume
            """,
            (
                _date_key(row["date"]),
                asset_key,
                float(row["open"]) if pd.notna(row["open"]) else None,
                float(row["high"]) if pd.notna(row["high"]) else None,
                float(row["low"]) if pd.notna(row["low"]) else None,
                float(row["close"]) if pd.notna(row["close"]) else None,
                float(row["adj_close"]) if pd.notna(row["adj_close"]) else None,
                int(row["volume"]) if pd.notna(row["volume"]) else None,
            ),
        )
        rows_written += 1
    conn.commit()
    return rows_written


def run(period: str = DEFAULT_LOOKBACK_PERIOD, interval: str = DEFAULT_INTERVAL) -> None:
    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    try:
        asset_key_by_ticker = upsert_dim_assets(conn)

        fetched = fetch_all(period=period, interval=interval)

        total_rows = 0
        for ticker, df in fetched.items():
            if df.empty:
                continue
            upsert_dim_dates(conn, df["date"])
            rows = load_fact_market_price(conn, df, asset_key_by_ticker[ticker])
            total_rows += rows
            print(f"[load] {ticker}: {rows} rows loaded")

        print(f"[load] done. {total_rows} total fact_market_price rows upserted.")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
