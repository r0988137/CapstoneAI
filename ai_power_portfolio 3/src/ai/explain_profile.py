"""
Week 7 - plain-language explanation of an investor profile.

Tries the LLM first; if no API key / no network / any failure, uses a
deterministic template so the workflow never breaks. The result is saved
to fact_user_profile.ai_explanation, and `source` records which path ran
("llm" or "template") so it's always clear what produced the text.
"""
import sqlite3
from typing import Tuple

from src.ai.llm import generate_text
from src.questionnaire.store import get_profile

PROFILE_BLURBS = {
    "Conservative": (
        "puts protecting your money ahead of growing it quickly. Portfolios like this lean on "
        "bonds and cash, so they usually move up and down less, but they also tend to grow more slowly."
    ),
    "Moderate": (
        "balances growth and stability. Portfolios like this mix stocks with bonds and cash, "
        "aiming for steady growth while keeping the ups and downs manageable."
    ),
    "Growth": (
        "favors long-term growth and is comfortable with noticeable ups and downs along the way. "
        "Portfolios like this hold mostly stocks, with smaller amounts of bonds and alternatives."
    ),
    "Aggressive": (
        "aims for the highest growth potential and accepts large swings in value to get there. "
        "Portfolios like this are heavy in stocks and include higher-risk assets such as crypto."
    ),
}

GOAL_TEXT = {
    "preservation": "protecting what you have",
    "income": "generating income",
    "combination": "a mix of growth and stability",
    "growth": "growing your money over time",
}

SYSTEM_PROMPT = (
    "You write short, friendly, plain-language explanations for a student-built educational "
    "investing prototype. Never promise returns, never tell the user what they must do, and "
    "never claim to be a licensed financial advisor. Write 3 to 5 sentences, no bullet points."
)


def template_explanation(profile: dict) -> str:
    name = profile["profile_name"]
    horizon = profile["time_horizon_years"]
    goal = GOAL_TEXT.get(profile["primary_goal"], profile["primary_goal"])
    year_word = "year" if horizon == 1 else "years"
    article = "an" if name[0] in "AEIOU" else "a"
    return (
        f"Based on your answers, you were classified as {article} {name} investor (risk score "
        f"{profile['risk_score']:.0f} out of 100). That profile {PROFILE_BLURBS[name]} "
        f"You told us your main goal is {goal} over about {horizon} {year_word}, which was "
        f"factored into the score. This is an educational estimate based on your answers, "
        f"not personalized financial advice."
    )


def _build_prompt(profile: dict) -> str:
    return (
        f"Explain this investor profile to the person who just completed the questionnaire.\n"
        f"Profile: {profile['profile_name']}\n"
        f"Risk score: {profile['risk_score']:.0f} / 100 (0 = most cautious, 100 = most aggressive)\n"
        f"Time horizon: {profile['time_horizon_years']} years\n"
        f"Main goal: {profile['primary_goal']}\n"
        f"Monthly contribution: ${profile['monthly_contribution']:,.0f}\n"
        f"Explain what the profile means, why their answers point to it, and end with a one-sentence "
        f"reminder that this is educational and not financial advice."
    )


def generate_explanation(profile: dict) -> Tuple[str, str]:
    """Returns (text, source) where source is 'llm' or 'template'."""
    text = generate_text(_build_prompt(profile), system=SYSTEM_PROMPT, max_tokens=350)
    if text:
        return text, "llm"
    return template_explanation(profile), "template"


def explain_and_save(conn: sqlite3.Connection, user_profile_key: int) -> dict:
    profile = get_profile(conn, user_profile_key)
    text, source = generate_explanation(profile)
    conn.execute(
        "UPDATE fact_user_profile SET ai_explanation = ? WHERE user_profile_key = ?",
        (text, user_profile_key),
    )
    conn.commit()
    return {"user_profile_key": user_profile_key, "explanation": text, "source": source}
