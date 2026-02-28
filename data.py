"""
Data fetching module using Yahoo Finance.
Includes per-ticker KPI caching and peer group resolution via stock_db.
"""

import math

import yfinance as yf
import pandas as pd
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import logging

from sp500 import SP500_BY_SECTOR
from rating import extract_kpis, compute_sector_averages, get_kpi_keys
from sentiment import fetch_sentiment, fetch_sentiment_multi
from sentiment import clear_cache as _clear_sentiment_cache
from reddit_buzz import fetch_reddit_buzz
from reddit_buzz import clear_cache as _clear_reddit_buzz_cache
from insider_trading import fetch_insider_trading
from insider_trading import clear_cache as _clear_insider_cache
from analyst_ratings import fetch_analyst_ratings
from analyst_ratings import clear_cache as _clear_analyst_cache
from options_sentiment import fetch_options_sentiment
from options_sentiment import clear_cache as _clear_options_cache
from google_trends import fetch_google_trends
from google_trends import clear_cache as _clear_trends_cache
import stock_db
from peers import resolve_peers
from sentiment_score import compute_composite_sentiment
import peer_groups

logger = logging.getLogger(__name__)


# --- In-memory session cache ---
# Per-ticker KPI cache: { ticker: { "kpis": dict, "timestamp": float } }
_ticker_kpi_cache: dict[str, dict] = {}
# Legacy sector cache (kept for fallback when stock not in DB)
_sector_cache: dict[str, dict] = {}
_historical_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 3600  # 1 hour
PEER_FETCH_WORKERS = 10


def clear_cache():
    """Clear all caches."""
    with _cache_lock:
        _ticker_kpi_cache.clear()
        _sector_cache.clear()
        _historical_cache.clear()
    _clear_sentiment_cache()
    _clear_reddit_buzz_cache()
    _clear_insider_cache()
    _clear_analyst_cache()
    _clear_options_cache()
    _clear_trends_cache()


def _sanitize_for_json(obj):
    """Replace NaN/Inf floats with None for valid JSON serialization."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


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


def _date_str(date) -> str:
    """Convert a date/timestamp to ISO date string for sorting."""
    return str(date.date()) if hasattr(date, 'date') else str(date)


def fetch_historical_kpis(ticker_str: str) -> dict:
    """
    Compute historical KPI data from financial statements.
    Returns {"averages": {key: float|None}, "yearly": {key: [(date_str, value), ...]}}.
    """
    now = time.time()
    cache_key = ticker_str.upper()

    with _cache_lock:
        if cache_key in _historical_cache:
            cached = _historical_cache[cache_key]
            if now - cached["timestamp"] < CACHE_TTL_SECONDS:
                return cached["data"]

    keys = get_kpi_keys()
    result = {"averages": {k: None for k in keys}, "yearly": {k: [] for k in keys}}

    try:
        t = yf.Ticker(ticker_str)
        fin = t.financials
        bs = t.balance_sheet
        hist = t.history(period="6y")

        cf = None
        try:
            cf = t.cashflow
        except Exception as e:
            logger.debug(f"Cashflow unavailable for {ticker_str}: {e}")

        if fin is None or fin.empty or bs is None or bs.empty or hist.empty:
            logger.warning(f"Historical data unavailable for {ticker_str}")
            with _cache_lock:
                _historical_cache[cache_key] = {"data": result, "timestamp": now}
            return result

        dates = sorted(fin.columns)
        yearly = result["yearly"]

        revenues_by_date = {}
        net_incomes_by_date = {}
        pe_by_date = {}

        for date in dates:
            ds = _date_str(date)
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

            if net_income is not None:
                net_incomes_by_date[date] = net_income

            if mcap and net_income and net_income > 0:
                pe = mcap / net_income
                yearly["trailingPE"].append((ds, pe))
                pe_by_date[date] = pe

            if mcap and equity and equity > 0:
                yearly["priceToBook"].append((ds, mcap / equity))

            if mcap and ebitda and ebitda > 0:
                ev = mcap + (debt or 0) - (cash or 0)
                yearly["enterpriseToEbitda"].append((ds, ev / ebitda))

            if debt is not None and equity and equity > 0:
                yearly["debtToEquity"].append((ds, (debt / equity) * 100))

            if net_income is not None and equity and equity > 0:
                yearly["returnOnEquity"].append((ds, net_income / equity))

            if net_income is not None and revenue and revenue > 0:
                yearly["profitMargins"].append((ds, net_income / revenue))

            if current_assets and current_liab and current_liab > 0:
                yearly["currentRatio"].append((ds, current_assets / current_liab))

            if revenue:
                revenues_by_date[date] = revenue

            if cf is not None and not cf.empty and mcap and mcap > 0:
                fcf = _safe_get(cf, "Free Cash Flow", date)
                if fcf is not None:
                    yearly["fcfYield"].append((ds, fcf / mcap))

        sorted_rev_dates = sorted(revenues_by_date.keys())
        for i in range(1, len(sorted_rev_dates)):
            prev_rev = revenues_by_date[sorted_rev_dates[i - 1]]
            curr_rev = revenues_by_date[sorted_rev_dates[i]]
            ds = _date_str(sorted_rev_dates[i])
            if prev_rev and prev_rev > 0:
                yearly["revenueGrowth"].append((ds, (curr_rev - prev_rev) / prev_rev))

        sorted_ni_dates = sorted(net_incomes_by_date.keys())
        for i in range(1, len(sorted_ni_dates)):
            date = sorted_ni_dates[i]
            prev_date = sorted_ni_dates[i - 1]
            ni = net_incomes_by_date[date]
            prev_ni = net_incomes_by_date[prev_date]
            pe = pe_by_date.get(date)
            if pe is not None and pe > 0 and prev_ni > 0 and ni > 0:
                growth_pct = ((ni - prev_ni) / abs(prev_ni)) * 100
                if growth_pct > 0:
                    yearly["pegRatio"].append((_date_str(date), pe / growth_pct))

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
                    if annual_div > 0:
                        yearly["dividendYield"].append((_date_str(date), annual_div / close))
        except Exception as e:
            logger.debug(f"Dividend data unavailable for {ticker_str}: {e}")

        for key, values in yearly.items():
            if values:
                result["averages"][key] = sum(v for _, v in values) / len(values)

    except Exception as e:
        logger.warning(f"Failed to fetch historical KPIs for {ticker_str}: {e}")

    with _cache_lock:
        _historical_cache[cache_key] = {"data": result, "timestamp": now}
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
    except Exception as e:
        logger.debug(f"Fetch failed for {ticker}: {e}")
    return None


def get_stock_info(ticker: str) -> dict:
    """
    Fetch stock info from Yahoo Finance.
    If the bare ticker fails, tries common exchange suffixes.
    Returns info dict or raises ValueError.
    """
    clean = ticker.upper().strip()

    if not clean or len(clean) > 20 or not all(c.isalnum() or c in '.-' for c in clean):
        raise ValueError(f"Invalid ticker format: '{ticker}'")

    if "." in clean:
        info = _try_fetch(clean)
        if info:
            return info
        raise ValueError(f"Could not retrieve data for ticker '{ticker}'. Please check the symbol.")

    info = _try_fetch(clean)
    if info:
        return info

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
    return info.get("sector")


def get_stock_industry(info: dict) -> Optional[str]:
    return info.get("industry")


def get_stock_name(info: dict) -> str:
    return info.get("shortName") or info.get("longName") or "Unknown"


def fetch_ticker_kpis(ticker: str) -> Optional[dict]:
    """Fetch KPIs for a single peer ticker. Returns dict or None on failure.
    Uses per-ticker cache for reuse across different peer sets."""
    now = time.time()
    cache_key = ticker.upper().strip()

    with _cache_lock:
        if cache_key in _ticker_kpi_cache:
            cached = _ticker_kpi_cache[cache_key]
            if now - cached["timestamp"] < CACHE_TTL_SECONDS:
                return cached["kpis"]

    try:
        info = yf.Ticker(ticker).info
        if info and info.get("regularMarketPrice") is not None:
            kpis = extract_kpis(info)
            kpis["_ticker"] = ticker
            kpis["_industry"] = info.get("industry", "")
            kpis["_name"] = info.get("shortName") or info.get("longName") or ticker
            kpis["_market_cap"] = info.get("marketCap")

            with _cache_lock:
                _ticker_kpi_cache[cache_key] = {"kpis": kpis, "timestamp": now}
            return kpis
    except Exception as e:
        logger.warning(f"  Skipping {ticker}: {e}")
    return None


def _fetch_peers_kpis(peer_tickers: list[str], exclude_ticker: str = "") -> list[dict]:
    """Fetch KPIs for a list of peer tickers using per-ticker cache."""
    exclude_upper = exclude_ticker.upper().strip()
    tickers_to_fetch = [t for t in peer_tickers if t.upper().strip() != exclude_upper]

    all_kpis = []
    with ThreadPoolExecutor(max_workers=PEER_FETCH_WORKERS) as pool:
        futures = {pool.submit(fetch_ticker_kpis, t): t for t in tickers_to_fetch}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                all_kpis.append(result)

    return all_kpis


def get_sector_peers_kpis(sector: str, exclude_ticker: str = "") -> list[dict[str, Optional[float]]]:
    """
    Get KPIs for all S&P 500 stocks in the given sector.
    Legacy fallback when stock not in the stock DB.
    """
    cache_key = sector.lower().strip()
    now = time.time()

    with _cache_lock:
        if cache_key in _sector_cache:
            cached = _sector_cache[cache_key]
            if now - cached["timestamp"] < CACHE_TTL_SECONDS:
                logger.info(f"Using cached sector data for '{sector}' ({len(cached['kpis'])} peers)")
                kpis = cached["kpis"]
                if exclude_ticker:
                    return [k for k in kpis if k.get("_ticker", "").upper() != exclude_ticker.upper()]
                return kpis

    sector_tickers = SP500_BY_SECTOR.get(sector, [])
    if not sector_tickers:
        for s, tickers in SP500_BY_SECTOR.items():
            if s.lower().strip() == cache_key:
                sector_tickers = tickers
                break

    logger.info(f"Fetching sector data for '{sector}' ({len(sector_tickers)} tickers)...")
    fetch_start = time.monotonic()

    all_kpis = _fetch_peers_kpis(sector_tickers)

    with _cache_lock:
        _sector_cache[cache_key] = {
            "kpis": all_kpis,
            "timestamp": now,
        }

    fetch_ms = round((time.monotonic() - fetch_start) * 1000)
    logger.info(
        f"Cached {len(all_kpis)} peers for sector '{sector}' in {fetch_ms}ms",
        extra={"duration_ms": fetch_ms},
    )

    if exclude_ticker:
        return [k for k in all_kpis if k.get("_ticker", "").upper() != exclude_ticker.upper()]
    return all_kpis


def get_industry_peers_kpis(peers_kpis: list[dict], industry: str) -> list[dict]:
    """Filter sector peers to those in the same industry."""
    if not industry:
        return []
    industry_lower = industry.lower().strip()
    return [k for k in peers_kpis if k.get("_industry", "").lower().strip() == industry_lower]


def analyze_stock(
    ticker: str,
    peers: list[str] | None = None,
    region: str | None = None,
    ticker_aliases: list[str] | None = None,
) -> dict:
    """
    Full analysis pipeline for a single stock ticker.

    Args:
        ticker: Stock ticker symbol.
        peers: Optional custom peer list. Bypasses auto peer resolution.
        region: Optional region filter ('us' or 'europe'). None = global.

    Returns a structured dict with all data needed for the frontend.
    """
    from rating import (
        KPI_CONFIGS, extract_kpis, compute_sector_averages,
        calculate_rating, format_kpi_value, compute_sector_thresholds,
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
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")

    # 3. Resolve peers
    # Check for saved custom peers if none explicitly provided
    custom_peers = peers
    if custom_peers is None:
        saved_custom = peer_groups.get_custom_peers(resolved_ticker)
        if saved_custom:
            custom_peers = saved_custom

    # Determine if stock is in the DB; if so, use new peer system
    db_stock = stock_db.get_stock(resolved_ticker)
    use_new_peers = db_stock is not None or custom_peers is not None

    if use_new_peers:
        peer_result = resolve_peers(
            ticker=resolved_ticker,
            sector=sector,
            industry=industry,
            region=region,
            custom_peers=custom_peers,
        )
        peer_tickers = peer_result.tickers
    else:
        peer_result = None
        peer_tickers = None

    # 4. Fetch data in parallel
    with ThreadPoolExecutor(max_workers=8) as pool:
        if peer_tickers is not None:
            peers_future = pool.submit(_fetch_peers_kpis, peer_tickers, resolved_ticker)
        else:
            peers_future = pool.submit(get_sector_peers_kpis, sector, resolved_ticker)
        hist_future = pool.submit(fetch_historical_kpis, resolved_ticker)
        _sent_aliases = ticker_aliases if ticker_aliases and len(ticker_aliases) > 1 else None
        if _sent_aliases:
            sentiment_future = pool.submit(fetch_sentiment_multi, _sent_aliases, company_name)
        else:
            sentiment_future = pool.submit(fetch_sentiment, resolved_ticker, company_name)
        reddit_future = pool.submit(fetch_reddit_buzz, resolved_ticker)
        insider_future = pool.submit(fetch_insider_trading, resolved_ticker)
        analyst_future = pool.submit(fetch_analyst_ratings, resolved_ticker)
        options_future = pool.submit(fetch_options_sentiment, resolved_ticker, current_price)
        trends_future = pool.submit(fetch_google_trends, resolved_ticker)

        peers_kpis = peers_future.result()
        historical_data = hist_future.result()
        sentiment_data = sentiment_future.result()
        reddit_buzz_data = reddit_future.result()
        insider_data = insider_future.result()
        analyst_data = analyst_future.result()
        options_data = options_future.result()
        trends_data = trends_future.result()

    sector_averages = compute_sector_averages(peers_kpis)

    # Industry-level comparison (from resolved peer set)
    industry_peers = get_industry_peers_kpis(peers_kpis, industry) if industry else []
    industry_averages = compute_sector_averages(industry_peers) if len(industry_peers) >= 5 else None
    industry_peer_count = len(industry_peers)

    # Dynamic thresholds
    sector_thresholds = compute_sector_thresholds(peers_kpis)

    # 5. Unpack historical data
    historical_averages = historical_data["averages"]
    historical_yearly = historical_data["yearly"]

    # 6. Calculate rating
    rating = calculate_rating(
        stock_kpis, sector_averages,
        industry_averages=industry_averages,
        sector_thresholds=sector_thresholds,
        historical_yearly=historical_yearly,
    )

    # 7. Build comparison table
    kpi_comparison = []
    for cfg in KPI_CONFIGS:
        stock_val = stock_kpis.get(cfg.key)
        sector_val = sector_averages.get(cfg.key)
        hist_val = historical_averages.get(cfg.key)
        industry_val = industry_averages.get(cfg.key) if industry_averages else None

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
            "industry_avg": format_kpi_value(cfg.key, industry_val),
            "difference": diff_str,
            "stock_raw": stock_val,
            "sector_raw": sector_val,
            "industry_raw": industry_val,
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

    # 8. Extract short interest
    short_pct = info.get("shortPercentOfFloat")
    short_interest = {
        "available": short_pct is not None,
        "short_pct_of_float": round(short_pct * 100, 2) if short_pct is not None else None,
        "short_ratio": info.get("shortRatio"),
        "shares_short": info.get("sharesShort"),
        "shares_short_prior_month": info.get("sharesShortPriorMonth"),
        "shares_outstanding": info.get("sharesOutstanding"),
    }

    # 9. Build peer selection info
    peer_selection = None
    if peer_result:
        peer_selection = {
            "level": peer_result.level,
            "region": peer_result.region,
            "count": len(peers_kpis),
            "total_available": peer_result.total_available,
            "message": peer_result.message,
            "is_custom": peer_result.level == "custom",
            "tickers": [k.get("_ticker") for k in peers_kpis],
        }

    # 10. Build peer metadata for modal display
    peer_metadata = [
        {
            "ticker": k.get("_ticker"),
            "name": k.get("_name", k.get("_ticker", "")),
            "industry": k.get("_industry", ""),
            "market_cap": k.get("_market_cap"),
        }
        for k in peers_kpis
    ]

    composite_sentiment = compute_composite_sentiment({
        "sentiment": sentiment_data,
        "insider_trading": insider_data,
        "analyst_ratings": analyst_data,
        "options_sentiment": options_data,
    })

    return _sanitize_for_json({
        "ticker": resolved_ticker,
        "company_name": company_name,
        "current_price": current_price,
        "sector": sector,
        "industry": industry or "N/A",
        "stock_kpis": stock_kpis,
        "sector_averages": sector_averages,
        "sector_peer_count": len(peers_kpis),
        "industry_peer_count": industry_peer_count,
        "industry_comparison_active": industry_averages is not None,
        "rating": rating,
        "kpi_comparison": kpi_comparison,
        "sentiment": sentiment_data,
        "reddit_buzz": reddit_buzz_data,
        "short_interest": short_interest,
        "insider_trading": insider_data,
        "analyst_ratings": analyst_data,
        "options_sentiment": options_data,
        "google_trends": trends_data,
        "sentiment_score": composite_sentiment,
        "peer_selection": peer_selection,
        "peer_metadata": peer_metadata,
        "historical_yearly": historical_data["yearly"],
    })
