"""
Data fetching module using Yahoo Finance.
Includes session-level caching for sector peer data.
"""

import yfinance as yf
from typing import Optional
from functools import lru_cache
import time
import logging

from sp500 import SP500_TICKERS
from rating import extract_kpis, compute_sector_averages, get_kpi_keys

logger = logging.getLogger(__name__)


# --- In-memory session cache ---
# Cache structure: { sector_name: { "kpis": [...], "timestamp": float } }
_sector_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def clear_cache():
    """Clear the sector cache."""
    global _sector_cache
    _sector_cache = {}


EXCHANGE_SUFFIXES = [
    ".L",    # London
    ".TO",   # Toronto
    ".AX",   # Australia
    ".DE",   # Germany (XETRA)
    ".PA",   # Paris
    ".AS",   # Amsterdam
    ".MI",   # Milan
    ".MC",   # Madrid
    ".SW",   # Swiss
    ".HK",   # Hong Kong
    ".SI",   # Singapore
    ".KS",   # Korea
    ".TW",   # Taiwan
    ".ST",   # Stockholm
    ".CO",   # Copenhagen
    ".HE",   # Helsinki
    ".OL",   # Oslo
    ".TA",   # Tel Aviv
    ".SA",   # Sao Paulo
    ".NS",   # NSE India
    ".BO",   # BSE India
]


def _try_fetch(ticker: str) -> Optional[dict]:
    """Try fetching info for a ticker, return info dict or None."""
    try:
        info = yf.Ticker(ticker).info
        if info and info.get("regularMarketPrice") is not None:
            return info
    except Exception:
        pass
    return None


def get_stock_info(ticker: str) -> dict:
    """
    Fetch stock info from Yahoo Finance.
    If the bare ticker fails, tries common exchange suffixes.
    Returns (info_dict, resolved_ticker) or raises ValueError.
    """
    clean = ticker.upper().strip()

    # If ticker already has a suffix, just try it directly
    if "." in clean:
        info = _try_fetch(clean)
        if info:
            return info
        raise ValueError(f"Could not retrieve data for ticker '{ticker}'. Please check the symbol.")

    # Try bare ticker first
    info = _try_fetch(clean)
    if info:
        return info

    # Auto-resolve: try exchange suffixes
    logger.info(f"Bare ticker '{clean}' failed, trying exchange suffixes...")
    for suffix in EXCHANGE_SUFFIXES:
        candidate = clean + suffix
        info = _try_fetch(candidate)
        if info:
            logger.info(f"Resolved '{clean}' -> '{candidate}'")
            return info

    raise ValueError(
        f"Could not retrieve data for ticker '{ticker}'. "
        f"Tried bare ticker and {len(EXCHANGE_SUFFIXES)} exchange suffixes. "
        f"Please check the symbol or try with an explicit suffix (e.g. {ticker}.L for London)."
    )


def get_stock_sector(info: dict) -> Optional[str]:
    """Extract the sector from a Yahoo Finance info dict."""
    return info.get("sector")


def get_stock_industry(info: dict) -> Optional[str]:
    """Extract the industry from a Yahoo Finance info dict."""
    return info.get("industry")


def get_stock_name(info: dict) -> str:
    """Extract the company name from a Yahoo Finance info dict."""
    return info.get("shortName") or info.get("longName") or "Unknown"


def get_sector_peers_kpis(sector: str, exclude_ticker: str = "") -> list[dict[str, Optional[float]]]:
    """
    Get KPIs for all S&P 500 stocks in the given sector.
    Uses caching to avoid redundant API calls within a session.
    """
    global _sector_cache

    cache_key = sector.lower().strip()
    now = time.time()

    # Check cache
    if cache_key in _sector_cache:
        cached = _sector_cache[cache_key]
        if now - cached["timestamp"] < CACHE_TTL_SECONDS:
            logger.info(f"Using cached sector data for '{sector}' ({len(cached['kpis'])} peers)")
            kpis = cached["kpis"]
            if exclude_ticker:
                return [k for k in kpis if k.get("_ticker", "").upper() != exclude_ticker.upper()]
            return kpis

    # Fetch sector peers
    logger.info(f"Fetching sector data for '{sector}' from S&P 500...")
    all_kpis = []

    for ticker in SP500_TICKERS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if info and info.get("sector", "").lower().strip() == cache_key:
                kpis = extract_kpis(info)
                kpis["_ticker"] = ticker
                all_kpis.append(kpis)
                logger.info(f"  Fetched {ticker} ({len(all_kpis)} peers so far)")
        except Exception as e:
            logger.warning(f"  Skipping {ticker}: {e}")
            continue

    # Store in cache
    _sector_cache[cache_key] = {
        "kpis": all_kpis,
        "timestamp": now,
    }

    logger.info(f"Cached {len(all_kpis)} peers for sector '{sector}'")

    if exclude_ticker:
        return [k for k in all_kpis if k.get("_ticker", "").upper() != exclude_ticker.upper()]
    return all_kpis


def analyze_stock(ticker: str) -> dict:
    """
    Full analysis pipeline for a single stock ticker.

    Returns a structured dict with all data needed for the frontend:
    {
        "ticker": str,
        "company_name": str,
        "sector": str,
        "industry": str,
        "stock_kpis": dict,
        "sector_averages": dict,
        "sector_peer_count": int,
        "rating": dict (from calculate_rating),
        "kpi_comparison": [
            {
                "key": str,
                "display_name": str,
                "stock_value": str (formatted),
                "sector_avg": str (formatted),
                "difference": str (formatted),
                "stock_raw": float | None,
                "sector_raw": float | None,
                "lower_is_better": bool,
                "kpi_score": dict,
            },
            ...
        ]
    }
    """
    from rating import (
        KPI_CONFIGS, extract_kpis, compute_sector_averages,
        calculate_rating, format_kpi_value,
    )

    # 1. Fetch stock data (may auto-resolve exchange suffix)
    info = get_stock_info(ticker)
    resolved_ticker = info.get("symbol", ticker.upper().strip())
    company_name = get_stock_name(info)
    sector = get_stock_sector(info)
    industry = get_stock_industry(info)

    if not sector:
        raise ValueError(f"No sector information available for '{ticker}'.")

    # 2. Extract stock KPIs
    stock_kpis = extract_kpis(info)

    # 3. Get sector peers and compute averages
    peers_kpis = get_sector_peers_kpis(sector, exclude_ticker=resolved_ticker)
    sector_averages = compute_sector_averages(peers_kpis)

    # 4. Calculate rating
    rating = calculate_rating(stock_kpis, sector_averages)

    # 5. Build comparison table
    kpi_comparison = []
    for cfg in KPI_CONFIGS:
        stock_val = stock_kpis.get(cfg.key)
        sector_val = sector_averages.get(cfg.key)

        # Calculate difference
        if stock_val is not None and sector_val is not None:
            diff = stock_val - sector_val
            if cfg.format_as_pct:
                diff_str = f"{diff * 100:+.{cfg.format_decimals}f}%"
            else:
                diff_str = f"{diff:+.{cfg.format_decimals}f}"
        else:
            diff = None
            diff_str = "N/A"

        kpi_comparison.append({
            "key": cfg.key,
            "display_name": cfg.display_name,
            "weight": f"{cfg.weight * 100:.0f}%",
            "stock_value": format_kpi_value(cfg.key, stock_val),
            "sector_avg": format_kpi_value(cfg.key, sector_val),
            "difference": diff_str,
            "stock_raw": stock_val,
            "sector_raw": sector_val,
            "diff_raw": diff,
            "lower_is_better": cfg.lower_is_better,
            "kpi_score": rating["kpi_scores"].get(cfg.key, {}),
        })

    return {
        "ticker": resolved_ticker,
        "company_name": company_name,
        "sector": sector,
        "industry": industry or "N/A",
        "stock_kpis": stock_kpis,
        "sector_averages": sector_averages,
        "sector_peer_count": len(peers_kpis),
        "rating": rating,
        "kpi_comparison": kpi_comparison,
    }
