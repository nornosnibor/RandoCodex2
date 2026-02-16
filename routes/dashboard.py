"""
Web dashboard route — serves the HTML page.

This is intentionally minimal. The dashboard is a single HTML page
that calls the /api/v1/ endpoints via JavaScript. This keeps the
frontend decoupled from the backend, which matters when you build
the iOS app (it'll call the same API endpoints).
"""

from flask import Blueprint, render_template

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    """Serve the main dashboard page."""
    return render_template("dashboard.html")
