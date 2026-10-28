import pandas as pd
"""Weeks 11-12 tests: form handling, charts, tables and dashboard queries (no browser, no network)."""
import sqlite3
from datetime import date, timedelta

import pytest
from matplotlib.figure import Figure

from src.app import views
from src.config.settings import SCHEMA_SQL_PATH
from src.news import market_news
from src.workflow.run_workflow import run_full_workflow

FORM = dict(investment_amount=10000, time_horizon_years=10, risk_tolerance=4, loss_reaction=4,
            primary_goal="growth", monthly_contribution=200)


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setattr("src.ai.explain_profile.generate_text", lambda *a, **k: None)
    monkeypatch.setattr(market_news, "generate_text", lambda *a, **k: None)
    monkeypatch.setattr(market_news, "fetch_news", lambda t, limit=5: [{"title": f"{t} headline", "publisher": "Wire", "link": "https://x.test"}])
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_SQL_PATH.read_text())
    yield c
    c.close()


def _load_prices(conn, ticker, days=420, start_price=100.0, daily=0.001):
    from src.etl.load_market_data import upsert_dim_assets, upsert_dim_dates
    keys = upsert_dim_assets(conn)
    p, start = start_price, date(2025, 1, 1)
    for k in range(days):
        d = start + timedelta(days=k)
        upsert_dim_dates(conn, [d])
        p *= 1 + daily
        conn.execute("INSERT INTO fact_market_price (date_key, asset_key, close, adj_close) VALUES (?,?,?,?)",
                     (int(d.strftime("%Y%m%d")), keys[ticker], p, p))
    conn.commit()


def test_answers_from_form_converts_types():
    a = views.answers_from_form(10000.0, 10.0, "4", 4, "growth", None)
    assert a["time_horizon_years"] == 10 and isinstance(a["time_horizon_years"], int)
    assert a["risk_tolerance"] == 4 and a["monthly_contribution"] == 0.0


@pytest.mark.parametrize("bad", [
    dict(investment_amount=None), dict(investment_amount=-5), dict(time_horizon_years=0),
    dict(primary_goal="yolo"), dict(risk_tolerance=9),
])
def test_answers_from_form_rejects_bad_input(bad):
    form = {**dict(investment_amount=1000, time_horizon_years=5, risk_tolerance=3, loss_reaction=3,
                   primary_goal="income", monthly_contribution=0), **bad}
    with pytest.raises(ValueError):
        views.answers_from_form(form["investment_amount"], form["time_horizon_years"], form["risk_tolerance"],
                                form["loss_reaction"], form["primary_goal"], form["monthly_contribution"])


def test_dropdown_choices_are_label_value_pairs():
    assert views.RISK_CHOICES[0][1] == 1 and len(views.RISK_CHOICES) == 5 and len(views.LOSS_CHOICES) == 5


def test_result_views_render(conn):
    result = run_full_workflow(conn, "alice", FORM)
    assert "Aggressive" in views.profile_markdown(result) or "Growth" in views.profile_markdown(result)
    table = views.allocation_table(result["allocation"])
    assert list(table.columns) == ["Asset", "Name", "Type", "Allocation %", "Amount ($)"]
    assert table["Allocation %"].is_monotonic_decreasing and table["Allocation %"].sum() == pytest.approx(100, abs=0.5)
    assert isinstance(views.allocation_figure(result["allocation"]), Figure)
    assert isinstance(views.forecast_figure(result["forecast"]["rows"]), Figure)
    md = views.forecast_markdown(result)
    assert "After 10 year" in md and "Optimistic" in md
    assert "[VTI headline](https://x.test)" in views.news_markdown(result["news"])


def test_news_markdown_handles_empty():
    assert "No market news" in views.news_markdown([])


def test_dashboard_empty_warehouse(conn):
    assert views.market_overview(conn).empty
    assert isinstance(views.price_figure(conn), Figure)
    assert views.saved_profiles(conn).empty
    assert isinstance(views.profile_mix_figure(conn), Figure)
    assert "no data yet" in views.warehouse_status(conn)


def test_market_overview_returns(conn):
    _load_prices(conn, "VTI", days=420, daily=0.001)
    df = views.market_overview(conn)
    assert list(df.columns) == ["Asset", "Last price", "1D %", "1M %", "1Y %", "5Y %"]
    row = df[df["Asset"] == "VTI"].iloc[0]
    assert row["1D %"] == pytest.approx(0.1, abs=0.01)
    assert row["1M %"] == pytest.approx((1.001 ** 30 - 1) * 100, abs=0.2)
    assert row["1Y %"] == pytest.approx((1.001 ** 365 - 1) * 100, abs=0.3)
    assert pd.isna(row["5Y %"])                       # only ~14 months of data
    assert views.available_tickers(conn) == ["VTI"]
    assert isinstance(views.price_figure(conn, ["VTI"]), Figure)


def test_market_overview_five_year_column(conn):
    _load_prices(conn, "VTI", days=1830, daily=0.0005)
    row = views.market_overview(conn).iloc[0]
    assert row["5Y %"] == pytest.approx((1.0005 ** 1825 - 1) * 100, abs=1.0)


def test_saved_profiles_lists_latest_first(conn):
    run_full_workflow(conn, "alice", FORM, include_news=False)
    run_full_workflow(conn, "bob", {**FORM, "risk_tolerance": 1, "loss_reaction": 1, "primary_goal": "preservation"},
                      include_news=False)
    df = views.saved_profiles(conn)
    assert list(df["User"]) == ["bob", "alice"]
    assert "Conservative" in set(df["Profile"])
    assert isinstance(views.profile_mix_figure(conn), Figure)
    assert "2 questionnaires" in views.warehouse_status(conn)


def test_dashboard_shows_only_recommended_assets(conn):
    for t in ("VTI", "QQQ", "BTC-USD"):
        _load_prices(conn, t, days=420, daily=0.001)
    weights = {"VTI": 60.0, "BTC-USD": 5.0}
    df = views.market_overview(conn, tickers=list(weights), weights=weights)
    assert set(df["Asset"]) == {"VTI", "BTC-USD"} and "QQQ" not in set(df["Asset"])
    assert list(df["Asset"]) == ["VTI", "BTC-USD"]          # biggest holding first
    assert set(views.market_overview(conn)["Asset"]) == {"VTI", "QQQ", "BTC-USD"}   # market tab keeps everything


def test_recommended_assets_drops_cash_and_zeros():
    alloc = [{"ticker": "VTI", "allocation_pct": 70}, {"ticker": "CASH", "allocation_pct": 30},
             {"ticker": "GLD", "allocation_pct": 0}]
    assert views.recommended_assets(alloc) == {"VTI": 70}


def test_dashboard_without_portfolio_shows_hint_and_empty_chart():
    from src.app import app as web_app
    status, overview, fig = web_app.refresh_dashboard(None)
    assert "Get your portfolio first" in status and overview.empty and isinstance(fig, Figure)
