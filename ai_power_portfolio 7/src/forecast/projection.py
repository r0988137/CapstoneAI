"""
Week 10 - scenario-based forecasting.

For a saved profile + its recommended allocation, projects the portfolio value
year by year under three scenarios (conservative / expected / optimistic),
supporting a lump sum plus optional monthly contributions.

Method (kept simple on purpose, all assumptions stated):
  1. Per-asset expected return = 50% its own historical annualized return from
     fact_market_price + 50% a long-run assumption (below). Blending stops a
     recent hot streak (e.g. crypto) from being extrapolated for decades. An
     asset with too little history uses the assumption alone.
  2. Portfolio expected return = weighted sum of asset returns.
  3. Portfolio volatility = 50% historical (from the weighted daily portfolio
     return series, when every holding has enough history) + 50% assumption-based
     (assumed volatilities with a flat 0.6 correlation between risky assets).
  4. "Expected" compounds at the expected annual return (mu). The other scenarios
     shift it: annualized return at horizon t years = mu + z * sigma / sqrt(t), with
     z = -1.2816 / 0 / +1.2816 (roughly the 10th / 50th / 90th percentile band), so
     the range is wide for short horizons and narrows as the horizon grows, instead
     of being a fixed good-year/bad-year rate. (This is a simplification: it ignores
     the small "volatility drag" that makes real median outcomes a bit lower than mu.)
  5. Value at year t = lump_sum * (1+r)^t + monthly contributions (end of month)
     compounded at the same rate.

These are illustrative estimates, not predictions or guarantees.
"""
import math
import sqlite3
from typing import Dict, Optional

import numpy as np
import pandas as pd

from src.questionnaire.store import get_profile

CASH_TICKER = "CASH"
MIN_OBSERVATIONS = 120          # trading days of history needed to trust historical stats
HISTORY_WEIGHT = 0.5            # blend between history and long-run assumption
FLAT_CORRELATION = 0.6          # assumed correlation between risky assets
MIN_ANNUAL_RETURN = -0.5        # floor so extreme short-horizon cases stay sane

# ticker: (annual return, annual volatility) - rough long-run planning assumptions.
# Per-ticker (not per asset_class) because BND is stored as 'equity_etf' in dim_asset.
ASSUMPTIONS = {
    "VTI": (0.07, 0.16), "VXUS": (0.06, 0.17), "BND": (0.035, 0.06), "QQQ": (0.08, 0.22),
    "BTC-USD": (0.10, 0.65), "ETH-USD": (0.10, 0.75), "GLD": (0.04, 0.15), "SLV": (0.04, 0.28),
    CASH_TICKER: (0.03, 0.0),
}
DEFAULT_ASSUMPTION = (0.06, 0.20)

SCENARIOS = {"conservative": -1.2816, "expected": 0.0, "optimistic": 1.2816}


def load_price_history(conn: sqlite3.Connection, tickers) -> pd.DataFrame:
    """Daily adjusted closes, one column per ticker, indexed by date."""
    frames = {}
    for t in tickers:
        rows = conn.execute(
            """
            SELECT d.full_date, COALESCE(f.adj_close, f.close)
            FROM fact_market_price f
            JOIN dim_asset a ON a.asset_key = f.asset_key
            JOIN dim_date d ON d.date_key = f.date_key
            WHERE a.ticker = ? AND COALESCE(f.adj_close, f.close) > 0
            ORDER BY d.full_date
            """,
            (t,),
        ).fetchall()
        if rows:
            frames[t] = pd.Series({r[0]: r[1] for r in rows})
    return pd.DataFrame(frames)


def _periods_per_year(conn, ticker) -> int:
    row = conn.execute("SELECT asset_class FROM dim_asset WHERE ticker = ?", (ticker,)).fetchone()
    return 365 if row and row[0] == "crypto" else 252


def _assumed_portfolio_vol(weights: Dict[str, float]) -> float:
    risky = {t: w for t, w in weights.items() if t != CASH_TICKER}
    total = 0.0
    for ti, wi in risky.items():
        for tj, wj in risky.items():
            rho = 1.0 if ti == tj else FLAT_CORRELATION
            total += wi * wj * ASSUMPTIONS.get(ti, DEFAULT_ASSUMPTION)[1] * ASSUMPTIONS.get(tj, DEFAULT_ASSUMPTION)[1] * rho
    return math.sqrt(total)


def estimate_portfolio_stats(conn: sqlite3.Connection, allocation_pct: Dict[str, float]) -> dict:
    """Returns {'mu', 'sigma', 'data_source'} for a {ticker: percent} allocation."""
    weights = {t: p / 100 for t, p in allocation_pct.items() if p > 0}
    risky = [t for t in weights if t != CASH_TICKER]
    prices = load_price_history(conn, risky) if risky else pd.DataFrame()

    # 1-2. expected return
    mu = 0.0
    used_history = False
    for t, w in weights.items():
        assumed_mu = ASSUMPTIONS.get(t, DEFAULT_ASSUMPTION)[0]
        asset_mu = assumed_mu
        if t != CASH_TICKER and t in prices and prices[t].dropna().shape[0] > MIN_OBSERVATIONS:
            series = prices[t].dropna()
            daily = series.pct_change().dropna()
            hist_mu = daily.mean() * _periods_per_year(conn, t)
            asset_mu = HISTORY_WEIGHT * hist_mu + (1 - HISTORY_WEIGHT) * assumed_mu
            used_history = True
        mu += w * asset_mu

    # 3. volatility
    assumed_sigma = _assumed_portfolio_vol(weights)
    sigma = assumed_sigma
    aligned = prices.dropna() if not prices.empty and all(t in prices for t in risky) else pd.DataFrame()
    if not aligned.empty and aligned.shape[0] > MIN_OBSERVATIONS:
        rets = aligned.pct_change().dropna()
        port = sum(weights[t] * rets[t] for t in risky)
        hist_sigma = float(port.std() * math.sqrt(252))
        sigma = HISTORY_WEIGHT * hist_sigma + (1 - HISTORY_WEIGHT) * assumed_sigma

    return {
        "mu": float(mu),
        "sigma": float(sigma),
        "data_source": "historical + assumptions" if used_history else "assumptions only",
    }


def project_value(lump_sum: float, monthly: float, annual_return: float, years: int) -> float:
    """Future value after `years`, contributions at end of each month."""
    value = lump_sum * (1 + annual_return) ** years
    i = (1 + annual_return) ** (1 / 12) - 1
    n = 12 * years
    annuity = n if abs(i) < 1e-12 else ((1 + i) ** n - 1) / i
    return value + monthly * annuity


def build_forecast(lump_sum: float, monthly: float, horizon_years: int, mu: float, sigma: float) -> list:
    """Rows of {scenario, horizon_year, projected_value, annual_return, total_contributed}."""
    rows = []
    for scenario, z in SCENARIOS.items():
        for t in range(1, horizon_years + 1):
            r = max(mu + z * sigma / math.sqrt(t), MIN_ANNUAL_RETURN)
            rows.append({
                "scenario": scenario,
                "horizon_year": t,
                "projected_value": round(project_value(lump_sum, monthly, r, t), 2),
                "annual_return": r,
                "total_contributed": round(lump_sum + monthly * 12 * t, 2),
            })
    return rows


def forecast_and_save(conn: sqlite3.Connection, user_profile_key: int) -> dict:
    """
    Reads the saved recommendation for a profile, builds the three scenarios over the
    profile's time horizon, and writes them to fact_forecast (replacing earlier rows).
    """
    profile = get_profile(conn, user_profile_key)
    alloc = {
        t: pct for t, pct in conn.execute(
            "SELECT a.ticker, r.allocation_pct FROM fact_recommendation r "
            "JOIN dim_asset a ON a.asset_key = r.asset_key WHERE r.user_profile_key = ?",
            (user_profile_key,),
        )
    }
    if not alloc:
        raise ValueError("No recommendation saved for this profile - run the portfolio recommendation first.")

    stats = estimate_portfolio_stats(conn, alloc)
    rows = build_forecast(profile["investment_amount"], profile["monthly_contribution"],
                          profile["time_horizon_years"], stats["mu"], stats["sigma"])

    scenario_keys = dict(conn.execute("SELECT scenario_name, scenario_key FROM dim_scenario").fetchall())
    conn.execute("DELETE FROM fact_forecast WHERE user_profile_key = ?", (user_profile_key,))
    for r in rows:
        conn.execute(
            "INSERT INTO fact_forecast (user_profile_key, scenario_key, horizon_year, projected_value, assumed_annual_return) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_profile_key, scenario_keys[r["scenario"]], r["horizon_year"], r["projected_value"], r["annual_return"]),
        )
    conn.commit()
    return {"stats": stats, "rows": rows}


def final_year_summary(rows: list) -> Dict[str, float]:
    """{scenario: projected value at the last horizon year} - handy for printing."""
    last = max(r["horizon_year"] for r in rows)
    return {r["scenario"]: r["projected_value"] for r in rows if r["horizon_year"] == last}
