import json
import os
import time
import sys
from typing import Optional, Dict, Any, List

import httpx

# FanDuel public API base for sportsbook odds
FANDUEL_API = "https://sportsbook.fanduel.com/api"

# Default headers that keep us looking like a normal browser session
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

class FanDuelError(Exception):
    pass

class FanDuelClient:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None
        self._last_request_time: Optional[float] = None
        # Minimum gap between requests in seconds; tuned after a few 429s
        self._min_gap = 0.6

    def _throttle(self) -> None:
        if self._last_request_time is not None:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._min_gap:
                time.sleep(self._min_gap - elapsed)
        self._last_request_time = time.monotonic()

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers=DEFAULT_HEADERS,
                http2=False,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        client = self._get_client()
        url = f"{FANDUEL_API}{path}"
        self._throttle()
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            raise FanDuelError("request timed out")
        except httpx.HTTPError as exc:
            raise FanDuelError(f"http error: {exc}")
        # print(f"status {resp.status_code}: {resp.text[:200]}")  # debug
        if resp.status_code == 429:
            # FanDuel doesn't always send Retry-After; default to 5s
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait = int(retry_after)
                except ValueError:
                    wait = 5
            else:
                wait = 5
            time.sleep(wait)
            self._throttle()
            resp = client.request(method, url, **kwargs)
        resp.raise_for_status()
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise FanDuelError(f"invalid json: {exc}")

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params)

    def get_events(self, sport: str) -> List[Dict[str, Any]]:
        """Fetch event list for a sport. Returns list of event dicts."""
        data = self.get("/sports", params={"sport": sport})
        # The events are nested under the sport response
        events = data.get("events", [])
        if not isinstance(events, list):
            return []
        return events

    def get_event_markets(self, event_id: str) -> List[Dict[str, Any]]:
        """Fetch all markets for a specific event."""
        data = self.get(f"/event/{event_id}/markets")
        markets = data.get("markets", [])
        if not isinstance(markets, list):
            return []
        return markets

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
