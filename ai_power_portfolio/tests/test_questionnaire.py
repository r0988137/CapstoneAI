"""Tests for the Week 5 questionnaire validation and the Weeks 5-6 storage flow."""
import sqlite3

import pytest

from src.config.settings import SCHEMA_SQL_PATH
from src.questionnaire.schema import validate_answers
from src.questionnaire.store import submit_questionnaire


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA_SQL_PATH.read_text())
    yield connection
    connection.close()


def _valid_answers(**overrides):
    base = {
        "investment_amount": 10000,
        "time_horizon_years": 10,
        "risk_tolerance": 3,
        "loss_reaction": 3,
        "primary_goal": "combination",
        "monthly_contribution": 200,
    }
    base.update(overrides)
    return base


def test_validate_answers_accepts_valid_input():
    validate_answers(_valid_answers())  # should not raise


def test_validate_answers_rejects_missing_field():
    answers = _valid_answers()
    del answers["risk_tolerance"]
    with pytest.raises(ValueError, match="Missing required answers"):
        validate_answers(answers)


def test_validate_answers_rejects_negative_investment():
    with pytest.raises(ValueError, match="investment_amount"):
        validate_answers(_valid_answers(investment_amount=-100))


def test_validate_answers_rejects_bad_risk_tolerance():
    with pytest.raises(ValueError, match="risk_tolerance"):
        validate_answers(_valid_answers(risk_tolerance=9))


def test_validate_answers_rejects_bad_goal():
    with pytest.raises(ValueError, match="primary_goal"):
        validate_answers(_valid_answers(primary_goal="yolo"))


def test_submit_questionnaire_writes_row_and_returns_profile(conn):
    result = submit_questionnaire(conn, "test-user-1", _valid_answers())
    assert result["profile_name"] in ("Conservative", "Moderate", "Growth", "Aggressive")
    assert 0 <= result["risk_score"] <= 100

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM fact_user_profile")
    assert cur.fetchone()[0] == 1


def test_submit_questionnaire_reuses_existing_user(conn):
    submit_questionnaire(conn, "same-user", _valid_answers())
    submit_questionnaire(conn, "same-user", _valid_answers(investment_amount=5000))

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM dim_user WHERE external_id = 'same-user'")
    assert cur.fetchone()[0] == 1  # one user row, not two

    cur.execute("SELECT COUNT(*) FROM fact_user_profile")
    assert cur.fetchone()[0] == 2  # but two profile submissions


def test_submit_questionnaire_rejects_invalid_answers(conn):
    with pytest.raises(ValueError):
        submit_questionnaire(conn, "test-user-2", _valid_answers(primary_goal="invalid"))
