"""
News sentiment & buzz indicator via Finnhub API.
Separate from the 1-10 rating -- purely informational.
"""

import os
import time
import threading
import logging

import requests

logger = logging.getLogger(__name__)

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_URL = "https://finnhub.io/api/v1/news-sentiment"

CACHE_TTL = 3600        # 1 hour for good data
ERROR_TTL = 300         # 5 minutes for failures
MIN_ARTICLES = 5

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def clear_cache():
    global _cache
    _cache = {}


def fetch_sentiment(ticker: str) -> dict | None:
    """Fetch news sentiment for a ticker from Finnhub. Returns flat dict or None."""
    if not FINNHUB_API_KEY:
        return None

    key = ticker.upper().strip()
    now = time.time()

    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < entry["ttl"]:
                return entry["data"]

    try:
        resp = requests.get(
            FINNHUB_URL,
            params={"symbol": key, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        logger.warning(f"Finnhub sentiment fetch failed for {key}: {e}")
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    buzz = raw.get("buzz", {})
    sentiment = raw.get("sentiment", {})
    articles = buzz.get("articlesInLastWeek", 0)

    result = {
        "available": True,
        "sufficient_data": articles >= MIN_ARTICLES,
        "bullish_pct": sentiment.get("bullishPercent", 0),
        "bearish_pct": sentiment.get("bearishPercent", 0),
        "buzz_ratio": buzz.get("buzz", 0),
        "articles_this_week": articles,
        "weekly_avg": buzz.get("weeklyAverage", 0),
        "company_news_score": raw.get("companyNewsScore"),
        "sector_avg_bullish": raw.get("sectorAverageBullishPercent"),
        "sector_avg_news_score": raw.get("sectorAverageNewsScore"),
    }

    with _cache_lock:
        _cache[key] = {"data": result, "ts": now, "ttl": CACHE_TTL}

    return result
