"""
Weeks 5-6 — Run the questionnaire interactively and save the result.

Usage:
    python -m src.questionnaire.run
    python -m src.questionnaire.run --user-id alice
"""
import argparse
import sqlite3

from src.config.settings import WAREHOUSE_DB_PATH
from src.questionnaire.collect import collect_answers_interactive
from src.questionnaire.store import submit_questionnaire

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the investor questionnaire.")
    parser.add_argument("--user-id", default="demo-user", help="External/session id for this respondent.")
    args = parser.parse_args()

    answers = collect_answers_interactive()

    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    try:
        result = submit_questionnaire(conn, args.user_id, answers)
    finally:
        conn.close()

    print("\n=== Result ===")
    print(f"Investor profile : {result['profile_name']}")
    print(f"Risk score       : {result['risk_score']} / 100")
    print(f"Saved as user_profile_key = {result['user_profile_key']}")
