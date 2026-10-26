"""End-to-end test of Weeks 5-10 chained together (no network, no API key)."""
import sqlite3

import pytest

from src.config.settings import SCHEMA_SQL_PATH
from src.news import market_news
from src.workflow.run_workflow import run_full_workflow, format_report


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setattr("src.ai.explain_profile.generate_text", lambda *a, **k: None)
    monkeypatch.setattr(market_news, "generate_text", lambda *a, **k: None)
    monkeypatch.setattr(market_news, "fetch_news", lambda t, limit=5: [{"title": f"{t} headline", "publisher": "Wire"}])
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_SQL_PATH.read_text())
    yield c
    c.close()


ANSWERS = dict(investment_amount=25000, time_horizon_years=15, risk_tolerance=4, loss_reaction=4,
               primary_goal="growth", monthly_contribution=300)


def test_full_workflow_populates_every_fact_table(conn):
    result = run_full_workflow(conn, "alice", ANSWERS)
    key = result["user_profile_key"]
    count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE user_profile_key=?", (key,)).fetchone()[0]
    assert count("fact_user_profile") == 1
    assert count("fact_recommendation") > 0
    assert count("fact_forecast") == 3 * 15
    assert conn.execute("SELECT ai_explanation FROM fact_user_profile WHERE user_profile_key=?", (key,)).fetchone()[0]
    assert result["news"] and result["explanation"]["source"] == "template"


def test_workflow_can_skip_news(conn):
    assert run_full_workflow(conn, "bob", ANSWERS, include_news=False)["news"] == []


def test_format_report_contains_all_sections(conn):
    text = format_report(run_full_workflow(conn, "carol", ANSWERS))
    for section in ["INVESTOR PROFILE", "RECOMMENDED PORTFOLIO", "MARKET CONTEXT", "FORECAST AFTER 15", "not financial advice"]:
        assert section in text


def test_workflow_rejects_invalid_answers(conn):
    with pytest.raises(ValueError):
        run_full_workflow(conn, "dave", {**ANSWERS, "primary_goal": "yolo"})
