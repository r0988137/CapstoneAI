"""
Week 6 — Turns questionnaire answers into a risk score (0-100) and an
investor profile category (Conservative / Moderate / Growth / Aggressive).

Scoring rubric (weighted average of four 1-5 inputs, rescaled to 0-100):
  - risk_tolerance   (stated comfort with risk)            weight 30%
  - loss_reaction    (how they'd react to a 10-20% drop)    weight 30%
  - time_horizon     (longer horizon -> more risk capacity) weight 25%
  - primary_goal     (growth-oriented goals score higher)   weight 15%

monthly_contribution and investment_amount don't feed the score — they're
used later by the recommendation/forecast modules, not for classification.
"""
from dataclasses import dataclass

WEIGHTS = {
    "risk_tolerance": 0.30,
    "loss_reaction": 0.30,
    "time_horizon": 0.25,
    "primary_goal": 0.15,
}

GOAL_SCORE = {
    "preservation": 1,
    "income": 2,
    "combination": 3,
    "growth": 5,
}

# Profile thresholds on the final 0-100 score.
PROFILE_THRESHOLDS = [
    (25, "Conservative"),
    (50, "Moderate"),
    (75, "Growth"),
    (101, "Aggressive"),  # catch-all upper bound
]


@dataclass
class RiskProfileResult:
    risk_score: float
    profile_name: str


def _time_horizon_score(years: int) -> int:
    """Maps years to a 1-5 capacity-for-risk score. Longer horizon = more risk capacity."""
    if years < 3:
        return 1
    if years < 5:
        return 2
    if years < 10:
        return 3
    if years < 20:
        return 4
    return 5


def compute_risk_score(answers: dict) -> float:
    """Returns a 0-100 risk score from validated questionnaire answers."""
    horizon_score = _time_horizon_score(answers["time_horizon_years"])
    goal_score = GOAL_SCORE[answers["primary_goal"]]

    weighted_avg = (
        answers["risk_tolerance"] * WEIGHTS["risk_tolerance"]
        + answers["loss_reaction"] * WEIGHTS["loss_reaction"]
        + horizon_score * WEIGHTS["time_horizon"]
        + goal_score * WEIGHTS["primary_goal"]
    )
    # weighted_avg is on a 1-5 scale (since inputs and weights are both scaled that way);
    # rescale to 0-100.
    return round(((weighted_avg - 1) / 4) * 100, 1)


def classify_profile(risk_score: float) -> str:
    for upper_bound, name in PROFILE_THRESHOLDS:
        if risk_score < upper_bound:
            return name
    return "Aggressive"


def score_and_classify(answers: dict) -> RiskProfileResult:
    score = compute_risk_score(answers)
    return RiskProfileResult(risk_score=score, profile_name=classify_profile(score))
