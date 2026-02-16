"""
Fetcher for OpenRouter usage data.

OpenRouter's API is simpler than OpenAI/Anthropic — it provides:
  - /api/v1/credits  -> total credits purchased and total usage (account-wide)

OpenRouter does NOT offer a per-day breakdown via API. The credits endpoint
gives lifetime totals only. To track daily trends, we store the total_usage
each time we fetch and calculate the daily delta from previous records.

For detailed per-generation data you'd need to store generation IDs from
your own API calls, which is outside the scope of this dashboard.
"""

import json
import requests
from datetime import date, datetime

from fetchers.base import BaseFetcher
from config import Config
import database


class OpenRouterFetcher(BaseFetcher):

    BASE_URL = "https://openrouter.ai/api/v1"

    @property
    def provider_name(self):
        return "openrouter"

    def _headers(self):
        """Build the authorization headers."""
        return {
            "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
        }

    def fetch_usage(self, start_date, end_date):
        """
        Fetch current usage snapshot from OpenRouter.

        Since OpenRouter only gives us a running total (not daily breakdown),
        we store today's cumulative total. The dashboard calculates daily
        changes by comparing consecutive records.

        Args:
            start_date: Ignored (OpenRouter doesn't support date ranges)
            end_date: Ignored

        Returns:
            List with a single record for today's cumulative usage.
        """
        # Get the current credits/usage snapshot
        response = requests.get(
            f"{self.BASE_URL}/credits",
            headers=self._headers(),
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        credits_data = data.get("data", {})
        total_credits = credits_data.get("total_credits", 0.0)
        total_usage = credits_data.get("total_usage", 0.0)

        # Calculate today's cost as delta from yesterday's cumulative total
        today_cost = self._calculate_daily_delta(total_usage)

        today = date.today().strftime("%Y-%m-%d")

        return [{
            "date": today,
            "input_tokens": 0,      # OpenRouter credits endpoint doesn't give tokens
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_usd": today_cost,
            "api_calls": 0,
            "raw_data": json.dumps({
                "total_credits": total_credits,
                "total_usage": total_usage,
                "remaining": total_credits - total_usage,
            }),
        }]

    def _calculate_daily_delta(self, current_total_usage):
        """
        Figure out how much was spent today by comparing against
        the most recent stored cumulative total.

        If this is our first fetch ever, we record 0 for today
        (we can't know how much of the total is from today).
        """
        # Look at the raw_data from our most recent stored record
        records = database.get_current_month_usage(provider="openrouter")

        if not records:
            # First time fetching — can't calculate a delta
            return 0.0

        # Get the last stored cumulative total
        last_record = records[-1]
        try:
            last_raw = json.loads(last_record.get("raw_data", "{}"))
            last_total = last_raw.get("total_usage", 0.0)
        except (json.JSONDecodeError, AttributeError):
            return 0.0

        # Today's spending is the difference
        delta = current_total_usage - last_total
        return max(0.0, delta)  # Never negative

    def test_connection(self):
        """Test the API key by calling the credits endpoint."""
        try:
            response = requests.get(
                f"{self.BASE_URL}/credits",
                headers=self._headers(),
                timeout=15,
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                remaining = data.get("total_credits", 0) - data.get("total_usage", 0)
                return {
                    "success": True,
                    "message": f"Connected to OpenRouter. "
                               f"Remaining credits: ${remaining:.2f}"
                }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": "Invalid API key."
                }
            else:
                return {
                    "success": False,
                    "message": f"HTTP {response.status_code}: {response.text[:200]}"
                }

        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}
