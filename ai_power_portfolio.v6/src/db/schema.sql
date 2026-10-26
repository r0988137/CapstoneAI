-- AI Power Portfolio — Data Warehouse Schema (Star Schema)
-- SQLite-compatible DDL. Portable to Postgres/MySQL with minor tweaks
-- (AUTOINCREMENT -> SERIAL/AUTO_INCREMENT).
--
-- Grain:
--   fact_market_price     : one row per (asset, date)
--   fact_user_profile     : one row per completed questionnaire submission
--   fact_recommendation   : one row per (profile, asset) allocation line
--   fact_forecast         : one row per (profile, scenario, horizon_year) projection point

PRAGMA foreign_keys = ON;

-- ============================================================
-- DIMENSION TABLES
-- ============================================================

CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,   -- YYYYMMDD
    full_date       TEXT NOT NULL UNIQUE,  -- ISO 'YYYY-MM-DD'
    day             INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    year            INTEGER NOT NULL,
    day_of_week     TEXT NOT NULL,
    is_trading_day  INTEGER NOT NULL DEFAULT 1  -- 0/1
);

CREATE TABLE dim_asset (
    asset_key       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL UNIQUE,
    asset_name      TEXT,
    asset_class     TEXT NOT NULL CHECK (asset_class IN
                        ('equity_etf', 'equity_stock', 'crypto', 'metal', 'cash')),
    currency        TEXT NOT NULL DEFAULT 'USD',
    data_source     TEXT NOT NULL DEFAULT 'yfinance'
);

CREATE TABLE dim_user (
    user_key        INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id     TEXT UNIQUE,           -- session id / anonymized user id
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE dim_investor_profile_type (
    profile_type_key INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name      TEXT NOT NULL UNIQUE CHECK (profile_name IN
                        ('Conservative', 'Moderate', 'Growth', 'Aggressive')),
    description       TEXT
);

CREATE TABLE dim_scenario (
    scenario_key    INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_name   TEXT NOT NULL UNIQUE CHECK (scenario_name IN
                        ('conservative', 'expected', 'optimistic')),
    description     TEXT
);

-- ============================================================
-- FACT TABLES
-- ============================================================

-- Populated by the Week 3 ETL pipeline.
CREATE TABLE fact_market_price (
    market_price_key INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key          INTEGER NOT NULL REFERENCES dim_date(date_key),
    asset_key         INTEGER NOT NULL REFERENCES dim_asset(asset_key),
    open              REAL,
    high              REAL,
    low               REAL,
    close             REAL,
    adj_close         REAL,
    volume            INTEGER,
    UNIQUE (date_key, asset_key)
);

-- Populated by the Week 5–6 questionnaire + profiling modules.
CREATE TABLE fact_user_profile (
    user_profile_key   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key           INTEGER NOT NULL REFERENCES dim_user(user_key),
    date_key           INTEGER NOT NULL REFERENCES dim_date(date_key),
    profile_type_key   INTEGER NOT NULL REFERENCES dim_investor_profile_type(profile_type_key),
    investment_amount  REAL NOT NULL,
    time_horizon_years INTEGER NOT NULL,
    risk_score         REAL,
    monthly_contribution REAL DEFAULT 0,
    primary_goal       TEXT,          -- growth / income / preservation / combination
    ai_explanation     TEXT           -- LLM-generated plain-language explanation
);

-- Populated by the Week 8 portfolio recommendation engine.
CREATE TABLE fact_recommendation (
    recommendation_key INTEGER PRIMARY KEY AUTOINCREMENT,
    user_profile_key    INTEGER NOT NULL REFERENCES fact_user_profile(user_profile_key),
    asset_key           INTEGER NOT NULL REFERENCES dim_asset(asset_key),
    allocation_pct       REAL NOT NULL CHECK (allocation_pct >= 0 AND allocation_pct <= 100),
    rationale            TEXT           -- optional AI-generated per-asset rationale
);

-- Populated by the Week 10 forecasting engine.
CREATE TABLE fact_forecast (
    forecast_key        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_profile_key     INTEGER NOT NULL REFERENCES fact_user_profile(user_profile_key),
    scenario_key         INTEGER NOT NULL REFERENCES dim_scenario(scenario_key),
    horizon_year          INTEGER NOT NULL,      -- 1, 2, 3, ... N years out
    projected_value       REAL NOT NULL,
    assumed_annual_return REAL,
    UNIQUE (user_profile_key, scenario_key, horizon_year)
);

-- ============================================================
-- SEED DATA (static dimensions)
-- ============================================================

INSERT INTO dim_investor_profile_type (profile_name, description) VALUES
    ('Conservative', 'Prioritizes capital preservation; low volatility tolerance'),
    ('Moderate',      'Balanced growth and stability'),
    ('Growth',        'Favors long-term growth; tolerates moderate volatility'),
    ('Aggressive',    'Maximizes growth potential; high volatility tolerance');

INSERT INTO dim_scenario (scenario_name, description) VALUES
    ('conservative', 'Below-average historical return assumption'),
    ('expected',     'Average historical return assumption'),
    ('optimistic',   'Above-average historical return assumption');
