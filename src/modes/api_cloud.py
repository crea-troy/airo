"""
AIRO Mode: API Cloud
Monitors OpenAI / Anthropic / Groq / Together.ai API usage.
Tracks latency, cost, token rate, and errors.
No model runs locally — AIRO monitors the API connection.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Optional


PROVIDERS = {
    "openai":     {"base_url": "https://api.openai.com/v1",      "cost_per_1k": 0.005},
    "anthropic":  {"base_url": "https://api.anthropic.com/v1",   "cost_per_1k": 0.008},
    "groq":       {"base_url": "https://api.groq.com/openai/v1", "cost_per_1k": 0.0002},
    "together":   {"base_url": "https://api.together.xyz/v1",    "cost_per_1k": 0.0004},
}


@dataclass
class APIStats:
    provider: str = "openai"
    connected: bool = False
    latency_ms: float = 0.0
    tokens_per_sec: float = 0.0
    total_tokens_today: int = 0
    cost_today: float = 0.0
    daily_budget: float = 5.0
    error_count: int = 0
    last_error: str = ""
    requests_today: int = 0


class APIMonitor:
    """
    Monitors API usage by wrapping API calls.
    Usage:
        monitor = APIMonitor("openai")
        with monitor.track():
            response = openai_client.chat.completions.create(...)
        stats = monitor.stats()
    """

    def __init__(self, provider: str = "openai", daily_budget: float = 5.0):
        self.provider = provider
        self.daily_budget = daily_budget
        self._stats = APIStats(provider=provider, daily_budget=daily_budget)
        self._lock = threading.Lock()

    def record_request(self, latency_ms: float, tokens_used: int,
                       success: bool, error: str = ""):
        """Call this after every API request to update stats."""
        cost_per_1k = PROVIDERS.get(self.provider, {}).get("cost_per_1k", 0.005)
        cost = (tokens_used / 1000) * cost_per_1k

        with self._lock:
            self._stats.latency_ms = latency_ms
            self._stats.tokens_per_sec = tokens_used / max(latency_ms / 1000, 0.001)
            self._stats.total_tokens_today += tokens_used
            self._stats.cost_today += cost
            self._stats.requests_today += 1
            self._stats.connected = True
            if not success:
                self._stats.error_count += 1
                self._stats.last_error = error

    def stats(self) -> APIStats:
        with self._lock:
            return APIStats(**self._stats.__dict__)

    def budget_remaining(self) -> float:
        return max(0.0, self.daily_budget - self._stats.cost_today)

    def budget_percent_used(self) -> float:
        return min(100.0, (self._stats.cost_today / self.daily_budget) * 100)


def ping_provider(provider: str, api_key: str) -> tuple[bool, float]:
    """
    Ping the API provider and return (success, latency_ms).
    Uses a minimal request to check connectivity.
    """
    import urllib.request
    import urllib.error

    base_url = PROVIDERS.get(provider, {}).get("base_url", "")
    if not base_url:
        return False, 0.0

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        start = time.time()
        req = urllib.request.Request(
            base_url + "/models",
            headers=headers,
            method="GET"
        )
        urllib.request.urlopen(req, timeout=5)
        latency_ms = (time.time() - start) * 1000
        return True, round(latency_ms, 1)
    except Exception:
        latency_ms = (time.time() - start) * 1000
        return False, round(latency_ms, 1)
