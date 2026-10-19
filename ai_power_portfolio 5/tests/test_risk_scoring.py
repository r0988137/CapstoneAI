"""Tests for the Week 6 risk-scoring rubric."""
import pytest

from src.profiling.risk_scoring import compute_risk_score, classify_profile, score_and_classify


def _answers(**overrides):
    base = {
        "risk_tolerance": 3,
        "loss_reaction": 3,
        "time_horizon_years": 8,
        "primary_goal": "combination",
    }
    base.update(overrides)
    return base


def test_most_conservative_inputs_score_low():
    answers = _answers(risk_tolerance=1, loss_reaction=1, time_horizon_years=1, primary_goal="preservation")
    score = compute_risk_score(answers)
    assert score == 0.0
    assert classify_profile(score) == "Conservative"


def test_most_aggressive_inputs_score_high():
    answers = _answers(risk_tolerance=5, loss_reaction=5, time_horizon_years=25, primary_goal="growth")
    score = compute_risk_score(answers)
    assert score == 100.0
    assert classify_profile(score) == "Aggressive"


def test_middle_of_the_road_inputs_score_moderate():
    answers = _answers()
    score = compute_risk_score(answers)
    assert 25 <= score < 75  # should land in Moderate or Growth, not the extremes


@pytest.mark.parametrize("score,expected", [
    (0, "Conservative"),
    (24.9, "Conservative"),
    (25, "Moderate"),
    (49.9, "Moderate"),
    (50, "Growth"),
    (74.9, "Growth"),
    (75, "Aggressive"),
    (100, "Aggressive"),
])
def test_classify_profile_thresholds(score, expected):
    assert classify_profile(score) == expected


def test_longer_horizon_increases_score_all_else_equal():
    short = compute_risk_score(_answers(time_horizon_years=1))
    long = compute_risk_score(_answers(time_horizon_years=25))
    assert long > short


def test_score_and_classify_returns_both():
    result = score_and_classify(_answers(risk_tolerance=5, loss_reaction=5, time_horizon_years=25, primary_goal="growth"))
    assert result.risk_score == 100.0
    assert result.profile_name == "Aggressive"
