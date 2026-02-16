"""
Fetcher for Anthropic (Claude) usage and cost data.

Uses two Anthropic Admin API endpoints:
  - /v1/organizations/cost_report          -> dollar amounts per day
  - /v1/organizations/usage_report/messages -> token counts per day

IMPORTANT: These endpoints require an Admin API key (starts with sk-ant-admin...).
Regular API keys won't work. Create one in the Anthropic Console under
Settings > Admin Keys.
"""

import json
import requests
from datetime import datetime, timedelta

from fetchers.base import BaseFetcher
from config import Config


class AnthropicFetcher(BaseFetcher):

    BASE_URL = "https://api.anthropic.com/v1/organizations"

    @property
    def provider_name(self):
        return "anthropic"

    def _headers(self):
        """Build the required headers for Anthropic's API."""
        return {
            "x-api-key": Config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def fetch_usage(self, start_date, end_date):
        """
        Fetch daily usage from Anthropic for the given date range.

        Calls both the cost report and usage report endpoints,
        then merges them by date.
        """
        # Anthropic uses ISO 8601 timestamps
        start_iso = f"{start_date}T00:00:00Z"
        # end is exclusive, so add one day
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        end_iso = end_dt.strftime("%Y-%m-%dT00:00:00Z")

        # Step 1: Fetch costs
        costs_by_date = self._fetch_costs(start_iso, end_iso)

        # Step 2: Fetch token usage
        tokens_by_date = self._fetch_tokens(start_iso, end_iso)

        # Step 3: Merge
        all_dates = set(list(costs_by_date.keys()) + list(tokens_by_date.keys()))
        results = []

        for d in sorted(all_dates):
            cost_data = costs_by_date.get(d, {})
            token_data = tokens_by_date.get(d, {})

            input_tokens = token_data.get("input_tokens", 0)
            output_tokens = token_data.get("output_tokens", 0)

            results.append({
                "date": d,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": cost_data.get("cost_usd", 0.0),
                "api_calls": 0,  # Anthropic doesn't expose request counts
                "raw_data": json.dumps({
                    "costs": cost_data,
                    "tokens": token_data,
                }),
            })

        return results

    def _fetch_costs(self, start_iso, end_iso):
        """
        Call /v1/organizations/cost_report to get dollar amounts per day.

        Returns a dict keyed by 'YYYY-MM-DD'.
        """
        costs_by_date = {}
        page = None

        while True:
            params = {
                "starting_at": start_iso,
                "ending_at": end_iso,
                "bucket_width": "1d",
            }
            if page:
                params["page"] = page

            response = requests.get(
                f"{self.BASE_URL}/cost_report",
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            for bucket in data.get("data", []):
                # Parse the ISO timestamp to get just the date
                bucket_date = bucket["starting_at"][:10]  # 'YYYY-MM-DD'

                total_cost = 0.0
                for result in bucket.get("results", []):
                    total_cost += result.get("cost_usd", 0.0)

                costs_by_date[bucket_date] = {"cost_usd": total_cost}

            if data.get("has_more"):
                page = data.get("next_page")
            else:
                break

        return costs_by_date

    def _fetch_tokens(self, start_iso, end_iso):
        """
        Call /v1/organizations/usage_report/messages to get token counts per day.

        Returns a dict keyed by 'YYYY-MM-DD'.
        """
        tokens_by_date = {}
        page = None

        while True:
            params = {
                "starting_at": start_iso,
                "ending_at": end_iso,
                "bucket_width": "1d",
            }
            if page:
                params["page"] = page

            response = requests.get(
                f"{self.BASE_URL}/usage_report/messages",
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            for bucket in data.get("data", []):
                bucket_date = bucket["starting_at"][:10]

                input_tokens = 0
                output_tokens = 0
                for result in bucket.get("results", []):
                    # Anthropic splits input into uncached + cache_read
                    input_tokens += result.get("input_tokens", 0)
                    input_tokens += result.get("cache_read_input_tokens", 0)
                    output_tokens += result.get("output_tokens", 0)

                tokens_by_date[bucket_date] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }

            if data.get("has_more"):
                page = data.get("next_page")
            else:
                break

        return tokens_by_date

    def test_connection(self):
        """
        Test the API key by making a small request to the cost report.
        """
        try:
            now = datetime.utcnow()
            yesterday = now - timedelta(days=1)

            response = requests.get(
                f"{self.BASE_URL}/cost_report",
                headers=self._headers(),
                params={
                    "starting_at": yesterday.strftime("%Y-%m-%dT00:00:00Z"),
                    "ending_at": now.strftime("%Y-%m-%dT00:00:00Z"),
                    "bucket_width": "1d",
                },
                timeout=15,
            )

            if response.status_code == 200:
                return {"success": True, "message": "Connected to Anthropic"}
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": "Invalid API key. Anthropic usage APIs require "
                               "an Admin key (starts with sk-ant-admin...)."
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": "Access denied. Your key may not have admin "
                               "permissions."
                }
            else:
                return {
                    "success": False,
                    "message": f"HTTP {response.status_code}: {response.text[:200]}"
                }

        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}
