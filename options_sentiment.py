"""
Options market sentiment via yfinance options chains (free).
Computes put/call ratio and implied volatility from nearest monthly expiration.
Options flow captures informed/leveraged money -- strong academic backing.
"""

import time
import threading
import logging
from datetime import datetime, timezone

import yfinance as yf

logger = logging.getLogger(__name__)

CACHE_TTL = 3600
ERROR_TTL = 300

_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _find_nearest_monthly(expirations: tuple) -> str | None:
    """Find the nearest expiration that's at least 7 days out (skip weeklies too close)."""
    today = datetime.now(timezone.utc).date()
    for exp in expirations:
        exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        days_out = (exp_date - today).days
        if days_out >= 7:
            return exp
    # Fallback to the nearest one if all are < 7 days
    return expirations[0] if expirations else None


def fetch_options_sentiment(ticker: str) -> dict | None:
    """Fetch options chain and compute P/C ratio + IV. Returns flat dict or None."""
    key = ticker.upper().strip()
    bare = key.split(".")[0] if "." in key else key
    now = time.time()

    with _cache_lock:
        if key in _cache:
            entry = _cache[key]
            if now - entry["ts"] < entry["ttl"]:
                return entry["data"]

    try:
        t = yf.Ticker(bare)
        expirations = t.options
        if not expirations:
            logger.warning(f"No options available for {key}")
            with _cache_lock:
                _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
            return None

        expiry = _find_nearest_monthly(expirations)
        if not expiry:
            with _cache_lock:
                _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
            return None

        chain = t.option_chain(expiry)
        calls = chain.calls
        puts = chain.puts

        # Current price for ATM detection
        info = t.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not current_price:
            with _cache_lock:
                _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
            return None

    except Exception as e:
        logger.warning(f"Options fetch failed for {key}: {e}")
        with _cache_lock:
            _cache[key] = {"data": None, "ts": now, "ttl": ERROR_TTL}
        return None

    # Aggregate put/call volume
    call_volume = calls["volume"].sum() if "volume" in calls.columns else 0
    put_volume = puts["volume"].sum() if "volume" in puts.columns else 0

    # Handle NaN
    call_volume = int(call_volume) if call_volume == call_volume else 0
    put_volume = int(put_volume) if put_volume == put_volume else 0

    pc_ratio = round(put_volume / call_volume, 3) if call_volume > 0 else None

    # ATM implied volatility (nearest strike to current price)
    atm_iv = None
    if not calls.empty:
        calls_clean = calls.dropna(subset=["impliedVolatility", "strike"])
        if not calls_clean.empty:
            atm_idx = (calls_clean["strike"] - current_price).abs().idxmin()
            atm_iv = round(calls_clean.loc[atm_idx, "impliedVolatility"] * 100, 1)

    # Open interest totals
    call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
    put_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0
    # Handle NaN
    call_oi = call_oi if call_oi == call_oi else 0
    put_oi = put_oi if put_oi == put_oi else 0

    pc_oi_ratio = round(put_oi / call_oi, 3) if call_oi > 0 else None

    result = {
        "available": True,
        "expiry": expiry,
        "call_volume": call_volume,
        "put_volume": put_volume,
        "pc_ratio": pc_ratio,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "pc_oi_ratio": pc_oi_ratio,
        "atm_iv": atm_iv,
    }

    with _cache_lock:
        _cache[key] = {"data": result, "ts": now, "ttl": CACHE_TTL}

    return result
