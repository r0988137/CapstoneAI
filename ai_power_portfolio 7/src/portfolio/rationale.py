"""
Week 13 - "why does this portfolio match my goals and risk tolerance?"

The proposal asks for a clear explanation connecting the portfolio to the user's
goals, horizon and risk level. This builds it from the saved profile + allocation:
  - a deterministic template (always available, always consistent with the numbers), or
  - the LLM, if an API key is set (it is given the exact numbers, so it can't invent them).
`source` records which one produced the text, same as the profile explanation.
"""
from typing import List, Tuple

from src.ai.llm import generate_text
from src.portfolio.allocation import CASH_TICKER, SHORT_HORIZON_YEARS

ASSET_GROUPS = {
    "Stocks / ETFs": ["VTI", "VXUS", "QQQ"],
    "Bonds": ["BND"],
    "Crypto": ["BTC-USD", "ETH-USD"],
    "Gold / silver": ["GLD", "SLV"],
    "Cash": [CASH_TICKER],
}

GOAL_FIT = {
    "preservation": "Since your main goal is protecting what you have, the portfolio keeps a meaningful share in lower-risk holdings.",
    "income": "Since your main goal is income, the portfolio leans on steadier holdings rather than only chasing growth.",
    "combination": "Since you want a mix of growth and stability, the portfolio spreads money between growth assets and steadier ones.",
    "growth": "Since your main goal is growth, most of the money sits in assets with higher long-term growth potential.",
}

SYSTEM_PROMPT = (
    "You explain a model investment portfolio to a user in a student-built educational prototype. "
    "Use ONLY the numbers given. Never promise returns, never tell the user what they must do, "
    "never claim to be a licensed financial advisor. Write 4 to 6 sentences, no bullet points."
)


def group_weights(allocation: List[dict]) -> dict:
    """{group name: percent} for the groups that have money in them."""
    pct = {a["ticker"]: a["allocation_pct"] for a in allocation}
    out = {}
    for group, tickers in ASSET_GROUPS.items():
        total = sum(pct.get(t, 0) for t in tickers)
        if total > 0:
            out[group] = total
    return out


def _weights_text(weights: dict) -> str:
    return ", ".join(f"{g} {w:.0f}%" for g, w in sorted(weights.items(), key=lambda kv: -kv[1]))


def template_rationale(profile: dict, allocation: List[dict]) -> str:
    weights = group_weights(allocation)
    article = "an" if profile["profile_name"][0] in "AEIOU" else "a"
    parts = [
        f"Your portfolio is split as: {_weights_text(weights)}.",
        f"That mix matches {article} {profile['profile_name']} profile (risk score {profile['risk_score']:.0f} out of 100): "
        f"the higher the score, the more of the money goes to higher-growth, higher-swing assets.",
        GOAL_FIT.get(profile["primary_goal"], ""),
    ]
    horizon = profile["time_horizon_years"]
    if horizon < SHORT_HORIZON_YEARS:
        parts.append(
            f"Because your time horizon is only {horizon} year(s), crypto was moved to cash and the technology tilt was "
            f"reduced, since there is little time to recover from a market drop."
        )
    elif horizon >= 10:
        parts.append(f"With a long horizon of {horizon} years, there is more time to ride out market ups and downs.")
    crypto = weights.get("Crypto", 0)
    if crypto:
        parts.append(f"Crypto is limited to {crypto:.0f}% because it can swing sharply in value.")
    parts.append("This is an educational model portfolio, not personalized financial advice.")
    return " ".join(p for p in parts if p)


def generate_rationale(profile: dict, allocation: List[dict]) -> Tuple[str, str]:
    """Returns (text, source) where source is 'llm' or 'template'."""
    weights = group_weights(allocation)
    holdings = ", ".join("{} {:.0f}%".format(a["ticker"], a["allocation_pct"]) for a in allocation)
    prompt = (
        f"Explain why this portfolio fits the user.\n"
        f"Profile: {profile['profile_name']} (risk score {profile['risk_score']:.0f}/100)\n"
        f"Main goal: {profile['primary_goal']}\nTime horizon: {profile['time_horizon_years']} years\n"
        f"Portfolio by group: {_weights_text(weights)}\n"
        f"Holdings: {holdings}\n"
        f"Short-horizon rule applied: {'yes' if profile['time_horizon_years'] < SHORT_HORIZON_YEARS else 'no'} "
        f"(under {SHORT_HORIZON_YEARS} years moves crypto to cash).\n"
        f"Connect the mix to their risk level, goal and horizon."
    )
    text = generate_text(prompt, system=SYSTEM_PROMPT, max_tokens=350)
    if text:
        return text, "llm"
    return template_rationale(profile, allocation), "template"
