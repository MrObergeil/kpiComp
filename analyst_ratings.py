"""
Analyst consensus indicator via Finnhub /stock/recommendation (free tier).
Tracks analyst recommendation trends (strong buy → strong sell) over time.
Revision direction (improving vs deteriorating consensus) is the key signal.
"""

import os
import time
import threading
import logging

import requests

logger = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/stock/recommendation"

CACHE_TTL = 3600
ERROR_TTL = 300

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _consensus_score(entry: dict) -> float:
    """Compute a -2 to +2 weighted consensus score from recommendation counts.
    +2 = all strong buy, -2 = all strong sell, 0 = neutral."""
    sb = entry.get("strongBuy", 0) or 0
    b = entry.get("buy", 0) or 0
    h = entry.get("hold", 0) or 0
    s = entry.get("sell", 0) or 0
    ss = entry.get("strongSell", 0) or 0
    total = sb + b + h + s + ss
    if total == 0:
        return 0.0
    return (sb * 2 + b * 1 + h * 0 + s * -1 + ss * -2) / total


def fetch_analyst_ratings(ticker: str) -> dict | None:
    """Fetch analyst recommendation trends. Returns flat dict or None."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return None

    key = ticker.upper().strip()
    bare = key.split(".")[0] if "." in key else key
    now = time.time()

    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < entry["ttl"]:
                return entry["data"]

    try:
        resp = requests.get(
            FINNHUB_URL,
            params={"symbol": bare, "token": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"Finnhub recommendation fetch failed for {key}: {e}")
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    if not isinstance(data, list) or len(data) == 0:
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    # Data comes sorted newest first
    current = data[0]
    prior = data[3] if len(data) > 3 else data[-1]  # ~3 months ago

    current_score = _consensus_score(current)
    prior_score = _consensus_score(prior)
    score_change = round(current_score - prior_score, 3)

    total = sum(current.get(k, 0) or 0 for k in ("strongBuy", "buy", "hold", "sell", "strongSell"))

    result = {
        "available": True,
        "period": current.get("period", ""),
        "strong_buy": current.get("strongBuy", 0) or 0,
        "buy": current.get("buy", 0) or 0,
        "hold": current.get("hold", 0) or 0,
        "sell": current.get("sell", 0) or 0,
        "strong_sell": current.get("strongSell", 0) or 0,
        "total_analysts": total,
        "consensus_score": round(current_score, 3),
        "prior_score": round(prior_score, 3),
        "score_change": score_change,
        "direction": "improving" if score_change > 0.05 else "deteriorating" if score_change < -0.05 else "stable",
    }

    with _cache_lock:
        _cache[key] = {"data": result, "ts": now, "ttl": CACHE_TTL}

    return result
