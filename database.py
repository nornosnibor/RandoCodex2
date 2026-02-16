"""
SQLite database layer for storing historical usage data.

Tables:
  - usage_records: One row per provider per day, tracking tokens and cost.
  - alerts: Stores triggered spending alerts so we don't spam duplicates.

Why SQLite? It's a single file, no server needed, and Python has built-in
support. Perfect for a lightweight local dashboard.
"""

import sqlite3
from datetime import datetime, date
from config import Config


def get_connection():
    """Open a connection to the SQLite database file."""
    conn = sqlite3.connect(Config.DB_PATH)
    # Return rows as dictionaries instead of plain tuples
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create the database tables if they don't already exist.
    Called once when the app starts up.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Main table: one row per provider per day
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            provider        TEXT NOT NULL,          -- 'openai', 'anthropic', 'openrouter'
            date            TEXT NOT NULL,           -- 'YYYY-MM-DD'
            input_tokens    INTEGER DEFAULT 0,       -- tokens sent to the model
            output_tokens   INTEGER DEFAULT 0,       -- tokens received from the model
            total_tokens    INTEGER DEFAULT 0,       -- input + output (some APIs only give total)
            cost_usd        REAL DEFAULT 0.0,        -- cost in US dollars
            api_calls       INTEGER DEFAULT 0,       -- number of API requests made
            raw_data        TEXT DEFAULT '',          -- full JSON response for debugging
            fetched_at      TEXT NOT NULL,            -- when we pulled this data
            UNIQUE(provider, date)                   -- one row per provider per day
        )
    """)

    # Alerts table: track which alerts have been sent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type      TEXT NOT NULL,           -- 'warning' or 'critical'
            provider        TEXT NOT NULL,            -- which provider or 'total'
            month           TEXT NOT NULL,            -- 'YYYY-MM'
            amount_usd      REAL NOT NULL,            -- spending amount that triggered it
            threshold_usd   REAL NOT NULL,            -- the threshold that was crossed
            created_at      TEXT NOT NULL,
            acknowledged    INTEGER DEFAULT 0         -- 1 if user dismissed it
        )
    """)

    conn.commit()
    conn.close()


def upsert_usage(provider, record_date, input_tokens, output_tokens,
                 total_tokens, cost_usd, api_calls=0, raw_data=""):
    """
    Insert or update a usage record for a given provider and date.

    Uses SQLite's INSERT OR REPLACE so that re-fetching the same day
    updates the numbers instead of creating duplicates.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO usage_records
            (provider, date, input_tokens, output_tokens, total_tokens,
             cost_usd, api_calls, raw_data, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, date) DO UPDATE SET
            input_tokens = excluded.input_tokens,
            output_tokens = excluded.output_tokens,
            total_tokens = excluded.total_tokens,
            cost_usd = excluded.cost_usd,
            api_calls = excluded.api_calls,
            raw_data = excluded.raw_data,
            fetched_at = excluded.fetched_at
    """, (
        provider,
        record_date,
        input_tokens,
        output_tokens,
        total_tokens,
        cost_usd,
        api_calls,
        raw_data,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()


def get_current_month_usage(provider=None):
    """
    Get usage records for the current month.

    Args:
        provider: If given, filter to just one provider. Otherwise return all.

    Returns:
        List of dicts with usage data.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Current month as 'YYYY-MM' prefix for date matching
    month_prefix = date.today().strftime("%Y-%m")

    if provider:
        cursor.execute("""
            SELECT * FROM usage_records
            WHERE provider = ? AND date LIKE ?
            ORDER BY date ASC
        """, (provider, f"{month_prefix}%"))
    else:
        cursor.execute("""
            SELECT * FROM usage_records
            WHERE date LIKE ?
            ORDER BY provider, date ASC
        """, (f"{month_prefix}%",))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_usage_range(start_date, end_date, provider=None):
    """
    Get usage records between two dates (inclusive).

    Args:
        start_date: 'YYYY-MM-DD' string
        end_date: 'YYYY-MM-DD' string
        provider: Optional provider filter

    Returns:
        List of dicts with usage data.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if provider:
        cursor.execute("""
            SELECT * FROM usage_records
            WHERE provider = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC
        """, (provider, start_date, end_date))
    else:
        cursor.execute("""
            SELECT * FROM usage_records
            WHERE date BETWEEN ? AND ?
            ORDER BY provider, date ASC
        """, (start_date, end_date))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_monthly_summary():
    """
    Get a summary of spending and token usage for the current month,
    grouped by provider.

    Returns:
        List of dicts like:
        [{"provider": "openai", "total_cost": 12.50, "total_tokens": 500000}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()

    month_prefix = date.today().strftime("%Y-%m")

    cursor.execute("""
        SELECT
            provider,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost,
            SUM(api_calls) as total_api_calls
        FROM usage_records
        WHERE date LIKE ?
        GROUP BY provider
        ORDER BY total_cost DESC
    """, (f"{month_prefix}%",))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_daily_totals(num_days=30):
    """
    Get daily spending totals across all providers for the last N days.
    Useful for the spending trend chart.

    Returns:
        List of dicts like:
        [{"date": "2025-01-15", "total_cost": 5.20, "total_tokens": 200000}, ...]
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            date,
            SUM(cost_usd) as total_cost,
            SUM(total_tokens) as total_tokens,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens
        FROM usage_records
        WHERE date >= date('now', ?)
        GROUP BY date
        ORDER BY date ASC
    """, (f"-{num_days} days",))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def create_alert(alert_type, provider, amount_usd, threshold_usd):
    """
    Record a spending alert if one hasn't already been created
    for this provider/month/type combination.

    Returns:
        True if a new alert was created, False if it already existed.
    """
    conn = get_connection()
    cursor = conn.cursor()

    month = date.today().strftime("%Y-%m")

    # Check if this alert already exists for this month
    cursor.execute("""
        SELECT id FROM alerts
        WHERE alert_type = ? AND provider = ? AND month = ?
    """, (alert_type, provider, month))

    if cursor.fetchone():
        conn.close()
        return False  # Already alerted

    cursor.execute("""
        INSERT INTO alerts (alert_type, provider, month, amount_usd,
                           threshold_usd, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (alert_type, provider, month, amount_usd, threshold_usd,
          datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()
    return True


def get_active_alerts():
    """Get all unacknowledged alerts for the current month."""
    conn = get_connection()
    cursor = conn.cursor()

    month = date.today().strftime("%Y-%m")

    cursor.execute("""
        SELECT * FROM alerts
        WHERE month = ? AND acknowledged = 0
        ORDER BY created_at DESC
    """, (month,))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def acknowledge_alert(alert_id):
    """Mark an alert as acknowledged/dismissed."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE alerts SET acknowledged = 1 WHERE id = ?
    """, (alert_id,))

    conn.commit()
    conn.close()
