"""
Fetcher for OpenAI usage and cost data.

Uses two OpenAI Admin API endpoints:
  - /v1/organization/costs      -> dollar amounts per day
  - /v1/organization/usage/completions -> token counts per day

IMPORTANT: These endpoints require an Admin API key, not a regular project key.
You can create one at https://platform.openai.com/settings/organization/admin-keys
"""

import json
import requests
from datetime import datetime, timedelta

from fetchers.base import BaseFetcher
from config import Config


class OpenAIFetcher(BaseFetcher):

    # Base URL for OpenAI's API
    BASE_URL = "https://api.openai.com/v1/organization"

    @property
    def provider_name(self):
        return "openai"

    def _headers(self):
        """Build the authorization headers."""
        return {
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

    def _date_to_unix(self, date_str):
        """Convert 'YYYY-MM-DD' to Unix timestamp (seconds)."""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp())

    def fetch_usage(self, start_date, end_date):
        """
        Fetch daily usage from OpenAI for the given date range.

        Calls both the costs endpoint (for dollar amounts) and the
        usage/completions endpoint (for token counts), then merges
        them by date.
        """
        start_unix = self._date_to_unix(start_date)
        # end_date is exclusive in OpenAI's API, so add one day
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        end_unix = int(end_dt.timestamp())

        # Step 1: Fetch costs (dollar amounts per day)
        costs_by_date = self._fetch_costs(start_unix, end_unix)

        # Step 2: Fetch token usage per day
        tokens_by_date = self._fetch_tokens(start_unix, end_unix)

        # Step 3: Merge costs and tokens by date
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
                "api_calls": token_data.get("num_requests", 0),
                "raw_data": json.dumps({
                    "costs": cost_data,
                    "tokens": token_data
                }),
            })

        return results

    def _fetch_costs(self, start_unix, end_unix):
        """
        Call /v1/organization/costs to get dollar amounts per day.

        Returns a dict keyed by 'YYYY-MM-DD' date strings.
        """
        costs_by_date = {}
        page = None

        while True:
            params = {
                "start_time": start_unix,
                "end_time": end_unix,
                "bucket_width": "1d",
                "limit": 180,
            }
            if page:
                params["page"] = page

            response = requests.get(
                f"{self.BASE_URL}/costs",
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            # Each bucket is one day
            for bucket in data.get("data", []):
                # Convert Unix timestamp to date string
                bucket_date = datetime.utcfromtimestamp(
                    bucket["start_time"]
                ).strftime("%Y-%m-%d")

                # Sum up all cost results in this bucket
                total_cost = 0.0
                for result in bucket.get("results", []):
                    amount = result.get("amount", {})
                    # OpenAI returns the value as a string, so cast to float
                    total_cost += float(amount.get("value", 0))

                costs_by_date[bucket_date] = {"cost_usd": total_cost}

            # Handle pagination
            if data.get("has_more"):
                page = data.get("next_page")
            else:
                break

        return costs_by_date

    def _fetch_tokens(self, start_unix, end_unix):
        """
        Call /v1/organization/usage/completions to get token counts per day.

        Returns a dict keyed by 'YYYY-MM-DD' date strings.
        """
        tokens_by_date = {}
        page = None

        while True:
            params = {
                "start_time": start_unix,
                "end_time": end_unix,
                "bucket_width": "1d",
                "limit": 180,
            }
            if page:
                params["page"] = page

            response = requests.get(
                f"{self.BASE_URL}/usage/completions",
                headers=self._headers(),
                params=params,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            for bucket in data.get("data", []):
                bucket_date = datetime.utcfromtimestamp(
                    bucket["start_time"]
                ).strftime("%Y-%m-%d")

                # Sum all results in this bucket (could be multiple models)
                input_tokens = 0
                output_tokens = 0
                num_requests = 0
                for result in bucket.get("results", []):
                    input_tokens += result.get("input_tokens", 0)
                    output_tokens += result.get("output_tokens", 0)
                    num_requests += result.get("num_model_requests", 0)

                tokens_by_date[bucket_date] = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "num_requests": num_requests,
                }

            if data.get("has_more"):
                page = data.get("next_page")
            else:
                break

        return tokens_by_date

    def test_connection(self):
        """
        Test the API key by making a small request to the costs endpoint.
        """
        try:
            # Try to fetch just today's data
            now_unix = int(datetime.utcnow().timestamp())
            yesterday_unix = now_unix - 86400

            response = requests.get(
                f"{self.BASE_URL}/costs",
                headers=self._headers(),
                params={
                    "start_time": yesterday_unix,
                    "limit": 1,
                },
                timeout=15,
            )

            if response.status_code == 200:
                return {"success": True, "message": "Connected to OpenAI"}
            elif response.status_code == 401:
                return {
                    "success": False,
                    "message": "Invalid API key. Note: OpenAI usage APIs "
                               "require an Admin API key, not a regular key."
                }
            elif response.status_code == 403:
                return {
                    "success": False,
                    "message": "Access denied. Your API key may not have "
                               "admin permissions. Create an Admin key at "
                               "platform.openai.com/settings/organization/admin-keys"
                }
            else:
                return {
                    "success": False,
                    "message": f"HTTP {response.status_code}: {response.text[:200]}"
                }

        except requests.exceptions.RequestException as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}
