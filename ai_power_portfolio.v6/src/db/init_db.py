"""
Creates (or recreates) the SQLite warehouse from schema.sql.

Usage:
    python -m src.db.init_db            # create if not exists
    python -m src.db.init_db --reset    # drop and recreate from scratch
"""
import argparse
import sqlite3
import sys

from src.config.settings import WAREHOUSE_DB_PATH, SCHEMA_SQL_PATH


def init_db(reset: bool = False) -> None:
    WAREHOUSE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if reset and WAREHOUSE_DB_PATH.exists():
        WAREHOUSE_DB_PATH.unlink()
        print(f"Removed existing warehouse at {WAREHOUSE_DB_PATH}")

    schema_sql = SCHEMA_SQL_PATH.read_text()

    conn = sqlite3.connect(WAREHOUSE_DB_PATH)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        print(f"Warehouse initialized at {WAREHOUSE_DB_PATH}")
    except sqlite3.OperationalError as e:
        # Most common case: tables already exist from a prior run.
        print(f"Skipped init (likely already exists): {e}", file=sys.stderr)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize the AI Power Portfolio warehouse.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the database file.")
    args = parser.parse_args()
    init_db(reset=args.reset)
