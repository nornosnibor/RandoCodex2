"""
Configuration loader for the AI Usage Dashboard.

Reads settings from a .env file (or environment variables).
This keeps secrets out of the code and makes it easy to configure.
"""

import os
from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()


class Config:
    """Central place for all app configuration."""

    # --- API Keys ---
    # Each provider is optional. If a key is missing, that provider is skipped.
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_ORG_ID = os.getenv("OPENAI_ORG_ID", "")

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

    # --- Dashboard ---
    HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    PORT = int(os.getenv("DASHBOARD_PORT", "5555"))

    # How often (in minutes) to pull fresh usage data from provider APIs
    FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL_MINUTES", "60"))

    # --- Alerts ---
    ALERT_WARNING = float(os.getenv("ALERT_THRESHOLD_WARNING", "50.0"))
    ALERT_CRITICAL = float(os.getenv("ALERT_THRESHOLD_CRITICAL", "100.0"))

    # --- Database ---
    # SQLite file lives next to the app
    DB_PATH = os.path.join(os.path.dirname(__file__), "usage.db")

    @classmethod
    def enabled_providers(cls):
        """Return a list of provider names that have API keys configured."""
        providers = []
        if cls.OPENAI_API_KEY and not cls.OPENAI_API_KEY.startswith("sk-your"):
            providers.append("openai")
        if cls.ANTHROPIC_API_KEY and not cls.ANTHROPIC_API_KEY.startswith("sk-ant-your"):
            providers.append("anthropic")
        if cls.OPENROUTER_API_KEY and not cls.OPENROUTER_API_KEY.startswith("sk-or-your"):
            providers.append("openrouter")
        return providers
