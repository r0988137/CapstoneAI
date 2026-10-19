"""
Week 4 — Data quality checks on fact_market_price.

Three checks, run against whatever is currently in the warehouse:
  1. Missing trading days   — a date where most other assets have a price
                               but a given asset doesn't (likely a gap in
                               the ETL pull, not a real market holiday).
  2. Null / zero prices     — rows where close is missing or <= 0.
  3. Price outliers         — day-over-day % change bigger than a threshold
                               (crypto gets a wider threshold than the rest,
                               since >20% daily moves are routine for it).

Usage:
    python -m src.etl.validate_market_data
"""
import argparse
import sqlite3
from dataclasses import dataclass, field

from src.config.settings import WAREHOUSE_DB_PATH

OUTLIER_THRESHOLD_DEFAULT = 0.20   # 20% day-over-day move
OUTLIER_THRESHOLD_CRYPTO = 0.35    # crypto is more volatile day-to-day


@dataclass
class ValidationReport:
    missing_dates: list = field(default_factory=list)      # [(ticker, full_date)]
    null_or_zero_prices: list = field(default_factory=list)  # [(ticker, full_date, close)]
    outliers: list = field(default_factory=list)             # [(ticker, full_date, pct_change)]

    @property
    def issue_count(self) -> int:
        return len(self.missing_dates) + len(self.null_or_zero_prices) + len(self.outliers)

    def summary(self) -> str:
        lines = [
            "=== Data Quality Report ===",
            f"Missing trading days : {len(self.missing_dates)}",
            f"Null/zero prices     : {len(self.null_or_zero_prices)}",
            f"Price outliers       : {len(self.outliers)}",
            f"Total issues         : {self.issue_count}",
        ]
        if self.missing_dates:
            lines.append("\nMissing dates (ticker, date) — first 20:")
            lines += [f"  {t}  {d}" for t, d in self.missing_dates[:20]]
        if self.null_or_zero_prices:
            lines.append("\nNull/zero prices (ticker, date, close) — first 20:")
            lines += [f"  {t}  {d}  close={c}" for t, d, c in self.null_or_zero_prices[:20]]
        if self.outliers:
            lines.append("\nOutliers (ticker, date, % change from prior day) — first 20:")
            lines += [f"  {t}  {d}  {p:+.1%}" for t, d, p in self.outliers[:20]]
        return "\n".join(lines)


def check_missing_dates(conn: sqlite3.Connection) -> list:
    """
    A date counts as a "trading day" if at least half of the tracked assets
    have a price row for it. Any asset missing a row on such a date is
    flagged. This avoids needing an external market-calendar dependency —
    it just uses the other assets in the warehouse as a reference.
    """
    cur = conn.cursor()
    # Use the count of assets that actually HAVE price data, not the count of
    # tickers configured in dim_asset — dim_asset gets a row for every ticker
    # in the universe as soon as the ETL upserts assets, before any prices
    # are ever pulled, so using it as the denominator would demand quorum
    # from tickers that haven't been fetched yet and never reach it.
    cur.execute("SELECT COUNT(DISTINCT asset_key) FROM fact_market_price")
    total_assets = cur.fetchone()[0]
    if total_assets == 0:
        return []

    cur.execute("""
        SELECT d.full_date, COUNT(DISTINCT f.asset_key) AS assets_present
        FROM fact_market_price f
        JOIN dim_date d ON d.date_key = f.date_key
        GROUP BY d.full_date
        HAVING assets_present >= ?
        ORDER BY d.full_date
    """, (max(1, total_assets // 2),))
    trading_dates = [row[0] for row in cur.fetchall()]
    if not trading_dates:
        return []

    # Only check assets that have at least one price row somewhere — a ticker
    # that has never been successfully fetched (e.g. still failing at the
    # source) isn't a "missing date" issue, it's a "never loaded" issue,
    # and flagging it on every single date would just be noise.
    cur.execute("""
        SELECT DISTINCT a.asset_key, a.ticker
        FROM dim_asset a
        JOIN fact_market_price f ON f.asset_key = a.asset_key
    """)
    assets = cur.fetchall()

    missing = []
    for asset_key, ticker in assets:
        cur.execute("""
            SELECT d.full_date FROM fact_market_price f
            JOIN dim_date d ON d.date_key = f.date_key
            WHERE f.asset_key = ?
        """, (asset_key,))
        present = {row[0] for row in cur.fetchall()}
        for full_date in trading_dates:
            if full_date not in present:
                missing.append((ticker, full_date))
    return missing


def check_null_or_zero_prices(conn: sqlite3.Connection) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT a.ticker, d.full_date, f.close
        FROM fact_market_price f
        JOIN dim_asset a ON a.asset_key = f.asset_key
        JOIN dim_date d ON d.date_key = f.date_key
        WHERE f.close IS NULL OR f.close <= 0
        ORDER BY a.ticker, d.full_date
    """)
    return cur.fetchall()


def check_price_outliers(conn: sqlite3.Connection) -> list:
    cur = conn.cursor()
    cur.execute("SELECT asset_key, ticker, asset_class FROM dim_asset")
    assets = cur.fetchall()

    outliers = []
    for asset_key, ticker, asset_class in assets:
        threshold = OUTLIER_THRESHOLD_CRYPTO if asset_class == "crypto" else OUTLIER_THRESHOLD_DEFAULT
        cur.execute("""
            SELECT d.full_date, f.close
            FROM fact_market_price f
            JOIN dim_date d ON d.date_key = f.date_key
            WHERE f.asset_key = ? AND f.close IS NOT NULL AND f.close > 0
            ORDER BY d.full_date
        """, (asset_key,))
        rows = cur.fetchall()
        for i in range(1, len(rows)):
            prev_date, prev_close = rows[i - 1]
            cur_date, cur_close = rows[i]
            pct_change = (cur_close - prev_close) / prev_close
            if abs(pct_change) > threshold:
                outliers.append((ticker, cur_date, pct_change))
    return outliers


def run_validation(conn: sqlite3.Connection) -> ValidationReport:
    return ValidationReport(
        missing_dates=check_missing_dates(conn),
        null_or_zero_prices=check_null_or_zero_prices(conn),
        outliers=check_price_outliers(conn),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data quality checks on fact_market_price.")
    parser.add_argument("--out", default=None, help="Optional path to write the report as text.")
    args = parser.parse_args()

    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    try:
        report = run_validation(conn)
    finally:
        conn.close()

    print(report.summary())
    if args.out:
        with open(args.out, "w") as f:
            f.write(report.summary())
        print(f"\nReport written to {args.out}")
