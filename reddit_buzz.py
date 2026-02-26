"""
Reddit social buzz indicator via ApeWisdom API (free, no auth).
Tracks mention volume & rank on Reddit stock communities (r/wallstreetbets, r/stocks, etc.).
Separate from news sentiment -- this is social attention, not bull/bear scoring.
"""

import time
import threading
import logging

import requests

logger = logging.getLogger(__name__)

APEWISDOM_URL = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/{page}"
MAX_PAGES = 20  # safety cap; usually ~12

CACHE_TTL = 3600  # 1 hour for good data
ERROR_TTL = 300   # 5 minutes for failures

_cache: dict[str, dict] | None = None  # {TICKER: entry} when populated
_cache_ts: float = 0
_cache_ok: bool = False
_refreshing: bool = False
_cache_lock = threading.Lock()


def _fetch_all_stocks() -> dict[str, dict] | None:
    """Fetch all pages from ApeWisdom. Returns {TICKER: entry} or None on failure."""
    ticker_map = {}
    for page in range(1, MAX_PAGES + 1):
        try:
            resp = requests.get(APEWISDOM_URL.format(page=page), timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"ApeWisdom fetch failed on page {page}: {e}")
            return None

        results = data.get("results", [])
        if not results:
            break

        for entry in results:
            t = entry.get("ticker", "").upper().strip()
            if t:
                ticker_map[t] = entry

        if page >= data.get("pages", 1):
            break

    return ticker_map if ticker_map else None


def _refresh_cache() -> None:
    """Refresh the global ticker map cache."""
    global _cache, _cache_ts, _cache_ok
    ticker_map = _fetch_all_stocks()
    now = time.time()

    with _cache_lock:
        if ticker_map:
            _cache = ticker_map
            _cache_ts = now
            _cache_ok = True
            logger.info(f"ApeWisdom cache refreshed: {len(ticker_map)} tickers")
        else:
            _cache = None
            _cache_ts = now
            _cache_ok = False
            logger.warning("ApeWisdom cache refresh failed")


def clear_cache():
    global _cache, _cache_ts, _cache_ok
    with _cache_lock:
        _cache = None
        _cache_ts = 0
        _cache_ok = False


def fetch_reddit_buzz(ticker: str) -> dict | None:
    """Look up Reddit buzz for a ticker. Returns flat dict or None."""
    global _cache_ts, _cache_ok, _refreshing
    key = ticker.upper().strip()
    bare = key.split(".")[0] if "." in key else key
    now = time.time()

    with _cache_lock:
        ttl = CACHE_TTL if _cache_ok else ERROR_TTL
        needs_refresh = now - _cache_ts >= ttl and not _refreshing
        if needs_refresh:
            _refreshing = True

    if needs_refresh:
        try:
            _refresh_cache()
        finally:
            with _cache_lock:
                _refreshing = False

    with _cache_lock:
        if _cache is None:
            return None
        entry = _cache.get(bare)

    if entry is None:
        return {
            "available": True,
            "found": False,
            "mentions": 0,
            "upvotes": 0,
            "rank": None,
            "rank_24h_ago": None,
            "mentions_24h_ago": 0,
            "mention_change_pct": None,
        }

    mentions = entry.get("mentions", 0) or 0
    mentions_24h = entry.get("mentions_24h_ago", 0) or 0

    if mentions_24h > 0:
        change_pct = round(((mentions - mentions_24h) / mentions_24h) * 100, 1)
    elif mentions > 0:
        change_pct = None
    else:
        change_pct = 0.0

    return {
        "available": True,
        "found": True,
        "mentions": mentions,
        "upvotes": entry.get("upvotes", 0) or 0,
        "rank": entry.get("rank"),
        "rank_24h_ago": entry.get("rank_24h_ago"),
        "mentions_24h_ago": mentions_24h,
        "mention_change_pct": change_pct,
    }
