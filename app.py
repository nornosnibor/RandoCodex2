"""
AI Usage Dashboard — Main Application

This is the entry point. It:
  1. Initializes the SQLite database
  2. Sets up the Flask web server
  3. Registers the API and dashboard routes
  4. Starts a background scheduler to fetch data periodically

Run with:  python app.py
"""

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date
import atexit

from config import Config
from database import init_db, upsert_usage
from routes.api import api_bp, _get_all_fetchers, _check_alerts
from routes.dashboard import dashboard_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Register route blueprints
    app.register_blueprint(api_bp)        # /api/v1/...
    app.register_blueprint(dashboard_bp)  # /

    return app


def scheduled_fetch():
    """
    Background job: fetch usage data from all enabled providers.
    Runs on the interval defined in FETCH_INTERVAL_MINUTES.
    """
    print("[Scheduler] Fetching usage data from all providers...")

    today = date.today()
    start = today.replace(day=1).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    for fetcher in _get_all_fetchers():
        try:
            records = fetcher.fetch_usage(start, end)
            for record in records:
                upsert_usage(
                    provider=fetcher.provider_name,
                    record_date=record["date"],
                    input_tokens=record["input_tokens"],
                    output_tokens=record["output_tokens"],
                    total_tokens=record["total_tokens"],
                    cost_usd=record["cost_usd"],
                    api_calls=record["api_calls"],
                    raw_data=record["raw_data"],
                )
            print(f"  [{fetcher.provider_name}] Updated {len(records)} records")
        except Exception as e:
            print(f"  [{fetcher.provider_name}] Error: {e}")

    # Check spending alerts after each fetch
    _check_alerts()
    print("[Scheduler] Fetch complete.")


def start_scheduler():
    """Start the background scheduler for periodic data fetching."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduled_fetch,
        trigger="interval",
        minutes=Config.FETCH_INTERVAL,
        id="usage_fetcher",
    )
    scheduler.start()
    print(f"[Scheduler] Will fetch data every {Config.FETCH_INTERVAL} minutes")

    # Shut down the scheduler when the app exits
    atexit.register(lambda: scheduler.shutdown())

    return scheduler


# ---- Main ----

if __name__ == "__main__":
    # Step 1: Create database tables if they don't exist
    print("Initializing database...")
    init_db()

    # Step 2: Create the Flask app
    app = create_app()

    # Step 3: Start the background fetcher
    start_scheduler()

    # Step 4: Show startup info
    providers = Config.enabled_providers()
    print(f"\nEnabled providers: {providers if providers else '(none — add API keys to .env)'}")
    print(f"Dashboard: http://localhost:{Config.PORT}")
    print(f"API docs:  http://localhost:{Config.PORT}/api/v1/status")
    print(f"\nAccess from other devices: http://<your-ip>:{Config.PORT}\n")

    # Step 5: Run the web server
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=False,  # Set True during development for auto-reload
    )
