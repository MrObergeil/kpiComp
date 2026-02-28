#!/usr/bin/env python3
"""
Build data/stocks.json — enriched stock database for peer comparison.

Covers index constituents: S&P 500, S&P 400, S&P 600, NASDAQ-100, Dow 30,
FTSE 100, DAX 40, Euro Stoxx 50, Russell 2000.
Seeds names from data/tickers.json, enriches via yfinance (sector, industry, marketCap).

Usage: python scripts/build_stock_db.py
Output: data/stocks.json (~3000+ stocks, keyed by ticker)
Runtime: ~90-120 min (yfinance rate limits)
"""

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from logging_config import setup_logging

import yfinance as yf

logger = logging.getLogger(__name__)

OUTPUT_PATH = ROOT / "data" / "stocks.json"
TICKERS_PATH = ROOT / "data" / "tickers.json"

# --- Index constituent lists ---

# NASDAQ-100 (as of early 2026)
NASDAQ_100 = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR",
    "CCEP", "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO",
    "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DLTR", "DXCM", "EA", "EXC",
    "FANG", "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX",
    "ILMN", "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU",
    "MAR", "MCHP", "MDB", "MDLZ", "MELI", "META", "MNST", "MRNA", "MRVL", "MSFT",
    "MU", "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR",
    "PDD", "PEP", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SMCI", "SNPS",
    "TEAM", "TMUS", "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY",
    "XEL", "ZS",
]

# Dow Jones Industrial Average 30
DOW_30 = [
    "AMGN", "AMZN", "AAPL", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "DOW",
    "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO", "MCD", "MMM",
    "MRK", "MSFT", "NKE", "PG", "SHW", "TRV", "UNH", "V", "VZ", "WMT",
]

EU_SUFFIX_REGION = {
    ".L": "Europe", ".IL": "Europe",
    ".DE": "Europe", ".F": "Europe",
    ".PA": "Europe", ".AS": "Europe",
    ".BR": "Europe", ".LS": "Europe",
    ".MC": "Europe", ".MI": "Europe",
    ".ST": "Europe", ".CO": "Europe",
    ".HE": "Europe", ".OL": "Europe",
    ".VI": "Europe", ".SW": "Europe",
    ".IR": "Europe", ".WA": "Europe",
}


def detect_region(ticker: str) -> str:
    if "." in ticker:
        suffix = ticker[ticker.rindex("."):]
        if suffix in EU_SUFFIX_REGION:
            return "Europe"
    return "US"


def load_tickers_json() -> dict[str, dict]:
    """Load existing tickers.json for name/exchange seeding."""
    if not TICKERS_PATH.exists():
        return {}
    with open(TICKERS_PATH) as f:
        data = json.load(f)
    return {item["t"]: item for item in data}


def get_sp500_tickers() -> list[str]:
    from sp500 import SP500_TICKERS
    return SP500_TICKERS


def _scrape_wikipedia_tickers(url: str, label: str) -> list[str]:
    """Scrape ticker symbols from a Wikipedia S&P index table."""
    import pandas as pd
    import requests

    resp = requests.get(url, headers={"User-Agent": "stock-db-builder/1.0"})
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    df = tables[0]
    tickers = df["Symbol"].dropna().str.strip().tolist()
    logger.info("%s: %d constituents", label, len(tickers))
    return tickers


def get_sp400_tickers() -> list[str]:
    return _scrape_wikipedia_tickers(
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "S&P 400",
    )


def get_sp600_tickers() -> list[str]:
    return _scrape_wikipedia_tickers(
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
        "S&P 600",
    )


def get_eu_index_tickers() -> dict[str, list[str]]:
    """Get EU index constituents via pytickersymbols."""
    try:
        from pytickersymbols import PyTickerSymbols
    except ImportError:
        logger.warning("pytickersymbols not installed, skipping pytickersymbols indices")
        return {}

    pts = PyTickerSymbols()
    index_map = {
        "FTSE 100": "ftse100",
        "DAX": "dax40",
    }

    result = {}
    for index_name, slug in index_map.items():
        tickers = []
        try:
            for stock in pts.get_stocks_by_index(index_name):
                for sym in stock.get("symbols", []):
                    yahoo = sym.get("yahoo")
                    if yahoo:
                        tickers.append(yahoo)
                        break  # one yahoo symbol per stock
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", index_name, e)
        result[slug] = tickers
        logger.info("%s: %d constituents", index_name, len(tickers))

    return result


def get_eurostoxx50_tickers() -> list[str]:
    """Get EURO STOXX 50 constituents from Wikipedia."""
    import pandas as pd
    import requests

    url = "https://en.wikipedia.org/wiki/EURO_STOXX_50"
    resp = requests.get(url, headers={"User-Agent": "stock-db-builder/1.0"})
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    for t in tables:
        if "Ticker" in t.columns:
            tickers = t["Ticker"].dropna().str.strip().tolist()
            logger.info("EURO STOXX 50: %d constituents", len(tickers))
            return tickers
    logger.warning("EURO STOXX 50: no Ticker column found")
    return []


def get_russell2000_tickers() -> list[str]:
    """Get Russell 2000 constituents via iShares IWM ETF holdings."""
    import csv
    import requests

    url = ("https://www.ishares.com/us/products/239710/"
           "ishares-russell-2000-etf/1467271812596.ajax"
           "?fileType=csv&fileName=IWM_holdings&dataType=fund")
    resp = requests.get(url, headers={"User-Agent": "stock-db-builder/1.0"})
    resp.raise_for_status()
    lines = resp.text.strip().split("\n")

    # Find header row
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("Ticker,") or line.startswith('"Ticker"'):
            header_idx = i
            break
    if header_idx is None:
        logger.warning("Russell 2000: could not find header in IWM CSV")
        return []

    reader = csv.DictReader(lines[header_idx:])
    tickers = []
    for row in reader:
        t = row.get("Ticker", "").strip()
        if t and t != "-" and not t.startswith("$"):
            tickers.append(t)
    logger.info("Russell 2000 (IWM): %d constituents", len(tickers))
    return tickers


def enrich_ticker(ticker: str, name_hint: str = "") -> dict | None:
    """Fetch sector/industry/marketCap from yfinance."""
    try:
        info = yf.Ticker(ticker).info
        if not info or info.get("regularMarketPrice") is None:
            return None
        return {
            "ticker": ticker,
            "name": info.get("shortName") or info.get("longName") or name_hint or ticker,
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "market_cap": info.get("marketCap"),
            "region": detect_region(ticker),
            "indices": [],
        }
    except Exception as e:
        logger.debug("SKIP %s: %s", ticker, e)
        return None


def build():
    logger.info("=== Building Stock Database ===")

    # Load name hints from tickers.json
    ticker_hints = load_tickers_json()
    logger.info("Loaded %d name hints from tickers.json", len(ticker_hints))

    # Collect all tickers with their index memberships
    ticker_indices: dict[str, set] = {}

    def add_tickers(tickers, index_slug):
        for t in tickers:
            if t not in ticker_indices:
                ticker_indices[t] = set()
            ticker_indices[t].add(index_slug)

    # S&P 500
    sp500 = get_sp500_tickers()
    add_tickers(sp500, "sp500")
    logger.info("S&P 500: %d tickers", len(sp500))

    # NASDAQ-100
    add_tickers(NASDAQ_100, "nasdaq100")
    logger.info("NASDAQ-100: %d tickers", len(NASDAQ_100))

    # Dow 30
    add_tickers(DOW_30, "dow30")
    logger.info("Dow 30: %d tickers", len(DOW_30))

    # S&P MidCap 400
    logger.info("Fetching S&P 400 constituents from Wikipedia...")
    try:
        sp400 = get_sp400_tickers()
        add_tickers(sp400, "sp400")
    except Exception as e:
        logger.warning("Failed to fetch S&P 400: %s", e)

    # S&P SmallCap 600
    logger.info("Fetching S&P 600 constituents from Wikipedia...")
    try:
        sp600 = get_sp600_tickers()
        add_tickers(sp600, "sp600")
    except Exception as e:
        logger.warning("Failed to fetch S&P 600: %s", e)

    # EU indices (pytickersymbols: FTSE 100, DAX)
    logger.info("Fetching EU index constituents...")
    eu_indices = get_eu_index_tickers()
    for slug, tickers in eu_indices.items():
        add_tickers(tickers, slug)

    # EURO STOXX 50 (Wikipedia)
    logger.info("Fetching EURO STOXX 50 constituents from Wikipedia...")
    try:
        eurostoxx50 = get_eurostoxx50_tickers()
        add_tickers(eurostoxx50, "eurostoxx50")
    except Exception as e:
        logger.warning("Failed to fetch EURO STOXX 50: %s", e)

    # Russell 2000 (iShares IWM holdings)
    logger.info("Fetching Russell 2000 constituents from iShares IWM...")
    try:
        russell2000 = get_russell2000_tickers()
        add_tickers(russell2000, "russell2000")
    except Exception as e:
        logger.warning("Failed to fetch Russell 2000: %s", e)

    all_tickers = list(ticker_indices.keys())
    logger.info("Total unique tickers to enrich: %d", len(all_tickers))

    # Enrich via yfinance in parallel batches
    stocks = {}
    batch_size = 20
    workers = 10
    failed = 0
    total = len(all_tickers)

    for batch_start in range(0, total, batch_size):
        batch = all_tickers[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        logger.info("Batch %d/%d (%d-%d/%d)", batch_num, total_batches, batch_start + 1, min(batch_start + batch_size, total), total)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for t in batch:
                hint = ticker_hints.get(t, {}).get("n", "")
                futures[pool.submit(enrich_ticker, t, hint)] = t

            for future in as_completed(futures):
                ticker = futures[future]
                result = future.result()
                if result:
                    result["indices"] = sorted(ticker_indices[ticker])
                    stocks[ticker] = result
                    logger.debug("OK  %s: %s / %s", ticker, result['sector'], result['industry'])
                else:
                    failed += 1
                    logger.warning("FAIL %s", ticker)

        # Rate limit between batches
        if batch_start + batch_size < total:
            time.sleep(1)

    logger.info("=== Results ===")
    logger.info("Enriched: %d / %d (%d failed)", len(stocks), total, failed)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(stocks, f, indent=2, sort_keys=True)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    logger.info("Written to %s (%.0f KB)", OUTPUT_PATH, size_kb)

    # Summary by region
    us_count = sum(1 for s in stocks.values() if s["region"] == "US")
    eu_count = sum(1 for s in stocks.values() if s["region"] == "Europe")
    logger.info("US: %d, Europe: %d", us_count, eu_count)

    # Summary by index
    index_counts = {}
    for s in stocks.values():
        for idx in s["indices"]:
            index_counts[idx] = index_counts.get(idx, 0) + 1
    for idx, count in sorted(index_counts.items()):
        logger.info("  %s: %d", idx, count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build data/stocks.json")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)
    build()
