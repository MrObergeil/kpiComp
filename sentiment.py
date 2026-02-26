"""
News sentiment & buzz indicator via Finnhub /company-news (free tier).
Computes sentiment from headline + summary keywords. Separate from the 1-10 rating.
"""

import json
import os
import re
import time
import threading
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/company-news"

CACHE_TTL = 3600        # 1 hour for good data
ERROR_TTL = 300         # 5 minutes for failures
MIN_ARTICLES = 5

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()

_TRAIN_DATA_DIR = Path(__file__).parent / "train_data"

# Keyword-based sentiment scoring (base sets)
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


def _get_effective_keywords() -> tuple[set[str], set[str]]:
    """Merge base keyword sets with persistent overrides from train_data/news_keywords.json."""
    bullish = set(_BULLISH)
    bearish = set(_BEARISH)
    try:
        overrides = json.loads((_TRAIN_DATA_DIR / "news_keywords.json").read_text())
        bullish |= set(overrides.get("bullish_add", []))
        bullish -= set(overrides.get("bullish_remove", []))
        bearish |= set(overrides.get("bearish_add", []))
        bearish -= set(overrides.get("bearish_remove", []))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return bullish, bearish


def _score_article(headline: str, summary: str, bullish: set, bearish: set) -> tuple[float, dict]:
    """Score an article from headline + summary. Headline matches weighted 2x.
    Returns (score, {"bullish": [...], "bearish": [...]})."""
    h_words = set(_WORD_RE.findall(headline.lower())) if headline else set()
    s_words = set(_WORD_RE.findall(summary.lower())) if summary else set()

    bull_matches = (h_words & bullish) | (s_words & bullish)
    bear_matches = (h_words & bearish) | (s_words & bearish)

    # Headline matches count 2x, summary-only matches count 1x
    bull_score = len(h_words & bullish) * 2 + len((s_words - h_words) & bullish)
    bear_score = len(h_words & bearish) * 2 + len((s_words - h_words) & bearish)

    matched = {"bullish": sorted(bull_matches), "bearish": sorted(bear_matches)}

    if bull_score > bear_score:
        return 1.0, matched
    if bear_score > bull_score:
        return -1.0, matched
    return 0.0, matched


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _fetch_raw_articles(ticker: str) -> list | None:
    """Fetch raw articles from Finnhub, with caching. Returns list or None."""
    api_key = os.environ.get("FINNHUB_API_KEY", "")
    if not api_key:
        return None

    key = ticker.upper().strip()
    finnhub_sym = key.split(".")[0] if "." in key else key
    now = time.time()

    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < entry["ttl"]:
                return entry.get("raw_articles")

    today = datetime.now(timezone.utc).date()
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
            _cache[key] = {"data": None, "raw_articles": None, "ts": now, "ttl": ERROR_TTL}
        return None

    if not isinstance(articles, list):
        logger.warning(f"Unexpected Finnhub response for {key}: {type(articles)}")
        with _cache_lock:
            _cache[key] = {"data": None, "raw_articles": None, "ts": now, "ttl": ERROR_TTL}
        return None

    return articles


def fetch_sentiment(ticker: str) -> dict | None:
    """Fetch company news and compute sentiment. Returns flat dict or None."""
    key = ticker.upper().strip()
    now = time.time()

    # Check for cached result
    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < entry["ttl"] and entry.get("data") is not None:
                return entry["data"]

    articles = _fetch_raw_articles(ticker)
    if articles is None:
        return None

    count = len(articles)
    sufficient = count >= MIN_ARTICLES
    bullish_kw, bearish_kw = _get_effective_keywords()

    bullish = 0
    bearish = 0
    neutral = 0
    for art in articles:
        score, _ = _score_article(art.get("headline", ""), art.get("summary", ""), bullish_kw, bearish_kw)
        if score > 0:
            bullish += 1
        elif score < 0:
            bearish += 1
        else:
            neutral += 1

    total_scored = bullish + bearish + neutral
    bull_pct = bullish / total_scored if total_scored else 0.0
    bear_pct = bearish / total_scored if total_scored else 0.0
    opinionated = bullish + bearish
    bull_bear_ratio = bullish / opinionated if opinionated else 0.5

    result = {
        "available": True,
        "sufficient_data": sufficient,
        "bullish_pct": round(bull_pct, 3),
        "bearish_pct": round(bear_pct, 3),
        "neutral_pct": round(1.0 - bull_pct - bear_pct, 3),
        "bull_bear_ratio": round(bull_bear_ratio, 3),
        "articles_this_week": count,
    }

    with _cache_lock:
        if key in _cache and _cache[key].get("raw_articles") is not None:
            _cache[key]["data"] = result
        else:
            _cache[key] = {"data": result, "raw_articles": articles, "ts": now, "ttl": CACHE_TTL}

    return result


def fetch_articles(ticker: str) -> list | None:
    """Fetch and score individual articles for the training UI.
    Returns list of scored article dicts or None."""
    articles = _fetch_raw_articles(ticker)
    if articles is None:
        return None

    bullish_kw, bearish_kw = _get_effective_keywords()
    scored = []
    for art in articles:
        headline = art.get("headline", "")
        summary = art.get("summary", "")
        score, matched = _score_article(headline, summary, bullish_kw, bearish_kw)
        scored.append({
            "headline": headline,
            "summary": summary,
            "source": art.get("source", ""),
            "url": art.get("url", ""),
            "datetime": art.get("datetime", 0),
            "score": score,
            "matched_keywords": matched,
        })

    return scored
