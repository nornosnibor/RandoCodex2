"""
Base class for all provider fetchers.

Each provider (OpenAI, Anthropic, OpenRouter) has different APIs,
but they all need to do the same thing: fetch usage data and store it.
This base class defines that shared interface.

Why a base class? When you add a new provider later (or build the iOS app),
you know every fetcher will have the same methods.
"""

from abc import ABC, abstractmethod


class BaseFetcher(ABC):
    """
    Abstract base class that all provider fetchers must implement.
    """

    @property
    @abstractmethod
    def provider_name(self):
        """Return the provider identifier string, e.g. 'openai'."""
        pass

    @abstractmethod
    def fetch_usage(self, start_date, end_date):
        """
        Fetch usage data from the provider's API.

        Args:
            start_date: Start date as 'YYYY-MM-DD' string
            end_date: End date as 'YYYY-MM-DD' string

        Returns:
            List of dicts, each with keys:
                - date: 'YYYY-MM-DD'
                - input_tokens: int
                - output_tokens: int
                - total_tokens: int
                - cost_usd: float
                - api_calls: int
                - raw_data: str (JSON string of the original response)
        """
        pass

    @abstractmethod
    def test_connection(self):
        """
        Test that the API key works.

        Returns:
            dict with keys:
                - success: bool
                - message: str (error message if failed)
        """
        pass
