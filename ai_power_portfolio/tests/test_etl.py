"""
Unit tests for the ETL pipeline. These use an in-memory SQLite DB and a
hand-built DataFrame instead of hitting the network, so they run anywhere.
"""
import sqlite3
from datetime import date

import pandas as pd
import pytest

from src.config.settings import SCHEMA_SQL_PATH
from src.etl.load_market_data import upsert_dim_assets, upsert_dim_dates, load_fact_market_price


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA_SQL_PATH.read_text())
    yield connection
    connection.close()


def make_fake_ohlcv(ticker: str) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [date(2026, 1, 2), date(2026, 1, 3)],
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "adj_close": [101.0, 102.0],
        "volume": [1_000_000, 1_200_000],
        "ticker": [ticker, ticker],
    })


def test_upsert_dim_assets_creates_all_configured_tickers(conn):
    asset_keys = upsert_dim_assets(conn)
    assert "VTI" in asset_keys
    assert "BTC-USD" in asset_keys
    assert all(isinstance(k, int) for k in asset_keys.values())


def test_upsert_dim_assets_is_idempotent(conn):
    first = upsert_dim_assets(conn)
    second = upsert_dim_assets(conn)
    assert first == second  # same keys on re-run, no duplicates


def test_upsert_dim_dates_inserts_expected_rows(conn):
    dates = pd.Series([date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 2)])  # dup on purpose
    upsert_dim_dates(conn, dates)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dim_date")
    assert cur.fetchone()[0] == 2  # duplicate collapsed


def test_load_fact_market_price_round_trip(conn):
    asset_keys = upsert_dim_assets(conn)
    df = make_fake_ohlcv("VTI")
    upsert_dim_dates(conn, df["date"])

    rows_written = load_fact_market_price(conn, df, asset_keys["VTI"])
    assert rows_written == 2

    cur = conn.cursor()
    cur.execute("SELECT close FROM fact_market_price ORDER BY date_key")
    closes = [r[0] for r in cur.fetchall()]
    assert closes == [101.0, 102.0]


def test_load_fact_market_price_upsert_updates_existing_row(conn):
    asset_keys = upsert_dim_assets(conn)
    df = make_fake_ohlcv("VTI")
    upsert_dim_dates(conn, df["date"])
    load_fact_market_price(conn, df, asset_keys["VTI"])

    # Re-load with a changed close price for the same (date, asset) — should update, not duplicate.
    df.loc[0, "close"] = 999.0
    load_fact_market_price(conn, df, asset_keys["VTI"])

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fact_market_price")
    assert cur.fetchone()[0] == 2  # still 2 rows, not 4

    cur.execute("SELECT close FROM fact_market_price ORDER BY date_key LIMIT 1")
    assert cur.fetchone()[0] == 999.0
