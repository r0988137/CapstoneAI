"""
Week 5 — Investor questionnaire definition.

This is the single source of truth for what a "questionnaire answer" is:
what fields exist, what values are valid, and what each one means. Both
the CLI/notebook collector (collect.py) and the risk-scoring logic
(src/profiling/risk_scoring.py) import from here, so the two stay in sync.
"""
import math

# Encodes "How much risk are you comfortable taking?" on a 1-5 scale.
RISK_TOLERANCE_SCALE = {
    1: "Very low — I don't want my investment to lose value",
    2: "Low — small, occasional dips are okay",
    3: "Medium — I can accept moderate ups and downs for better returns",
    4: "High — I'm comfortable with large swings for higher growth potential",
    5: "Very high — maximum growth, even with big swings",
}

# Encodes "How would you react if your portfolio temporarily lost 10-20% of its value?"
LOSS_REACTION_SCALE = {
    1: "Sell everything immediately",
    2: "Sell some to reduce risk",
    3: "Do nothing, wait it out",
    4: "Stay the course, it's temporary",
    5: "Buy more while prices are down",
}

PRIMARY_GOAL_OPTIONS = ["preservation", "income", "combination", "growth"]

# time_horizon_years is a free integer (>= 1), bucketed internally by risk_scoring.py

REQUIRED_FIELDS = {
    "investment_amount": "Initial investment amount (a positive number)",
    "time_horizon_years": "Investment time horizon in years (a positive integer)",
    "risk_tolerance": f"Risk tolerance, 1-5 — see RISK_TOLERANCE_SCALE ({list(RISK_TOLERANCE_SCALE)})",
    "loss_reaction": f"Reaction to a 10-20% loss, 1-5 — see LOSS_REACTION_SCALE ({list(LOSS_REACTION_SCALE)})",
    "primary_goal": f"Primary goal — one of {PRIMARY_GOAL_OPTIONS}",
    "monthly_contribution": "Planned monthly contribution (0 if none)",
}


# Sanity limits so absurd inputs (typos, nan/inf) are rejected instead of producing nonsense forecasts.
MAX_INVESTMENT = 1_000_000_000      # $1 billion
MAX_MONTHLY_CONTRIBUTION = 10_000_000
MAX_HORIZON_YEARS = 60


def _is_number(x) -> bool:
    """A real, finite number. Booleans (True/False) and nan/inf do not count."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _is_whole(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def validate_answers(answers: dict) -> None:
    """Raises ValueError with a clear message if anything is missing or out of range."""
    missing = [f for f in REQUIRED_FIELDS if f not in answers]
    if missing:
        raise ValueError(
            f"Missing required answers: {missing}. Each field must be provided: "
            + "; ".join(f"{k} = {v}" for k, v in REQUIRED_FIELDS.items())
        )

    if not _is_number(answers["investment_amount"]) or answers["investment_amount"] <= 0:
        raise ValueError("investment_amount must be a positive number")
    if answers["investment_amount"] > MAX_INVESTMENT:
        raise ValueError(f"investment_amount must be at most ${MAX_INVESTMENT:,}")

    if not _is_whole(answers["time_horizon_years"]) or answers["time_horizon_years"] < 1:
        raise ValueError("time_horizon_years must be a positive integer")
    if answers["time_horizon_years"] > MAX_HORIZON_YEARS:
        raise ValueError(f"time_horizon_years must be at most {MAX_HORIZON_YEARS}")

    if not _is_whole(answers["risk_tolerance"]) or answers["risk_tolerance"] not in RISK_TOLERANCE_SCALE:
        raise ValueError(f"risk_tolerance must be one of {list(RISK_TOLERANCE_SCALE)}")

    if not _is_whole(answers["loss_reaction"]) or answers["loss_reaction"] not in LOSS_REACTION_SCALE:
        raise ValueError(f"loss_reaction must be one of {list(LOSS_REACTION_SCALE)}")

    if answers["primary_goal"] not in PRIMARY_GOAL_OPTIONS:
        raise ValueError(f"primary_goal must be one of {PRIMARY_GOAL_OPTIONS}")

    if not _is_number(answers["monthly_contribution"]) or answers["monthly_contribution"] < 0:
        raise ValueError("monthly_contribution must be zero or a positive number")
    if answers["monthly_contribution"] > MAX_MONTHLY_CONTRIBUTION:
        raise ValueError(f"monthly_contribution must be at most ${MAX_MONTHLY_CONTRIBUTION:,}")
