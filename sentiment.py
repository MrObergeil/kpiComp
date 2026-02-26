"""
News sentiment & buzz indicator via Finnhub /company-news (free tier).
Computes sentiment from headline keywords. Separate from the 1-10 rating.
"""

import os
import re
import time
import threading
import logging
from datetime import datetime, timedelta

import requests

logger = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"

CACHE_TTL = 3600        # 1 hour for good data
ERROR_TTL = 300         # 5 minutes for failures
MIN_ARTICLES = 5

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

# Keyword-based sentiment scoring
_BULLISH = {
    "surge", "surges", "surging", "soar", "soars", "soaring", "rally", "rallies",
    "rallying", "jump", "jumps", "jumping", "gain", "gains", "gaining", "rise",
    "rises", "rising", "upgrade", "upgrades", "upgraded", "bull", "bullish",
    "outperform", "outperforms", "beat", "beats", "beating", "record", "high",
    "highs", "breakout", "boom", "booming", "strong", "strength", "buy",
    "growth", "grows", "growing", "profit", "profits", "profitable", "revenue",
    "upside", "optimistic", "positive", "exceed", "exceeds", "exceeded",
    "impressive", "robust", "momentum", "accelerate", "accelerates",
}

_BEARISH = {
    "crash", "crashes", "crashing", "plunge", "plunges", "plunging", "drop",
    "drops", "dropping", "fall", "falls", "falling", "decline", "declines",
    "declining", "sell", "selloff", "downgrade", "downgrades", "downgraded",
    "bear", "bearish", "underperform", "underperforms", "miss", "misses",
    "missed", "low", "lows", "weak", "weakness", "loss", "losses", "losing",
    "risk", "risks", "risky", "fear", "fears", "concern", "concerns",
    "worried", "worry", "slump", "slumps", "slumping", "cut", "cuts",
    "cutting", "layoff", "layoffs", "lawsuit", "investigation", "probe",
    "recession", "warning", "warns", "negative", "disappointing", "trouble",
}

_WORD_RE = re.compile(r"[a-z]+")


def _score_headline(headline: str) -> float:
    """Score a headline: +1 bullish, -1 bearish, 0 neutral."""
    if not headline:
        return 0.0
    words = set(_WORD_RE.findall(headline.lower()))
    bull = len(words & _BULLISH)
    bear = len(words & _BEARISH)
    if bull > bear:
        return 1.0
    if bear > bull:
        return -1.0
    return 0.0


def clear_cache():
    with _cache_lock:
        _cache.clear()


def fetch_sentiment(ticker: str) -> dict | None:
    """Fetch company news and compute sentiment. Returns flat dict or None."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return None

    key = ticker.upper().strip()
    # Finnhub uses bare tickers -- strip exchange suffixes like .L, .TO
    finnhub_sym = key.split(".")[0] if "." in key else key
    now = time.time()

    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < entry["ttl"]:
                return entry["data"]

    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)

    try:
        resp = requests.get(
            FINNHUB_URL,
            params={
                "symbol": finnhub_sym,
                "from": week_ago.isoformat(),
                "to": today.isoformat(),
                "token": api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json()
    except Exception as e:
        logger.warning(f"Finnhub news fetch failed for {key}: {e}")
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    if not isinstance(articles, list):
        logger.warning(f"Unexpected Finnhub response for {key}: {type(articles)}")
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    count = len(articles)
    sufficient = count >= MIN_ARTICLES

    # Score headlines
    bullish = 0
    bearish = 0
    neutral = 0
    for art in articles:
        s = _score_headline(art.get("headline", ""))
        if s > 0:
            bullish += 1
        elif s < 0:
            bearish += 1
        else:
            neutral += 1

    total_scored = bullish + bearish + neutral
    bull_pct = bullish / total_scored if total_scored else 0.0
    bear_pct = bearish / total_scored if total_scored else 0.0

    result = {
        "available": True,
        "sufficient_data": sufficient,
        "bullish_pct": round(bull_pct, 3),
        "bearish_pct": round(bear_pct, 3),
        "neutral_pct": round(1.0 - bull_pct - bear_pct, 3),
        "buzz_ratio": None,  # no baseline available from free API
        "articles_this_week": count,
        "weekly_avg": None,  # not available from free API
        "company_news_score": None,
        "sector_avg_bullish": None,
        "sector_avg_news_score": None,
    }

    with _cache_lock:
        _cache[key] = {"data": result, "ts": now, "ttl": CACHE_TTL}

    return result
