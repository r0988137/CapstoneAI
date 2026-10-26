"""
End-to-end workflow (Weeks 5-10 in one call):
questionnaire answers -> risk profile -> AI explanation -> portfolio
recommendation -> market news context -> forecast.

This is the single entry point the Week 11 front-end will call.

Usage (interactive questionnaire, then prints the full result):
    python -m src.workflow.run_workflow --user-id your-name
    python -m src.workflow.run_workflow --user-id your-name --no-news
"""
import argparse
import sqlite3

from src.ai.explain_profile import explain_and_save
from src.forecast.projection import forecast_and_save, final_year_summary
from src.news.market_news import get_market_context
from src.portfolio.allocation import recommend_and_save
from src.questionnaire.store import submit_questionnaire, get_profile

DISCLAIMER = ("Educational prototype only - not financial advice. Forecasts are illustrative estimates "
              "based on historical data and stated assumptions; past performance does not guarantee future results.")


def run_full_workflow(conn: sqlite3.Connection, external_id: str, answers: dict, include_news: bool = True) -> dict:
    submitted = submit_questionnaire(conn, external_id, answers)
    key = submitted["user_profile_key"]

    explanation = explain_and_save(conn, key)
    allocation = recommend_and_save(conn, key)
    forecast = forecast_and_save(conn, key)
    news = get_market_context(conn, key) if include_news else []

    return {
        "user_profile_key": key,
        "profile": get_profile(conn, key),
        "explanation": explanation,
        "allocation": allocation,
        "news": news,
        "forecast": forecast,
        "disclaimer": DISCLAIMER,
    }


def format_report(result: dict) -> str:
    p = result["profile"]
    lines = [
        "=" * 60,
        f"INVESTOR PROFILE: {p['profile_name']}  (risk score {p['risk_score']:.0f}/100)",
        "=" * 60,
        result["explanation"]["explanation"],
        f"[explanation source: {result['explanation']['source']}]",
        "",
        f"RECOMMENDED PORTFOLIO (${p['investment_amount']:,.0f})",
    ]
    for a in result["allocation"]:
        lines.append(f"  {a['ticker']:8s} {a['allocation_pct']:5.1f}%   ${a['amount']:>10,.2f}")

    if result["news"]:
        lines += ["", "MARKET CONTEXT"]
        for n in result["news"]:
            lines.append(f"  {n['ticker']} ({n['allocation_pct']:.0f}%): {n['summary']}")
            for h in n["headlines"]:
                lines.append(f"      - {h['title']} ({h['publisher']})")

    stats = result["forecast"]["stats"]
    summary = final_year_summary(result["forecast"]["rows"])
    years = max(r["horizon_year"] for r in result["forecast"]["rows"])
    contributed = [r for r in result["forecast"]["rows"] if r["horizon_year"] == years][0]["total_contributed"]
    lines += [
        "",
        f"FORECAST AFTER {years} YEAR(S)  (total put in: ${contributed:,.0f})",
        f"  assumed return {stats['mu']:.1%}/yr, volatility {stats['sigma']:.1%}  [{stats['data_source']}]",
        f"  conservative: ${summary['conservative']:>12,.0f}",
        f"  expected:     ${summary['expected']:>12,.0f}",
        f"  optimistic:   ${summary['optimistic']:>12,.0f}",
        "",
        result["disclaimer"],
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    from src.config.settings import WAREHOUSE_DB_PATH
    from src.questionnaire.collect import collect_answers_interactive

    parser = argparse.ArgumentParser(description="Run the full AI Power Portfolio workflow.")
    parser.add_argument("--user-id", default="demo-user")
    parser.add_argument("--no-news", action="store_true", help="Skip the news step (faster, works offline).")
    args = parser.parse_args()

    answers = collect_answers_interactive()
    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    try:
        result = run_full_workflow(conn, args.user_id, answers, include_news=not args.no_news)
    finally:
        conn.close()
    print("\n" + format_report(result))
