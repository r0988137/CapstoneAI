"""
Tests for the Week 4 data-quality checks. Uses an in-memory SQLite DB
seeded by hand so each check can be tested against a known-bad scenario.
"""
import sqlite3
from datetime import date

import pytest

from src.config.settings import SCHEMA_SQL_PATH
from src.etl.validate_market_data import (
    check_missing_dates,
    check_null_or_zero_prices,
    check_price_outliers,
    run_validation,
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA_SQL_PATH.read_text())
    yield connection
    connection.close()


def _insert_date(conn, d: date):
    date_key = int(d.strftime("%Y%m%d"))
    conn.execute(
        "INSERT OR IGNORE INTO dim_date (date_key, full_date, day, month, quarter, year, day_of_week, is_trading_day) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (date_key, d.isoformat(), d.day, d.month, (d.month - 1) // 3 + 1, d.year, d.strftime("%A")),
    )
    return date_key


def _insert_asset(conn, ticker, asset_class="equity_etf"):
    conn.execute("INSERT INTO dim_asset (ticker, asset_class) VALUES (?, ?)", (ticker, asset_class))
    return conn.execute("SELECT asset_key FROM dim_asset WHERE ticker = ?", (ticker,)).fetchone()[0]


def _insert_price(conn, date_key, asset_key, close):
    conn.execute(
        "INSERT INTO fact_market_price (date_key, asset_key, close) VALUES (?, ?, ?)",
        (date_key, asset_key, close),
    )


def test_check_missing_dates_flags_gap(conn):
    a1 = _insert_asset(conn, "AAA")
    a2 = _insert_asset(conn, "BBB")
    d1 = _insert_date(conn, date(2026, 1, 2))
    d2 = _insert_date(conn, date(2026, 1, 3))

    # AAA has both days, BBB is missing day 2 -> should be flagged
    _insert_price(conn, d1, a1, 100)
    _insert_price(conn, d2, a1, 101)
    _insert_price(conn, d1, a2, 50)
    conn.commit()

    missing = check_missing_dates(conn)
    assert ("BBB", "2026-01-03") in missing
    assert ("AAA", "2026-01-02") not in missing


def test_check_null_or_zero_prices(conn):
    a1 = _insert_asset(conn, "AAA")
    d1 = _insert_date(conn, date(2026, 1, 2))
    _insert_price(conn, d1, a1, 0)
    conn.commit()

    bad = check_null_or_zero_prices(conn)
    assert len(bad) == 1
    assert bad[0][0] == "AAA"
    assert bad[0][2] == 0


def test_check_price_outliers_flags_big_jump(conn):
    a1 = _insert_asset(conn, "AAA", asset_class="equity_etf")
    d1 = _insert_date(conn, date(2026, 1, 2))
    d2 = _insert_date(conn, date(2026, 1, 3))
    _insert_price(conn, d1, a1, 100)
    _insert_price(conn, d2, a1, 200)  # +100% day-over-day
    conn.commit()

    outliers = check_price_outliers(conn)
    assert len(outliers) == 1
    assert outliers[0][0] == "AAA"
    assert outliers[0][2] == pytest.approx(1.0)


def test_check_price_outliers_uses_wider_threshold_for_crypto(conn):
    a1 = _insert_asset(conn, "BTC-USD", asset_class="crypto")
    d1 = _insert_date(conn, date(2026, 1, 2))
    d2 = _insert_date(conn, date(2026, 1, 3))
    _insert_price(conn, d1, a1, 100)
    _insert_price(conn, d2, a1, 125)  # +25% — within crypto's 35% threshold
    conn.commit()

    outliers = check_price_outliers(conn)
    assert outliers == []


def test_run_validation_returns_combined_report(conn):
    a1 = _insert_asset(conn, "AAA")
    d1 = _insert_date(conn, date(2026, 1, 2))
    _insert_price(conn, d1, a1, 0)
    conn.commit()

    report = run_validation(conn)
    assert report.issue_count >= 1
    assert "Data Quality Report" in report.summary()
