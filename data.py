"""
Data fetching module using Yahoo Finance.
Includes session-level caching for sector peer data.
"""

import yfinance as yf
import pandas as pd
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
_historical_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def clear_cache():
    """Clear all caches."""
    global _sector_cache, _historical_cache
    _sector_cache = {}
    _historical_cache = {}


def _safe_get(df, label, col):
    """Safely get a value from a DataFrame, returning None if missing or NaN."""
    try:
        val = df.loc[label, col]
        if pd.notna(val):
            return float(val)
    except (KeyError, TypeError):
        pass
    return None


def _nearest_close(history: pd.DataFrame, date) -> Optional[float]:
    """Find the closest trading day's close price to a given date."""
    if history.empty:
        return None
    target = pd.Timestamp(date).tz_localize(history.index.tz) if history.index.tz and pd.Timestamp(date).tz is None else pd.Timestamp(date)
    idx = history.index.get_indexer([target], method="nearest")[0]
    if idx < 0 or idx >= len(history):
        return None
    return float(history.iloc[idx]["Close"])


def fetch_historical_kpis(ticker_str: str) -> dict[str, Optional[float]]:
    """
    Compute 5-year average KPIs from historical financial statements.
    Returns a dict with same keys as extract_kpis(), values are 5Y averages.
    """
    global _historical_cache
    now = time.time()
    cache_key = ticker_str.upper()

    if cache_key in _historical_cache:
        cached = _historical_cache[cache_key]
        if now - cached["timestamp"] < CACHE_TTL_SECONDS:
            return cached["kpis"]

    from rating import get_kpi_keys
    result = {k: None for k in get_kpi_keys()}

    try:
        t = yf.Ticker(ticker_str)
        fin = t.financials
        bs = t.balance_sheet
        hist = t.history(period="6y")

        if fin is None or fin.empty or bs is None or bs.empty or hist.empty:
            logger.warning(f"Historical data unavailable for {ticker_str}")
            _historical_cache[cache_key] = {"kpis": result, "timestamp": now}
            return result

        dates = sorted(fin.columns)

        yearly = {k: [] for k in result}
        revenues_by_date = {}

        for date in dates:
            close = _nearest_close(hist, date)
            if close is None or close <= 0:
                continue

            net_income = _safe_get(fin, "Net Income", date)
            revenue = _safe_get(fin, "Total Revenue", date)
            ebitda = _safe_get(fin, "EBITDA", date)
            equity = _safe_get(bs, "Stockholders Equity", date)
            debt = _safe_get(bs, "Total Debt", date)
            shares = _safe_get(bs, "Ordinary Shares Number", date) or _safe_get(bs, "Share Issued", date)
            current_assets = _safe_get(bs, "Current Assets", date)
            current_liab = _safe_get(bs, "Current Liabilities", date)
            cash = _safe_get(bs, "Cash Cash Equivalents And Short Term Investments", date) or _safe_get(bs, "Cash And Cash Equivalents", date)

            mcap = shares * close if shares else None

            # P/E — skip negative earnings (negative P/E averages are misleading)
            if mcap and net_income and net_income > 0:
                yearly["trailingPE"].append(mcap / net_income)

            # P/B
            if mcap and equity and equity > 0:
                yearly["priceToBook"].append(mcap / equity)

            # EV/EBITDA
            if mcap and ebitda and ebitda > 0:
                ev = mcap + (debt or 0) - (cash or 0)
                yearly["enterpriseToEbitda"].append(ev / ebitda)

            # D/E (yfinance reports as percentage-like, e.g. 81.86)
            if debt is not None and equity and equity > 0:
                yearly["debtToEquity"].append((debt / equity) * 100)

            # ROE
            if net_income is not None and equity and equity > 0:
                yearly["returnOnEquity"].append(net_income / equity)

            # Profit Margin
            if net_income is not None and revenue and revenue > 0:
                yearly["profitMargins"].append(net_income / revenue)

            # Current Ratio
            if current_assets and current_liab and current_liab > 0:
                yearly["currentRatio"].append(current_assets / current_liab)

            # Store revenue for growth calc
            if revenue:
                revenues_by_date[date] = revenue

        # Revenue Growth — YoY from sorted revenues
        sorted_dates = sorted(revenues_by_date.keys())
        for i in range(1, len(sorted_dates)):
            prev_rev = revenues_by_date[sorted_dates[i - 1]]
            curr_rev = revenues_by_date[sorted_dates[i]]
            if prev_rev and prev_rev > 0:
                yearly["revenueGrowth"].append((curr_rev - prev_rev) / prev_rev)

        # Dividend yield — sum dividends per fiscal year / close price
        try:
            divs = t.dividends
            if divs is not None and not divs.empty:
                div_tz = divs.index.tz
                for date in dates:
                    close = _nearest_close(hist, date)
                    if not close or close <= 0:
                        continue
                    d = pd.Timestamp(date)
                    if div_tz and d.tz is None:
                        d = d.tz_localize(div_tz)
                    year_start = d - pd.DateOffset(years=1)
                    mask = (divs.index >= year_start) & (divs.index <= d)
                    annual_div = divs[mask].sum()
                    if annual_div >= 0:
                        yearly["dividendYield"].append(annual_div / close)
        except Exception:
            pass

        # Average each KPI
        for key, values in yearly.items():
            if values:
                result[key] = sum(values) / len(values)

    except Exception as e:
        logger.warning(f"Failed to fetch historical KPIs for {ticker_str}: {e}")

    _historical_cache[cache_key] = {"kpis": result, "timestamp": now}
    return result


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

    # 4. Fetch historical KPI averages
    historical_averages = fetch_historical_kpis(resolved_ticker)

    # 5. Calculate rating
    rating = calculate_rating(stock_kpis, sector_averages)

    # 6. Build comparison table
    kpi_comparison = []
    for cfg in KPI_CONFIGS:
        stock_val = stock_kpis.get(cfg.key)
        sector_val = sector_averages.get(cfg.key)
        hist_val = historical_averages.get(cfg.key)

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

        kpi_score = rating["kpi_scores"].get(cfg.key, {})
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
            "kpi_score": kpi_score,
            "description": cfg.description,
            "weight_raw": cfg.weight,
            "historical_avg": format_kpi_value(cfg.key, hist_val),
            "historical_raw": hist_val,
            "negative_flag": kpi_score.get("flag"),
            "negative_flag_reason": kpi_score.get("flag_reason"),
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
