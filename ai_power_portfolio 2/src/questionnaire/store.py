"""
Weeks 5-6 combined — validates questionnaire answers, scores + classifies
them, and writes the result into the warehouse (dim_user + fact_user_profile).

fact_user_profile.profile_type_key is NOT NULL by schema design (Week 2),
so a submission always writes a classified row — there's no "unscored"
half-state saved to the warehouse.
"""
import sqlite3
from datetime import date

from src.questionnaire.schema import validate_answers
from src.profiling.risk_scoring import score_and_classify


def _date_key(d: date) -> int:
    return int(d.strftime("%Y%m%d"))


def _get_or_create_user(conn: sqlite3.Connection, external_id: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT user_key FROM dim_user WHERE external_id = ?", (external_id,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO dim_user (external_id) VALUES (?)", (external_id,))
    conn.commit()
    return cur.lastrowid


def _ensure_date(conn: sqlite3.Connection, d: date) -> int:
    date_key = _date_key(d)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO dim_date (date_key, full_date, day, month, quarter, year, day_of_week, is_trading_day)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(date_key) DO NOTHING
        """,
        (date_key, d.isoformat(), d.day, d.month, (d.month - 1) // 3 + 1, d.year, d.strftime("%A")),
    )
    conn.commit()
    return date_key


def _get_profile_type_key(conn: sqlite3.Connection, profile_name: str) -> int:
    cur = conn.cursor()
    cur.execute("SELECT profile_type_key FROM dim_investor_profile_type WHERE profile_name = ?", (profile_name,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Unknown profile_name '{profile_name}' — not seeded in dim_investor_profile_type")
    return row[0]


def submit_questionnaire(
    conn: sqlite3.Connection,
    external_id: str,
    answers: dict,
    submission_date: date = None,
) -> dict:
    """
    Validates answers, scores + classifies them, and inserts one row into
    fact_user_profile. Returns a summary dict including the assigned
    profile and risk score, so the caller (CLI, notebook, future web form)
    can show it to the user immediately.
    """
    validate_answers(answers)
    result = score_and_classify(answers)

    submission_date = submission_date or date.today()
    user_key = _get_or_create_user(conn, external_id)
    date_key = _ensure_date(conn, submission_date)
    profile_type_key = _get_profile_type_key(conn, result.profile_name)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO fact_user_profile (
            user_key, date_key, profile_type_key, investment_amount,
            time_horizon_years, risk_score, monthly_contribution, primary_goal, ai_explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_key,
            date_key,
            profile_type_key,
            answers["investment_amount"],
            answers["time_horizon_years"],
            result.risk_score,
            answers["monthly_contribution"],
            answers["primary_goal"],
            None,  # ai_explanation is filled in by the Week 7 LLM layer
        ),
    )
    conn.commit()

    return {
        "user_profile_key": cur.lastrowid,
        "profile_name": result.profile_name,
        "risk_score": result.risk_score,
    }
