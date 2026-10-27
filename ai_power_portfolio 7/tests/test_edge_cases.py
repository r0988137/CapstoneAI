"""Week 13: edge cases, bug-fix regressions and full-path integration tests (no network, no API key)."""
import itertools
import math
import sqlite3
import time
from datetime import date, timedelta

import pytest

from src.app import app as web_app
from src.app import views
from src.config.settings import SCHEMA_SQL_PATH
from src.forecast.projection import estimate_portfolio_stats
from src.news import market_news
from src.portfolio.rationale import generate_rationale, group_weights, template_rationale
from src.questionnaire.schema import MAX_HORIZON_YEARS, validate_answers
from src.workflow.run_workflow import format_report, run_full_workflow

BASE = dict(investment_amount=10000, time_horizon_years=10, risk_tolerance=3, loss_reaction=3,
            primary_goal="growth", monthly_contribution=100)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr("src.ai.explain_profile.generate_text", lambda *a, **k: None)
    monkeypatch.setattr("src.portfolio.rationale.generate_text", lambda *a, **k: None)
    monkeypatch.setattr(market_news, "generate_text", lambda *a, **k: None)
    monkeypatch.setattr(market_news, "fetch_news", lambda t, limit=5: [{"title": f"{t} news", "publisher": "Wire", "link": ""}])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_SQL_PATH.read_text())
    yield c
    c.close()


# ---------------------------------------------------------------- validation regressions
@pytest.mark.parametrize("field,value", [
    ("investment_amount", float("nan")), ("investment_amount", float("inf")), ("investment_amount", 1e15),
    ("investment_amount", True), ("time_horizon_years", True), ("time_horizon_years", MAX_HORIZON_YEARS + 1),
    ("time_horizon_years", 2.5), ("monthly_contribution", float("nan")), ("monthly_contribution", float("inf")),
    ("monthly_contribution", 1e12), ("monthly_contribution", -1), ("risk_tolerance", True), ("risk_tolerance", 3.5),
])
def test_validation_rejects_bad_values(field, value):
    with pytest.raises(ValueError):
        validate_answers({**BASE, field: value})


def test_validation_accepts_the_limits():
    validate_answers({**BASE, "time_horizon_years": MAX_HORIZON_YEARS, "investment_amount": 1, "monthly_contribution": 0})


@pytest.mark.parametrize("args,message", [
    ((float("inf"), 10, 3, 3, "growth", 0), "valid number"),
    ((1000, 7.5, 3, 3, "growth", 0), "whole number"),
    ((1000, "abc", 3, 3, "growth", 0), "valid number"),
    ((1000, 10, None, 3, "growth", 0), "every question"),
    ((1000, 10, 3, 3, None, 0), "main goal"),
    ((None, 10, 3, 3, "growth", 0), "valid number"),
])
def test_form_gives_friendly_messages(args, message):
    with pytest.raises(ValueError, match=message):
        views.answers_from_form(*args)


def test_form_accepts_formatted_numbers_and_blank_monthly():
    a = views.answers_from_form("$1,500.50", "10", 3, 3, "income", None)
    assert a["investment_amount"] == 1500.50 and a["monthly_contribution"] == 0.0


# ---------------------------------------------------------------- every combination works
def test_every_questionnaire_combination_gives_a_sane_result(conn):
    count = 0
    for rt, lr, goal, years in itertools.product(range(1, 6), range(1, 6), ["preservation", "income", "combination", "growth"],
                                                 [1, 2, 3, 5, 10, 30, MAX_HORIZON_YEARS]):
        r = run_full_workflow(conn, f"u{count}", {**BASE, "risk_tolerance": rt, "loss_reaction": lr,
                                                  "primary_goal": goal, "time_horizon_years": years}, include_news=False)
        assert sum(a["allocation_pct"] for a in r["allocation"]) == pytest.approx(100)
        rows = r["forecast"]["rows"]
        assert all(math.isfinite(x["projected_value"]) and x["projected_value"] > 0 for x in rows)
        last = {x["scenario"]: x["projected_value"] for x in rows if x["horizon_year"] == years}
        assert last["conservative"] <= last["expected"] <= last["optimistic"]
        if years < 3:
            assert not {a["ticker"] for a in r["allocation"]} & {"BTC-USD", "ETH-USD"}
        count += 1
    assert count == 700


def test_extreme_amounts_stay_finite(conn):
    tiny = run_full_workflow(conn, "tiny", {**BASE, "investment_amount": 1, "monthly_contribution": 0, "time_horizon_years": 1}, include_news=False)
    huge = run_full_workflow(conn, "huge", {**BASE, "investment_amount": 1e9, "monthly_contribution": 1e7,
                                            "time_horizon_years": MAX_HORIZON_YEARS}, include_news=False)
    assert all(math.isfinite(r["projected_value"]) for r in tiny["forecast"]["rows"] + huge["forecast"]["rows"])


def test_same_user_can_submit_twice_and_history_keeps_both(conn):
    run_full_workflow(conn, "alice", BASE, include_news=False)
    run_full_workflow(conn, "alice", {**BASE, "risk_tolerance": 5, "loss_reaction": 5}, include_news=False)
    assert conn.execute("SELECT COUNT(*) FROM dim_user").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM fact_user_profile").fetchone()[0] == 2
    assert len(views.saved_profiles(conn)) == 2


# ---------------------------------------------------------------- data gaps
def _prices(conn, ticker, days=300, daily=0.0005):
    from src.etl.load_market_data import upsert_dim_assets, upsert_dim_dates
    keys = upsert_dim_assets(conn)
    p, start = 100.0, date(2025, 1, 1)
    for k in range(days):
        d = start + timedelta(days=k)
        upsert_dim_dates(conn, [d])
        p *= 1 + daily
        conn.execute("INSERT INTO fact_market_price (date_key, asset_key, close, adj_close) VALUES (?,?,?,?)",
                     (int(d.strftime("%Y%m%d")), keys[ticker], p, p))
    conn.commit()


def test_forecast_works_when_only_some_assets_have_price_history(conn):
    _prices(conn, "VTI")           # every other asset has no data at all
    r = run_full_workflow(conn, "partial", BASE, include_news=False)
    assert r["forecast"]["stats"]["data_source"] == "historical + assumptions"
    assert math.isfinite(r["forecast"]["stats"]["sigma"])


def test_zero_and_null_prices_are_ignored(conn):
    _prices(conn, "VTI", days=200)
    conn.execute("UPDATE fact_market_price SET close = 0, adj_close = NULL WHERE date_key % 7 = 0")
    conn.commit()
    stats = estimate_portfolio_stats(conn, {"VTI": 100})
    assert math.isfinite(stats["mu"]) and math.isfinite(stats["sigma"])


# ---------------------------------------------------------------- news can't freeze the app
def test_slow_news_request_times_out_instead_of_hanging(conn, monkeypatch):
    monkeypatch.setattr(market_news, "NEWS_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(market_news, "fetch_news", lambda t, limit=5: time.sleep(3) or [])
    r = run_full_workflow(conn, "slow", BASE, include_news=False)
    start = time.time()
    ctx = market_news.get_market_context(conn, r["user_profile_key"], top_n=3)
    assert time.time() - start < 2.5          # three 3-second requests ran in parallel and were abandoned
    assert len(ctx) == 3 and all(c["source"] == "unavailable" for c in ctx)


def test_news_error_for_one_ticker_does_not_break_the_rest(conn, monkeypatch):
    def flaky(ticker, limit=5):
        if ticker == "VTI":
            raise RuntimeError("boom")
        return [{"title": f"{ticker} news", "publisher": "Wire", "link": ""}]
    monkeypatch.setattr(market_news, "fetch_news", flaky)
    r = run_full_workflow(conn, "flaky", BASE, include_news=False)
    ctx = market_news.get_market_context(conn, r["user_profile_key"], top_n=3)
    by = {c["ticker"]: c for c in ctx}
    assert by["VTI"]["source"] == "unavailable" and any(c["source"] == "headlines-only" for c in ctx)


# ---------------------------------------------------------------- portfolio rationale
def test_rationale_weights_add_up_to_the_allocation(conn):
    r = run_full_workflow(conn, "w", {**BASE, "risk_tolerance": 5, "loss_reaction": 5}, include_news=False)
    w = group_weights(r["allocation"])
    assert sum(w.values()) == pytest.approx(100) and "Crypto" in w


def test_rationale_mentions_short_horizon_rule(conn):
    r = run_full_workflow(conn, "s", {**BASE, "time_horizon_years": 2, "risk_tolerance": 5, "loss_reaction": 5}, include_news=False)
    assert "time horizon is only 2" in r["rationale"]["text"] and r["rationale"]["source"] == "template"
    assert "Crypto is limited" not in r["rationale"]["text"]      # no crypto left after the rule


def test_rationale_uses_llm_when_available(monkeypatch):
    monkeypatch.setattr("src.portfolio.rationale.generate_text", lambda *a, **k: "LLM text")
    alloc = [{"ticker": "VTI", "allocation_pct": 100.0, "amount": 1, "rationale": ""}]
    profile = dict(profile_name="Growth", risk_score=60, primary_goal="growth", time_horizon_years=10)
    assert generate_rationale(profile, alloc) == ("LLM text", "llm")
    assert "a Growth profile" in template_rationale(profile, alloc)
    assert "an Aggressive profile" in template_rationale({**profile, "profile_name": "Aggressive"}, alloc)


def test_report_contains_the_new_section(conn):
    assert "WHY THIS PORTFOLIO" in format_report(run_full_workflow(conn, "r", BASE, include_news=False))


# ---------------------------------------------------------------- the web handlers, end to end
@pytest.fixture
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "web.db"

    def get_conn():
        c = sqlite3.connect(path)
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='fact_user_profile'").fetchone():
            c.executescript(SCHEMA_SQL_PATH.read_text())
        return c
    monkeypatch.setattr(web_app, "get_conn", get_conn)
    return path


def test_web_handler_full_path(app_db):
    out = web_app.run_questionnaire("web-user", 20000, 15, 4, 4, "growth", 300, True)
    assert len(out) == 7
    profile_md, rationale_md, pie, table, fig, forecast_md, news_md = out
    assert "investor" in profile_md and "Why this portfolio" in rationale_md
    assert pie is not None and fig is not None and len(table) >= 5
    assert "After 15 year" in forecast_md and "VTI" in news_md
    status, overview, price_fig, profiles, mix = web_app.refresh_dashboard(None)
    assert "1 questionnaires" in status and len(profiles) == 1 and overview.empty


@pytest.mark.parametrize("bad", [(0, 10, 3, 3, "growth", 0), (1000, 200, 3, 3, "growth", 0), (1000, 10, 3, 3, "growth", -5)])
def test_web_handler_shows_message_and_saves_nothing_on_bad_input(app_db, bad):
    out = web_app.run_questionnaire("x", *bad, False)
    assert out[0].startswith("**Please check your answers:**") and len(out) == 7
    assert web_app.refresh_dashboard(None)[3].empty


def test_web_handler_blank_name_falls_back(app_db):
    web_app.run_questionnaire("   ", 1000, 5, 3, 3, "income", 0, False)
    assert list(web_app.refresh_dashboard(None)[3]["User"]) == ["web-user"]
