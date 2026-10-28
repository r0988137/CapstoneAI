"""
Week 5 — Collects questionnaire answers.

Two ways to use this, both landing on the same validated dict:
  - collect_answers_interactive(): asks questions with input(), works fine
    in a terminal or a Colab cell.
  - Build the answers dict yourself (e.g. from a future web form) and pass
    it straight to validate_answers() / submit_questionnaire().
"""
from src.questionnaire.schema import (
    RISK_TOLERANCE_SCALE,
    LOSS_REACTION_SCALE,
    PRIMARY_GOAL_OPTIONS,
    validate_answers,
)


def _ask_float(prompt: str, min_value: float = 0) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a number.")
            continue
        if value < min_value:
            print(f"Please enter a number >= {min_value}.")
            continue
        return value


def _ask_int_from_scale(prompt: str, scale: dict) -> int:
    options = "\n".join(f"  {k}. {v}" for k, v in scale.items())
    while True:
        raw = input(f"{prompt}\n{options}\nEnter a number ({min(scale)}-{max(scale)}): ").strip()
        if raw.isdigit() and int(raw) in scale:
            return int(raw)
        print(f"Please enter one of {list(scale)}.")


def _ask_choice(prompt: str, options: list) -> str:
    while True:
        raw = input(f"{prompt} ({'/'.join(options)}): ").strip().lower()
        if raw in options:
            return raw
        print(f"Please enter one of {options}.")


def collect_answers_interactive() -> dict:
    """Runs the questionnaire as a series of input() prompts. Returns validated answers."""
    print("=== AI Power Portfolio — Investor Questionnaire ===\n")

    answers = {
        "investment_amount": _ask_float("How much do you want to invest initially? $"),
        "time_horizon_years": int(_ask_float("What is your investment time horizon, in years? ", min_value=1)),
        "risk_tolerance": _ask_int_from_scale("How much risk are you comfortable taking?", RISK_TOLERANCE_SCALE),
        "loss_reaction": _ask_int_from_scale(
            "How would you react if your portfolio temporarily lost 10-20% of its value?", LOSS_REACTION_SCALE
        ),
        "primary_goal": _ask_choice("What is your main objective?", PRIMARY_GOAL_OPTIONS),
        "monthly_contribution": _ask_float("Planned monthly contribution (0 if none)? $"),
    }

    validate_answers(answers)
    return answers
