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

CASH_TICKER = "CASH"

# percent per ticker; each row sums to 100
MODEL_PORTFOLIOS = {
    "Conservative": {"VTI": 15, "VXUS": 5, "BND": 45, "QQQ": 0, "BTC-USD": 0, "ETH-USD": 0, "GLD": 10, "SLV": 0, CASH_TICKER: 25},
    "Moderate":     {"VTI": 30, "VXUS": 10, "BND": 30, "QQQ": 5, "BTC-USD": 2, "ETH-USD": 0, "GLD": 8, "SLV": 0, CASH_TICKER: 15},
    "Growth":       {"VTI": 38, "VXUS": 15, "BND": 12, "QQQ": 15, "BTC-USD": 5, "ETH-USD": 2, "GLD": 6, "SLV": 1, CASH_TICKER: 6},
    "Aggressive":   {"VTI": 35, "VXUS": 15, "BND": 0, "QQQ": 25, "BTC-USD": 12, "ETH-USD": 5, "GLD": 4, "SLV": 1, CASH_TICKER: 3},
}

SHORT_HORIZON_YEARS = 3

RATIONALE = {
    "VTI": "Core holding: broad U.S. stock market exposure for long-term growth and diversification.",
    "VXUS": "Adds international stocks so the portfolio isn't tied to the U.S. market alone.",
    "BND": "Bonds tend to move less than stocks, which helps cushion the portfolio in down markets.",
    "QQQ": "Tilts toward large technology-oriented companies for higher growth potential (and higher swings).",
    "BTC-USD": "Small higher-risk slice: Bitcoin is very volatile, so it is limited to what the profile can tolerate.",
    "ETH-USD": "Small higher-risk slice: Ethereum adds crypto exposure with similarly large swings.",
    "GLD": "Gold is often used as a diversifier that does not always move with stocks.",
    "SLV": "Silver adds a small precious-metals position with more volatility than gold.",
    CASH_TICKER: "Cash keeps part of the money stable and available, and reduces overall volatility.",
}


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
