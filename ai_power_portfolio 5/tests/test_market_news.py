"""Week 9 tests. No network: yfinance and the LLM are stubbed."""
import sqlite3

import pytest

from src.config.settings import SCHEMA_SQL_PATH
from src.news import market_news
from src.news.market_news import normalize_news_item, summarize_relevance, get_market_context
from src.portfolio.allocation import recommend_and_save
from src.questionnaire.store import submit_questionnaire

NEW_FORMAT = {"content": {
    "title": "Fed holds rates steady",
    "provider": {"displayName": "Example News"},
    "canonicalUrl": {"url": "https://example.com/a"},
    "pubDate": "2026-10-01T12:00:00Z",
}}
OLD_FORMAT = {"title": "Gold hits record", "publisher": "Old Wire", "link": "https://example.com/b",
              "providerPublishTime": 1759320000}


def test_normalize_handles_new_format():
    assert normalize_news_item(NEW_FORMAT) == {
        "title": "Fed holds rates steady", "publisher": "Example News",
        "link": "https://example.com/a", "published": "2026-10-01T12:00:00Z"}


def test_normalize_handles_old_format():
    item = normalize_news_item(OLD_FORMAT)
    assert item["title"] == "Gold hits record" and item["publisher"] == "Old Wire"


def test_normalize_skips_items_without_title():
    assert normalize_news_item({"content": {"summary": "no title"}}) is None


def test_fetch_news_returns_empty_when_yfinance_fails(monkeypatch):
    import yfinance
    def boom(*a, **k):
        raise RuntimeError("no network")
    monkeypatch.setattr(yfinance, "Ticker", boom)
    assert market_news.fetch_news("VTI") == []


def test_summarize_with_no_headlines_is_unavailable():
    out = summarize_relevance("VTI", "Vanguard Total Stock Market ETF", 30, "Growth", [])
    assert out["source"] == "unavailable"


def test_summarize_falls_back_without_llm(monkeypatch):
    monkeypatch.setattr(market_news, "generate_text", lambda *a, **k: None)
    out = summarize_relevance("GLD", "SPDR Gold Shares", 8, "Moderate", [{"title": "x", "publisher": "y"}])
    assert out["source"] == "headlines-only"


def test_summarize_uses_llm_when_available(monkeypatch):
    monkeypatch.setattr(market_news, "generate_text", lambda *a, **k: "Summary text.")
    out = summarize_relevance("GLD", "SPDR Gold Shares", 8, "Moderate", [{"title": "x", "publisher": "y"}])
    assert out == {"summary": "Summary text.", "source": "llm"}


def test_get_market_context_skips_cash_and_respects_top_n(monkeypatch):
    monkeypatch.setattr(market_news, "fetch_news", lambda t, limit=5: [{"title": f"{t} news", "publisher": "p"}])
    monkeypatch.setattr(market_news, "generate_text", lambda *a, **k: None)
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_SQL_PATH.read_text())
    key = submit_questionnaire(conn, "u", dict(
        investment_amount=1000, time_horizon_years=10, risk_tolerance=2, loss_reaction=2,
        primary_goal="preservation", monthly_contribution=0))["user_profile_key"]
    recommend_and_save(conn, key)

    ctx = get_market_context(conn, key, top_n=3)
    assert len(ctx) == 3
    assert all(c["ticker"] != "CASH" for c in ctx)
    assert ctx[0]["allocation_pct"] >= ctx[-1]["allocation_pct"]
    assert ctx[0]["headlines"][0]["title"].endswith("news")
    conn.close()
