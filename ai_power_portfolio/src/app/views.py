"""
Weeks 11-12 - everything the web app shows, as plain functions.

No web library is imported here, so all of it is testable without a browser:
  - form answers -> validated questionnaire dict
  - results -> markdown text, tables and matplotlib figures
  - dashboard queries on the warehouse (market overview, price chart, saved profiles)
"""
import sqlite3
from typing import List, Optional

import pandas as pd
from matplotlib.figure import Figure

from src.questionnaire.schema import (
    LOSS_REACTION_SCALE, PRIMARY_GOAL_OPTIONS, RISK_TOLERANCE_SCALE, validate_answers,
)

SCENARIO_LABELS = {"conservative": "Conservative (bad case)", "expected": "Expected", "optimistic": "Optimistic (good case)"}
SCENARIO_STYLES = {"conservative": "--", "expected": "-", "optimistic": "--"}


# ---------------------------------------------------------------- form -> answers
def answers_from_form(investment_amount, time_horizon_years, risk_tolerance, loss_reaction,
                      primary_goal, monthly_contribution) -> dict:
    """Turns raw form values (numbers can arrive as floats/strings) into a validated answers dict."""
    try:
        answers = {
            "investment_amount": float(investment_amount),
            "time_horizon_years": int(float(time_horizon_years)),
            "risk_tolerance": int(risk_tolerance),
            "loss_reaction": int(loss_reaction),
            "primary_goal": primary_goal,
            "monthly_contribution": float(monthly_contribution or 0),
        }
    except (TypeError, ValueError):
        raise ValueError("Please fill in every field with valid numbers.")
    validate_answers(answers)
    return answers


def scale_choices(scale: dict) -> list:
    """[(label, value)] pairs for dropdowns/radios."""
    return [(f"{k} - {v}", k) for k, v in scale.items()]


RISK_CHOICES = scale_choices(RISK_TOLERANCE_SCALE)
LOSS_CHOICES = scale_choices(LOSS_REACTION_SCALE)
GOAL_CHOICES = PRIMARY_GOAL_OPTIONS


# ---------------------------------------------------------------- results
def profile_markdown(result: dict) -> str:
    p = result["profile"]
    return (
        f"## {p['profile_name']} investor\n"
        f"**Risk score:** {p['risk_score']:.0f} / 100\n\n"
        f"{result['explanation']['explanation']}\n\n"
        f"*Explanation source: {result['explanation']['source']}*"
    )


def allocation_table(allocation: List[dict]) -> pd.DataFrame:
    return pd.DataFrame([
        {"Asset": a["ticker"], "Allocation %": round(a["allocation_pct"], 1), "Amount ($)": round(a["amount"], 2)}
        for a in sorted(allocation, key=lambda a: -a["allocation_pct"])
    ])


def allocation_figure(allocation: List[dict]) -> Figure:
    rows = sorted(allocation, key=lambda a: -a["allocation_pct"])
    fig = Figure(figsize=(5.5, 4))
    ax = fig.subplots()
    wedges, _, _ = ax.pie([r["allocation_pct"] for r in rows],
                          autopct=lambda p: f"{p:.0f}%" if p >= 5 else "", startangle=90, counterclock=False,
                          pctdistance=0.78)
    ax.legend(wedges, [f"{r['ticker']} ({r['allocation_pct']:.0f}%)" for r in rows],
              loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8, frameon=False)
    ax.set_title("Recommended portfolio")
    return fig


def forecast_figure(rows: List[dict]) -> Figure:
    """Three scenario lines + the total money put in, by year."""
    fig = Figure(figsize=(7, 4))
    ax = fig.subplots()
    for scenario in ("conservative", "expected", "optimistic"):
        pts = sorted((r for r in rows if r["scenario"] == scenario), key=lambda r: r["horizon_year"])
        ax.plot([p["horizon_year"] for p in pts], [p["projected_value"] for p in pts],
                SCENARIO_STYLES[scenario], marker="o", markersize=3, label=SCENARIO_LABELS[scenario])
    exp = sorted((r for r in rows if r["scenario"] == "expected"), key=lambda r: r["horizon_year"])
    ax.plot([p["horizon_year"] for p in exp], [p["total_contributed"] for p in exp],
            ":", color="gray", label="Total you put in")
    ax.set_xlabel("Years")
    ax.set_ylabel("Portfolio value ($)")
    ax.set_title("Forecast by scenario")
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    return fig


def forecast_markdown(result: dict) -> str:
    from src.forecast.projection import final_year_summary
    rows, stats = result["forecast"]["rows"], result["forecast"]["stats"]
    s = final_year_summary(rows)
    years = max(r["horizon_year"] for r in rows)
    put_in = [r for r in rows if r["horizon_year"] == years][0]["total_contributed"]
    return (
        f"### After {years} year(s)\n"
        f"- Total you put in: **${put_in:,.0f}**\n"
        f"- Conservative: **${s['conservative']:,.0f}**\n"
        f"- Expected: **${s['expected']:,.0f}**\n"
        f"- Optimistic: **${s['optimistic']:,.0f}**\n\n"
        f"*Assumed return {stats['mu']:.1%}/yr, volatility {stats['sigma']:.1%} ({stats['data_source']}).*"
    )


def news_markdown(news: List[dict]) -> str:
    if not news:
        return "*No market news to show (skipped or unavailable).*"
    out = []
    for n in news:
        out.append(f"**{n['ticker']}** ({n['allocation_pct']:.0f}% of your portfolio) - {n['summary']}")
        for h in n["headlines"]:
            title = f"[{h['title']}]({h['link']})" if h.get("link") else h["title"]
            out.append(f"- {title} - *{h.get('publisher', '')}*")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- dashboard
def market_overview(conn: sqlite3.Connection) -> pd.DataFrame:
    """One row per asset with data: last price and returns over 1 month / 1 year / whole history."""
    df = pd.read_sql(
        """
        SELECT a.ticker, d.full_date AS date, COALESCE(f.adj_close, f.close) AS price
        FROM fact_market_price f
        JOIN dim_asset a ON a.asset_key = f.asset_key
        JOIN dim_date d ON d.date_key = f.date_key
        WHERE COALESCE(f.adj_close, f.close) > 0
        ORDER BY a.ticker, d.full_date
        """, conn)
    if df.empty:
        return pd.DataFrame(columns=["Asset", "Last date", "Last price", "1M %", "1Y %", "Since start %", "Days of data"])

    def pct_back(g, days):
        last = pd.Timestamp(g["date"].iloc[-1])
        past = g[pd.to_datetime(g["date"]) <= last - pd.Timedelta(days=days)]
        return round((g["price"].iloc[-1] / past["price"].iloc[-1] - 1) * 100, 1) if len(past) else None

    rows = []
    for ticker, g in df.groupby("ticker"):
        rows.append({
            "Asset": ticker, "Last date": g["date"].iloc[-1], "Last price": round(g["price"].iloc[-1], 2),
            "1M %": pct_back(g, 30), "1Y %": pct_back(g, 365),
            "Since start %": round((g["price"].iloc[-1] / g["price"].iloc[0] - 1) * 100, 1),
            "Days of data": len(g),
        })
    return pd.DataFrame(rows)


def price_figure(conn: sqlite3.Connection, tickers: Optional[List[str]] = None) -> Figure:
    """Prices rebased to 100 at each asset's first day so different assets can be compared."""
    df = pd.read_sql(
        """
        SELECT a.ticker, d.full_date AS date, COALESCE(f.adj_close, f.close) AS price
        FROM fact_market_price f
        JOIN dim_asset a ON a.asset_key = f.asset_key
        JOIN dim_date d ON d.date_key = f.date_key
        WHERE COALESCE(f.adj_close, f.close) > 0
        ORDER BY d.full_date
        """, conn)
    fig = Figure(figsize=(8, 4))
    ax = fig.subplots()
    if df.empty:
        ax.text(0.5, 0.5, "No market data loaded yet.\nRun the ETL first.", ha="center", va="center")
        ax.set_axis_off()
        return fig
    df["date"] = pd.to_datetime(df["date"])
    wide = df.pivot_table(index="date", columns="ticker", values="price")
    if tickers:
        wide = wide[[t for t in tickers if t in wide.columns]]
    for t in wide.columns:
        s = wide[t].dropna()
        if not s.empty:
            ax.plot(s.index, s / s.iloc[0] * 100, label=t)
    ax.set_ylabel("Price (first day = 100)")
    ax.set_title("Asset performance")
    ax.set_yscale("log")
    ax.grid(alpha=0.3)
    ax.legend(ncol=4, fontsize=8)
    fig.tight_layout()
    return fig


def available_tickers(conn: sqlite3.Connection) -> List[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT a.ticker FROM fact_market_price f JOIN dim_asset a ON a.asset_key=f.asset_key ORDER BY 1")]


def saved_profiles(conn: sqlite3.Connection, limit: int = 50) -> pd.DataFrame:
    """Latest saved questionnaires with their profile and risk score."""
    return pd.read_sql(
        """
        SELECT u.external_id AS "User", p.profile_name AS "Profile", ROUND(f.risk_score) AS "Risk score",
               f.investment_amount AS "Amount ($)", f.time_horizon_years AS "Years",
               f.monthly_contribution AS "Monthly ($)", f.primary_goal AS "Goal", d.full_date AS "Date"
        FROM fact_user_profile f
        JOIN dim_user u ON u.user_key = f.user_key
        JOIN dim_investor_profile_type p ON p.profile_type_key = f.profile_type_key
        JOIN dim_date d ON d.date_key = f.date_key
        ORDER BY f.user_profile_key DESC LIMIT ?
        """, conn, params=(limit,))


def profile_mix_figure(conn: sqlite3.Connection) -> Figure:
    df = pd.read_sql(
        """
        SELECT p.profile_name AS profile, COUNT(*) AS n
        FROM fact_user_profile f JOIN dim_investor_profile_type p ON p.profile_type_key = f.profile_type_key
        GROUP BY p.profile_name
        """, conn)
    fig = Figure(figsize=(5, 3.5))
    ax = fig.subplots()
    if df.empty:
        ax.text(0.5, 0.5, "No questionnaires yet.", ha="center", va="center")
        ax.set_axis_off()
        return fig
    order = ["Conservative", "Moderate", "Growth", "Aggressive"]
    df = df.set_index("profile").reindex(order).fillna(0)
    ax.bar(df.index, df["n"])
    ax.set_ylabel("Questionnaires")
    ax.set_title("Investor profiles")
    ax.yaxis.get_major_locator().set_params(integer=True)
    fig.tight_layout()
    return fig


def warehouse_status(conn: sqlite3.Connection) -> str:
    def n(t):
        return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    rng = conn.execute(
        "SELECT MIN(d.full_date), MAX(d.full_date) FROM fact_market_price f JOIN dim_date d ON d.date_key=f.date_key"
    ).fetchone()
    span = f"{rng[0]} to {rng[1]}" if rng[0] else "no data yet"
    return (f"**Warehouse:** {n('fact_market_price'):,} price rows ({span}) | {n('fact_user_profile')} questionnaires | "
            f"{n('fact_recommendation')} recommendation lines | {n('fact_forecast')} forecast points")
