"""
Google Trends search interest indicator via pytrends (free, no auth).
Tracks 90-day search interest for a stock ticker as an attention proxy.
Spikes in search interest correlate with upcoming volume and volatility.
Note: Google rate-limits aggressively -- longer cache TTL and generous error TTL.
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)

CACHE_TTL = 7200   # 2 hours -- Google rate-limits hard
ERROR_TTL = 900    # 15 minutes on failure

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def clear_cache():
    with _cache_lock:
        _cache.clear()


def fetch_google_trends(ticker: str) -> dict | None:
    """Fetch 90-day Google Trends data for a ticker. Returns flat dict or None."""
    key = ticker.upper().strip()
    bare = key.split(".")[0] if "." in key else key
    now = time.time()

    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < entry["ttl"]:
                return entry["data"]

    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360, timeout=(5, 10))
        keyword = f"{bare} stock"
        pt.build_payload([keyword], timeframe="today 3-m")
        df = pt.interest_over_time()
    except Exception as e:
        logger.warning(f"Google Trends fetch failed for {key}: {e}")
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    if df is None or df.empty or keyword not in df.columns:
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    values = df[keyword].tolist()
    # Exclude partial data (last row may be incomplete)
    if "isPartial" in df.columns:
        partials = df["isPartial"].tolist()
        values = [v for v, p in zip(values, partials) if not p]

    if not values:
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    current = values[-1]
    avg = sum(values) / len(values)
    peak = max(values)

    # Spike detection: current > 2x trailing average
    spike = current > avg * 2 if avg > 0 else False

    # Recent trend: last 7 values vs prior 7
    recent_avg = sum(values[-7:]) / min(len(values), 7)
    prior_avg = sum(values[-14:-7]) / len(values[-14:-7]) if len(values) > 7 else avg

    if prior_avg > 0:
        trend_pct = round(((recent_avg - prior_avg) / prior_avg) * 100, 1)
    else:
        trend_pct = None

    # Sparkline data: last 30 daily values
    sparkline = values[-30:]

    result = {
        "available": True,
        "current": current,
        "average": round(avg, 1),
        "peak": peak,
        "spike": spike,
        "trend_pct": trend_pct,
        "sparkline": sparkline,
    }

    with _cache_lock:
        _cache[key] = {"data": result, "ts": now, "ttl": CACHE_TTL}

    return result
