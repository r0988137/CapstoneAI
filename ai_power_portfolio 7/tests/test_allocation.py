"""Week 8 tests: model portfolios and saving recommendations."""
import sqlite3

import pytest

from src.config.settings import SCHEMA_SQL_PATH, TICKER_UNIVERSE
from src.portfolio.allocation import (
    MODEL_PORTFOLIOS, CASH_TICKER, target_allocation, recommend_and_save, get_recommendation,
)
from src.questionnaire.store import submit_questionnaire


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_SQL_PATH.read_text())
    yield c
    c.close()


def _profile_key(conn, **kw):
    answers = dict(investment_amount=10000, time_horizon_years=10, risk_tolerance=3,
                   loss_reaction=3, primary_goal="combination", monthly_contribution=0)
    answers.update(kw)
    return submit_questionnaire(conn, "u", answers)["user_profile_key"]


@pytest.mark.parametrize("name", list(MODEL_PORTFOLIOS))
def test_every_model_portfolio_sums_to_100(name):
    assert sum(MODEL_PORTFOLIOS[name].values()) == 100


def test_model_portfolios_cover_whole_universe_plus_cash():
    tickers = {t for t, _, _ in TICKER_UNIVERSE} | {CASH_TICKER}
    for alloc in MODEL_PORTFOLIOS.values():
        assert set(alloc) == tickers


def test_riskier_profiles_hold_more_crypto_and_less_cash():
    crypto = lambda n: MODEL_PORTFOLIOS[n]["BTC-USD"] + MODEL_PORTFOLIOS[n]["ETH-USD"]
    order = ["Conservative", "Moderate", "Growth", "Aggressive"]
    assert [crypto(n) for n in order] == sorted(crypto(n) for n in order)
    cash = [MODEL_PORTFOLIOS[n][CASH_TICKER] for n in order]
    assert cash == sorted(cash, reverse=True)


def test_short_horizon_removes_crypto_and_still_sums_to_100():
    alloc = target_allocation("Aggressive", 2)
    assert alloc["BTC-USD"] == 0 and alloc["ETH-USD"] == 0
    assert alloc["QQQ"] == MODEL_PORTFOLIOS["Aggressive"]["QQQ"] / 2
    assert sum(alloc.values()) == 100


def test_long_horizon_keeps_model_portfolio_unchanged():
    assert target_allocation("Growth", 10) == MODEL_PORTFOLIOS["Growth"]


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        target_allocation("Reckless", 10)


def test_recommend_and_save_writes_rows_and_amounts(conn):
    key = _profile_key(conn, risk_tolerance=5, loss_reaction=5, time_horizon_years=25, primary_goal="growth")
    rows = recommend_and_save(conn, key)
    assert sum(r["allocation_pct"] for r in rows) == 100
    assert sum(r["amount"] for r in rows) == pytest.approx(10000)
    saved = get_recommendation(conn, key)
    assert len(saved) == len(rows)
    assert any(t == CASH_TICKER and cls == "cash" for t, cls, _ in saved)


def test_recommend_and_save_is_idempotent(conn):
    key = _profile_key(conn)
    recommend_and_save(conn, key)
    first = get_recommendation(conn, key)
    recommend_and_save(conn, key)
    assert get_recommendation(conn, key) == first
