"""
Week 8 - portfolio recommendation engine.

Maps an investor profile to a target allocation across the ticker universe
(+ cash), then adjusts for short time horizons. Allocations are fixed,
transparent rules (a "model portfolio" per profile, in the spirit of the
robo-advisors the proposal cites), not an optimizer - easy to explain and
to defend in the demo.

All allocations are in percent and always sum to 100.
"""
import sqlite3

from src.questionnaire.store import get_profile

from src.config.settings import ASSET_CATALOG, ASSET_INFO, CASH_ASSET, CASH_TICKER

# percent per ticker; each profile sums to 100. Tickers left out count as 0.
_RAW_PORTFOLIOS = {
    "Conservative": {"VTI": 10, "SCHD": 8, "VXUS": 4, "BND": 30, "VTIP": 8, "SHV": 12, "VNQ": 3, "GLD": 10, CASH_TICKER: 15},
    "Moderate":     {"VTI": 22, "SCHD": 8, "VXUS": 7, "VWO": 3, "QQQ": 5, "BND": 22, "VTIP": 6, "SHV": 5, "VNQ": 4,
                     "BTC-USD": 2, "GLD": 8, CASH_TICKER: 8},
    "Growth":       {"VTI": 28, "SCHD": 5, "VXUS": 10, "VWO": 5, "QQQ": 15, "BND": 11, "VTIP": 2, "VNQ": 4,
                     "BTC-USD": 5, "ETH-USD": 2, "GLD": 6, "SLV": 1, CASH_TICKER: 6},
    "Aggressive":   {"VTI": 28, "VXUS": 10, "VWO": 6, "QQQ": 28, "VNQ": 3, "BTC-USD": 12, "ETH-USD": 5,
                     "GLD": 4, "SLV": 1, CASH_TICKER: 3},
}
_ALL_TICKERS = [a["ticker"] for a in ASSET_CATALOG] + [CASH_TICKER]
MODEL_PORTFOLIOS = {name: {t: raw.get(t, 0) for t in _ALL_TICKERS} for name, raw in _RAW_PORTFOLIOS.items()}

SHORT_HORIZON_YEARS = 3

RATIONALE = {t: a["why"] for t, a in ASSET_INFO.items()}


def target_allocation(profile_name: str, time_horizon_years: int) -> dict:
    """Returns {ticker: percent} for a profile, adjusted for short horizons."""
    if profile_name not in MODEL_PORTFOLIOS:
        raise ValueError(f"Unknown profile '{profile_name}'")
    alloc = dict(MODEL_PORTFOLIOS[profile_name])

    if time_horizon_years < SHORT_HORIZON_YEARS:
        # Short horizon: not enough time to recover from a crash, so crypto goes to cash
        # and the tech tilt (QQQ) is halved, with the difference moved to bonds.
        crypto = alloc["BTC-USD"] + alloc["ETH-USD"]
        alloc["BTC-USD"] = alloc["ETH-USD"] = 0
        alloc[CASH_TICKER] += crypto
        moved = alloc["QQQ"] / 2
        alloc["QQQ"] -= moved
        alloc["BND"] += moved

    assert abs(sum(alloc.values()) - 100) < 1e-9, "allocation must sum to 100"
    return alloc


def _ensure_cash_asset(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO dim_asset (ticker, asset_name, asset_class, data_source)
        VALUES (?, 'Cash / money market', 'cash', 'none')
        ON CONFLICT(ticker) DO NOTHING
        """,
        (CASH_TICKER,),
    )
    conn.commit()


def _ensure_asset_rows(conn: sqlite3.Connection) -> dict:
    """Makes sure every ticker in the universe + CASH exists in dim_asset; returns {ticker: asset_key}."""
    from src.etl.load_market_data import upsert_dim_assets  # reuse the ETL's upsert
    upsert_dim_assets(conn)
    _ensure_cash_asset(conn)
    return dict(conn.execute("SELECT ticker, asset_key FROM dim_asset").fetchall())


def recommend_and_save(conn: sqlite3.Connection, user_profile_key: int) -> list:
    """
    Builds the allocation for a saved profile and writes it to fact_recommendation
    (replacing any earlier recommendation for that profile, so re-running is safe).
    Returns a list of dicts: ticker, allocation_pct, amount, rationale.
    """
    profile = get_profile(conn, user_profile_key)
    alloc = target_allocation(profile["profile_name"], profile["time_horizon_years"])
    asset_keys = _ensure_asset_rows(conn)

    conn.execute("DELETE FROM fact_recommendation WHERE user_profile_key = ?", (user_profile_key,))
    rows = []
    for ticker, pct in alloc.items():
        if pct <= 0:
            continue
        conn.execute(
            "INSERT INTO fact_recommendation (user_profile_key, asset_key, allocation_pct, rationale) "
            "VALUES (?, ?, ?, ?)",
            (user_profile_key, asset_keys[ticker], pct, RATIONALE[ticker]),
        )
        rows.append({
            "ticker": ticker,
            "allocation_pct": pct,
            "amount": round(profile["investment_amount"] * pct / 100, 2),
            "rationale": RATIONALE[ticker],
        })
    conn.commit()
    return sorted(rows, key=lambda r: -r["allocation_pct"])


def get_recommendation(conn: sqlite3.Connection, user_profile_key: int) -> list:
    """Reads a saved recommendation back as [(ticker, asset_class, allocation_pct)]."""
    return conn.execute(
        """
        SELECT a.ticker, a.asset_class, r.allocation_pct
        FROM fact_recommendation r JOIN dim_asset a ON a.asset_key = r.asset_key
        WHERE r.user_profile_key = ? ORDER BY r.allocation_pct DESC
        """,
        (user_profile_key,),
    ).fetchall()
