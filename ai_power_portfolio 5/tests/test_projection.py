"""Week 10 tests: projection math, stats estimation, and saving to fact_forecast."""
import sqlite3
from datetime import date, timedelta

import pytest

from src.config.settings import SCHEMA_SQL_PATH
from src.forecast.projection import (
    project_value, build_forecast, estimate_portfolio_stats, forecast_and_save,
    final_year_summary, ASSUMPTIONS, MIN_OBSERVATIONS,
)
from src.portfolio.allocation import MODEL_PORTFOLIOS, recommend_and_save
from src.questionnaire.store import submit_questionnaire


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_SQL_PATH.read_text())
    yield c
    c.close()


def test_project_value_zero_return_is_just_money_in():
    assert project_value(1000, 0, 0.0, 5) == 1000
    assert project_value(0, 100, 0.0, 1) == 1200


def test_project_value_lump_sum_only_matches_compound_interest():
    assert project_value(1000, 0, 0.07, 10) == pytest.approx(1000 * 1.07 ** 10)


def test_project_value_monthly_contributions_hand_check():
    # 12 end-of-month contributions of 100 at 12%/yr effective -> i = 1.12^(1/12)-1
    i = 1.12 ** (1 / 12) - 1
    expected = 100 * ((1 + i) ** 12 - 1) / i
    assert project_value(0, 100, 0.12, 1) == pytest.approx(expected)


def test_build_forecast_shape_and_ordering():
    rows = build_forecast(10000, 200, 10, mu=0.06, sigma=0.15)
    assert len(rows) == 3 * 10
    for t in range(1, 11):
        by = {r["scenario"]: r["projected_value"] for r in rows if r["horizon_year"] == t}
        assert by["conservative"] < by["expected"] < by["optimistic"]


def test_build_forecast_expected_scenario_compounds_at_mu():
    rows = build_forecast(10000, 0, 5, mu=0.06, sigma=0.15)
    expected_y5 = [r for r in rows if r["scenario"] == "expected" and r["horizon_year"] == 5][0]
    assert expected_y5["projected_value"] == pytest.approx(10000 * 1.06 ** 5, abs=0.01)


def test_build_forecast_band_narrows_as_horizon_grows():
    rows = build_forecast(10000, 0, 20, mu=0.06, sigma=0.15)
    ret = lambda s, t: [r["annual_return"] for r in rows if r["scenario"] == s and r["horizon_year"] == t][0]
    spread = lambda t: ret("optimistic", t) - ret("conservative", t)
    assert spread(1) > spread(5) > spread(20)


def test_build_forecast_tracks_total_contributed():
    rows = build_forecast(5000, 100, 3, mu=0.05, sigma=0.1)
    assert [r for r in rows if r["horizon_year"] == 3][0]["total_contributed"] == 5000 + 100 * 36


def test_stats_use_assumptions_when_no_price_history(conn):
    stats = estimate_portfolio_stats(conn, {"VTI": 60, "CASH": 40})
    assert stats["data_source"] == "assumptions only"
    assert stats["mu"] == pytest.approx(0.6 * ASSUMPTIONS["VTI"][0] + 0.4 * ASSUMPTIONS["CASH"][0])
    assert stats["sigma"] == pytest.approx(0.6 * ASSUMPTIONS["VTI"][1])  # cash has zero vol, single risky asset


def test_all_cash_portfolio_has_zero_volatility(conn):
    assert estimate_portfolio_stats(conn, {"CASH": 100})["sigma"] == 0


def _load_flat_growth_history(conn, ticker, daily_return, days):
    from src.etl.load_market_data import upsert_dim_assets, upsert_dim_dates
    keys = upsert_dim_assets(conn)
    start = date(2025, 1, 1)
    price = 100.0
    for k in range(days):
        d = start + timedelta(days=k)
        upsert_dim_dates(conn, [d])
        price *= 1 + daily_return
        conn.execute(
            "INSERT INTO fact_market_price (date_key, asset_key, close, adj_close) VALUES (?, ?, ?, ?)",
            (int(d.strftime("%Y%m%d")), keys[ticker], price, price),
        )
    conn.commit()


def test_stats_blend_history_with_assumption(conn):
    _load_flat_growth_history(conn, "VTI", 0.0004, MIN_OBSERVATIONS + 50)  # ~10.1%/yr, zero volatility
    stats = estimate_portfolio_stats(conn, {"VTI": 100})
    hist_mu = 0.0004 * 252
    assert stats["data_source"] == "historical + assumptions"
    assert stats["mu"] == pytest.approx(0.5 * hist_mu + 0.5 * ASSUMPTIONS["VTI"][0])
    # history has ~zero vol, so sigma is half the assumption-based number
    assert stats["sigma"] == pytest.approx(0.5 * ASSUMPTIONS["VTI"][1], rel=0.01)


def test_forecast_and_save_writes_three_scenarios_for_each_year(conn):
    key = submit_questionnaire(conn, "u", dict(
        investment_amount=10000, time_horizon_years=7, risk_tolerance=4, loss_reaction=4,
        primary_goal="growth", monthly_contribution=150))["user_profile_key"]
    recommend_and_save(conn, key)
    out = forecast_and_save(conn, key)

    assert conn.execute("SELECT COUNT(*) FROM fact_forecast WHERE user_profile_key=?", (key,)).fetchone()[0] == 21
    summary = final_year_summary(out["rows"])
    assert summary["conservative"] < summary["expected"] < summary["optimistic"]

    forecast_and_save(conn, key)  # re-run replaces rather than duplicates
    assert conn.execute("SELECT COUNT(*) FROM fact_forecast WHERE user_profile_key=?", (key,)).fetchone()[0] == 21


def test_forecast_without_recommendation_raises_clear_error(conn):
    key = submit_questionnaire(conn, "u", dict(
        investment_amount=1000, time_horizon_years=5, risk_tolerance=3, loss_reaction=3,
        primary_goal="combination", monthly_contribution=0))["user_profile_key"]
    with pytest.raises(ValueError, match="recommendation"):
        forecast_and_save(conn, key)


def test_higher_risk_profiles_have_higher_expected_return():
    mus = []
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_SQL_PATH.read_text())
    for name in ["Conservative", "Moderate", "Growth", "Aggressive"]:
        mus.append(estimate_portfolio_stats(c, MODEL_PORTFOLIOS[name])["mu"])
    assert mus == sorted(mus)
    c.close()
