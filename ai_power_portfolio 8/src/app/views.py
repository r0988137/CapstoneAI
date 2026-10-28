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

from src.config.settings import ASSET_INFO, GROUP_ORDER
from src.questionnaire.schema import (
    LOSS_REACTION_SCALE, PRIMARY_GOAL_OPTIONS, RISK_TOLERANCE_SCALE, validate_answers,
)

SCENARIO_LABELS = {"conservative": "Conservative (bad case)", "expected": "Expected", "optimistic": "Optimistic (good case)"}
SCENARIO_STYLES = {"conservative": "--", "expected": "-", "optimistic": "--"}


# ---------------------------------------------------------------- form -> answers
def _to_number(value, name: str) -> float:
    """Form value -> float. Accepts numbers and strings like '1,000' or '$1000'; rejects nan/inf/blank."""
    if isinstance(value, str):
        value = value.replace(",", "").replace("$", "").strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Please enter a valid number for {name}.")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"Please enter a valid number for {name}.")
    return number


def answers_from_form(investment_amount, time_horizon_years, risk_tolerance, loss_reaction,
                      primary_goal, monthly_contribution) -> dict:
    """Turns raw form values (numbers can arrive as floats/strings) into a validated answers dict."""
    years = _to_number(time_horizon_years, "the time horizon")
    if years != int(years):
        raise ValueError("The time horizon must be a whole number of years.")
    monthly = 0.0 if monthly_contribution in (None, "") else _to_number(monthly_contribution, "the monthly contribution")
    if primary_goal not in GOAL_CHOICES:
        raise ValueError("Please choose a main goal.")
    try:
        risk, loss = int(risk_tolerance), int(loss_reaction)
    except (TypeError, ValueError):
        raise ValueError("Please answer every question.")
    answers = {
        "investment_amount": _to_number(investment_amount, "the investment amount"),
        "time_horizon_years": int(years),
        "risk_tolerance": risk,
        "loss_reaction": loss,
        "primary_goal": primary_goal,
        "monthly_contribution": monthly,
    }
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


def rationale_markdown(result: dict) -> str:
    lines = ["### Why this portfolio", result["rationale"]["text"], ""]
    for a in sorted(result["allocation"], key=lambda a: -a["allocation_pct"]):
        lines.append(f"- **{a['ticker']}** ({a['allocation_pct']:.0f}%): {a['rationale']}")
    return "\n".join(lines)


def allocation_table(allocation: List[dict]) -> pd.DataFrame:
    rows = []
    for a in sorted(allocation, key=lambda a: -a["allocation_pct"]):
        info = ASSET_INFO.get(a["ticker"], {})
        rows.append({"Asset": a["ticker"], "Name": info.get("name", ""), "Type": info.get("group", ""),
                     "Allocation %": round(a["allocation_pct"], 1), "Amount ($)": round(a["amount"], 2)})
    return pd.DataFrame(rows)


GROUP_COLORS = {
    "U.S. stocks": "#1F6F5C", "International stocks": "#3FA796", "Bonds": "#3B6EA8", "Real estate": "#8A6FB0",
    "Crypto": "#E08A1E", "Gold / silver": "#C9A227", "Cash": "#9AA5AE",
}
PROFILE_COLORS = {"Conservative": "#3B6EA8", "Moderate": "#3FA796", "Growth": "#E08A1E", "Aggressive": "#C0392B"}


def group_totals(allocation: List[dict]) -> dict:
    """{group: percent} in a fixed display order, only groups that hold money."""
    totals = {}
    for a in allocation:
        g = ASSET_INFO.get(a["ticker"], {}).get("group", "Other")
        totals[g] = totals.get(g, 0) + a["allocation_pct"]
    order = [g for g in GROUP_ORDER if g in totals] + [g for g in totals if g not in GROUP_ORDER]
    return {g: totals[g] for g in order if totals[g] > 0}


def allocation_figure(allocation: List[dict]) -> Figure:
    """Donut by asset type (7 colors at most), with the percentage in the legend."""
    totals = group_totals(allocation)
    fig = Figure(figsize=(6.4, 4))
    ax = fig.subplots()
    colors = [GROUP_COLORS.get(g, "#888888") for g in totals]
    wedges, _ = ax.pie(list(totals.values()), colors=colors, startangle=90, counterclock=False,
                       wedgeprops=dict(width=0.38, edgecolor="white", linewidth=2))
    ax.legend(wedges, [f"{g}  {p:.0f}%" for g, p in totals.items()], loc="center left",
              bbox_to_anchor=(1, 0.5), fontsize=9, frameon=False)
    fig.tight_layout()
    return fig


def holdings_figure(allocation: List[dict]) -> Figure:
    """Horizontal bars, one per ETF/asset, colored by type."""
    rows = sorted(allocation, key=lambda a: a["allocation_pct"])
    fig = Figure(figsize=(6, max(2.5, 0.38 * len(rows) + 1)))
    ax = fig.subplots()
    labels = [r["ticker"] for r in rows]
    colors = [GROUP_COLORS.get(ASSET_INFO.get(r["ticker"], {}).get("group"), "#888888") for r in rows]
    bars = ax.barh(labels, [r["allocation_pct"] for r in rows], color=colors)
    for bar, r in zip(bars, rows):
        ax.text(bar.get_width() + 0.4, bar.get_y() + bar.get_height() / 2, f"{r['allocation_pct']:.0f}%",
                va="center", fontsize=9)
    ax.set_xlim(0, max(r["allocation_pct"] for r in rows) * 1.18)
    ax.set_xlabel("% of portfolio")
    ax.set_title(" ", fontsize=14)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def summary_cards_html(result: dict) -> str:
    """Headline numbers as cards: profile + risk score, money in, and the three forecast outcomes."""
    from src.forecast.projection import final_year_summary
    p = result["profile"]
    rows = result["forecast"]["rows"]
    years = max(r["horizon_year"] for r in rows)
    put_in = [r for r in rows if r["horizon_year"] == years and r["scenario"] == "expected"][0]["total_contributed"]
    s = final_year_summary(rows)
    color = PROFILE_COLORS.get(p["profile_name"], "#1F6F5C")
    score = max(0, min(100, p["risk_score"]))
    return (
        '<div class="apc-grid">'
        f'<div class="apc-card apc-wide"><div class="apc-label">Your investor profile</div>'
        f'<div class="apc-big" style="color:{color}">{p["profile_name"]}</div>'
        f'<div class="apc-meter"><div style="width:{score:.0f}%;background:{color}"></div></div>'
        f'<div class="apc-small">Risk score {score:.0f} / 100</div></div>'
        f'<div class="apc-card"><div class="apc-label">You put in</div><div class="apc-big">${put_in:,.0f}</div>'
        f'<div class="apc-small">over {years} year(s)</div></div>'
        f'<div class="apc-card"><div class="apc-label">Expected value</div><div class="apc-big">${s["expected"]:,.0f}</div>'
        f'<div class="apc-small">likely range ${s["conservative"]:,.0f} to ${s["optimistic"]:,.0f}</div></div>'
        '</div>'
    )


def forecast_figure(rows: List[dict]) -> Figure:
    """Expected line, shaded bad-to-good range, and the total money put in, by year."""
    fig = Figure(figsize=(7, 4))
    ax = fig.subplots()
    series = {sc: sorted((r for r in rows if r["scenario"] == sc), key=lambda r: r["horizon_year"])
              for sc in ("conservative", "expected", "optimistic")}
    xs = [p["horizon_year"] for p in series["expected"]]
    low = [p["projected_value"] for p in series["conservative"]]
    mid = [p["projected_value"] for p in series["expected"]]
    high = [p["projected_value"] for p in series["optimistic"]]
    ax.fill_between(xs, low, high, color="#3FA796", alpha=0.18, label="Range (bad to good case)")
    ax.plot(xs, high, "--", color="#3FA796", linewidth=1, label=SCENARIO_LABELS["optimistic"])
    ax.plot(xs, low, "--", color="#C0392B", linewidth=1, label=SCENARIO_LABELS["conservative"])
    ax.plot(xs, mid, "-", color="#1F6F5C", linewidth=2.5, marker="o", markersize=3, label=SCENARIO_LABELS["expected"])
    ax.plot(xs, [p["total_contributed"] for p in series["expected"]], ":", color="gray", label="Total you put in")
    ax.set_xlabel("Years")
    ax.set_ylabel("Portfolio value ($)")
    ax.set_title("How your money could grow")
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:,.0f}")
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
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
    ax.bar(df.index, df["n"], color=[PROFILE_COLORS[i] for i in df.index])
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


def asset_catalog_table() -> pd.DataFrame:
    """Every asset the system can recommend, with the planning assumptions used in the forecast."""
    from src.config.settings import ASSET_CATALOG, CASH_ASSET
    rows = [{"Ticker": a["ticker"], "Name": a["name"], "Type": a["group"],
             "Return/yr": f'{a["ret"]:.1%}', "Volatility": f'{a["vol"]:.1%}', "Why it is used": a["why"]}
            for a in ASSET_CATALOG + [CASH_ASSET]]
    return pd.DataFrame(rows)
