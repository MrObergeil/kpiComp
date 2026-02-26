"""
Insider trading indicator via Finnhub /stock/insider-transactions (free tier).
Tracks insider purchases and sales from SEC Form 4 filings.
Purchases are far more informative than sales (academic consensus).
"""

import os
import time
import threading
import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

FINNHUB_URL = "https://finnhub.io/api/v1/stock/insider-transactions"

CACHE_TTL = 3600
ERROR_TTL = 300
LOOKBACK_DAYS = 90

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def clear_cache():
    with _cache_lock:
        _cache.clear()


def fetch_insider_trading(ticker: str) -> dict | None:
    """Fetch insider transactions and compute summary. Returns flat dict or None."""
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
        payload = resp.json()
    except Exception as e:
        logger.warning(f"Finnhub insider fetch failed for {key}: {e}")
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    raw = payload.get("data")
    if not isinstance(raw, list):
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    # Filter to last N days, open-market buys (P) and sells (S)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    # Transaction codes: P = open-market purchase, S = open-market sale
    # Exclude: M (option exercise), A (grant/award), G (gift), etc.
    open_market_codes = {"P", "S"}

    buys = []
    sells = []
    for txn in raw:
        tdate = txn.get("transactionDate", "")
        code = (txn.get("transactionCode") or "").upper()
        if tdate < cutoff:
            continue
        if code not in open_market_codes:
            continue

        change = txn.get("change", 0) or 0
        entry = {
            "name": txn.get("name", "Unknown"),
            "date": tdate,
            "shares": abs(change),
            "price": txn.get("transactionPrice"),
        }

        if code == "P" or change > 0:
            buys.append(entry)
        elif code == "S" or change < 0:
            sells.append(entry)

    # Detect cluster buys: 3+ unique insiders buying within the window
    unique_buyers = {b["name"] for b in buys}
    cluster_buy = len(unique_buyers) >= 3

    # Build recent transactions list (most recent first, capped at 10)
    all_txns = []
    for b in buys:
        all_txns.append({**b, "type": "buy"})
    for s in sells:
        all_txns.append({**s, "type": "sell"})
    all_txns.sort(key=lambda x: x["date"], reverse=True)

    total_buy_value = sum((b["shares"] * b["price"]) for b in buys if b["price"])
    total_sell_value = sum((s["shares"] * s["price"]) for s in sells if s["price"])

    result = {
        "available": True,
        "buy_count": len(buys),
        "sell_count": len(sells),
        "unique_buyers": len(unique_buyers),
        "unique_sellers": len({s["name"] for s in sells}),
        "total_buy_value": round(total_buy_value, 2),
        "total_sell_value": round(total_sell_value, 2),
        "cluster_buy": cluster_buy,
        "recent_transactions": all_txns[:10],
        "lookback_days": LOOKBACK_DAYS,
    }

    with _cache_lock:
        _cache[key] = {"data": result, "ts": now, "ttl": CACHE_TTL}

    return result
