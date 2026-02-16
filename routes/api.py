"""
REST API endpoints — the core of the dashboard.

These return JSON, making them reusable by:
  1. The web dashboard (via JavaScript fetch calls)
  2. A future iOS app (same endpoints, same JSON format)
  3. Any other client you want to build

All endpoints are prefixed with /api/v1/ for clean versioning.
"""

from flask import Blueprint, jsonify, request
from datetime import date, datetime, timedelta

import database
from config import Config
from fetchers.openai_fetcher import OpenAIFetcher
from fetchers.anthropic_fetcher import AnthropicFetcher
from fetchers.openrouter_fetcher import OpenRouterFetcher

# Create a Flask "blueprint" — a way to organize routes into modules
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


# ---- Helper: get the right fetcher for a provider name ----

def _get_fetcher(provider_name):
    """Return the fetcher instance for a given provider name."""
    fetchers = {
        "openai": OpenAIFetcher,
        "anthropic": AnthropicFetcher,
        "openrouter": OpenRouterFetcher,
    }
    fetcher_class = fetchers.get(provider_name)
    if fetcher_class:
        return fetcher_class()
    return None


def _get_all_fetchers():
    """Return fetcher instances for all enabled providers."""
    fetchers = []
    for provider in Config.enabled_providers():
        fetcher = _get_fetcher(provider)
        if fetcher:
            fetchers.append(fetcher)
    return fetchers


# ---- Endpoints ----

@api_bp.route("/status")
def status():
    """
    Health check + show which providers are configured.
    Useful for the iOS app to discover what's available.
    """
    return jsonify({
        "status": "ok",
        "enabled_providers": Config.enabled_providers(),
        "fetch_interval_minutes": Config.FETCH_INTERVAL,
        "alert_warning_usd": Config.ALERT_WARNING,
        "alert_critical_usd": Config.ALERT_CRITICAL,
    })


@api_bp.route("/summary")
def monthly_summary():
    """
    Get current month summary: total spending and tokens per provider.
    This is the main data for the dashboard overview cards.
    """
    summaries = database.get_monthly_summary()

    # Calculate grand totals across all providers
    grand_total_cost = sum(s["total_cost"] or 0 for s in summaries)
    grand_total_tokens = sum(s["total_tokens"] or 0 for s in summaries)

    return jsonify({
        "month": date.today().strftime("%Y-%m"),
        "providers": summaries,
        "totals": {
            "cost_usd": round(grand_total_cost, 4),
            "total_tokens": grand_total_tokens,
        },
        "alerts": {
            "warning_threshold": Config.ALERT_WARNING,
            "critical_threshold": Config.ALERT_CRITICAL,
            "current_spend": round(grand_total_cost, 4),
            "status": _get_alert_status(grand_total_cost),
        },
    })


@api_bp.route("/daily")
def daily_totals():
    """
    Get daily spending totals for the trend chart.
    Optional query param: ?days=30 (default 30)
    """
    num_days = request.args.get("days", 30, type=int)
    # Cap at 365 days to prevent abuse
    num_days = min(num_days, 365)

    daily = database.get_daily_totals(num_days)
    return jsonify({
        "days_requested": num_days,
        "data": daily,
    })


@api_bp.route("/usage")
def usage_range():
    """
    Get usage records for a date range.
    Query params:
      ?start=YYYY-MM-DD  (default: first of current month)
      ?end=YYYY-MM-DD    (default: today)
      ?provider=openai   (optional filter)
    """
    today = date.today()
    default_start = today.replace(day=1).strftime("%Y-%m-%d")

    start = request.args.get("start", default_start)
    end = request.args.get("end", today.strftime("%Y-%m-%d"))
    provider = request.args.get("provider", None)

    records = database.get_usage_range(start, end, provider)
    return jsonify({
        "start": start,
        "end": end,
        "provider": provider,
        "records": records,
    })


@api_bp.route("/alerts")
def active_alerts():
    """Get all unacknowledged alerts for the current month."""
    alerts = database.get_active_alerts()
    return jsonify({"alerts": alerts})


@api_bp.route("/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def acknowledge_alert(alert_id):
    """Dismiss/acknowledge an alert."""
    database.acknowledge_alert(alert_id)
    return jsonify({"success": True})


@api_bp.route("/fetch", methods=["POST"])
def trigger_fetch():
    """
    Manually trigger a data fetch from all enabled providers.
    Useful for the "Refresh" button on the dashboard.

    Optional JSON body: {"provider": "openai"} to fetch just one.
    """
    # Determine date range: current month
    today = date.today()
    start = today.replace(day=1).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    # Check if a specific provider was requested
    body = request.get_json(silent=True) or {}
    target_provider = body.get("provider")

    results = {}

    if target_provider:
        fetchers = []
        f = _get_fetcher(target_provider)
        if f:
            fetchers = [f]
    else:
        fetchers = _get_all_fetchers()

    for fetcher in fetchers:
        try:
            records = fetcher.fetch_usage(start, end)
            for record in records:
                database.upsert_usage(
                    provider=fetcher.provider_name,
                    record_date=record["date"],
                    input_tokens=record["input_tokens"],
                    output_tokens=record["output_tokens"],
                    total_tokens=record["total_tokens"],
                    cost_usd=record["cost_usd"],
                    api_calls=record["api_calls"],
                    raw_data=record["raw_data"],
                )
            results[fetcher.provider_name] = {
                "success": True,
                "records_updated": len(records),
            }
        except Exception as e:
            results[fetcher.provider_name] = {
                "success": False,
                "error": str(e),
            }

    # Check spending alerts after fetching
    _check_alerts()

    return jsonify({"results": results})


@api_bp.route("/test-connection", methods=["POST"])
def test_connections():
    """
    Test API key connections for all configured providers.
    Returns status for each provider.
    """
    body = request.get_json(silent=True) or {}
    target_provider = body.get("provider")

    results = {}

    if target_provider:
        fetcher = _get_fetcher(target_provider)
        if fetcher:
            results[target_provider] = fetcher.test_connection()
        else:
            results[target_provider] = {
                "success": False,
                "message": f"Unknown provider: {target_provider}"
            }
    else:
        for provider in Config.enabled_providers():
            fetcher = _get_fetcher(provider)
            if fetcher:
                results[provider] = fetcher.test_connection()

    return jsonify({"results": results})


# ---- Internal helpers ----

def _get_alert_status(total_spend):
    """Determine alert status based on current spending."""
    if Config.ALERT_CRITICAL > 0 and total_spend >= Config.ALERT_CRITICAL:
        return "critical"
    elif Config.ALERT_WARNING > 0 and total_spend >= Config.ALERT_WARNING:
        return "warning"
    return "ok"


def _check_alerts():
    """Check if any spending thresholds have been crossed."""
    summaries = database.get_monthly_summary()
    grand_total = sum(s["total_cost"] or 0 for s in summaries)

    # Check total spending against thresholds
    if Config.ALERT_CRITICAL > 0 and grand_total >= Config.ALERT_CRITICAL:
        database.create_alert("critical", "total", grand_total,
                              Config.ALERT_CRITICAL)

    if Config.ALERT_WARNING > 0 and grand_total >= Config.ALERT_WARNING:
        database.create_alert("warning", "total", grand_total,
                              Config.ALERT_WARNING)
