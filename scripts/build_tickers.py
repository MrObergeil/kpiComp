#!/usr/bin/env python3
"""
Build data/tickers.json from SEC EDGAR (US) + pytickersymbols (Europe) + financedatabase (Asia).

Usage: python scripts/build_tickers.py
Output: data/tickers.json

Dependencies (build-time only): pytickersymbols, financedatabase, requests
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logging_config import setup_logging

import requests

logger = logging.getLogger(__name__)

EDGAR_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
EDGAR_HEADERS = {"User-Agent": "StockRater/1.0 admin@example.com"}
US_EXCHANGES = {"NYSE", "Nasdaq", "AMEX", "BATS"}

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "tickers.json"


def fetch_us_tickers() -> dict[str, dict]:
    """Fetch US tickers from SEC EDGAR. Returns {ticker: {t, n, e}}."""
    logger.info("Fetching US tickers from SEC EDGAR...")
    resp = requests.get(EDGAR_URL, headers=EDGAR_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    fields = data["fields"]  # [cik, name, ticker, exchange]
    ti = fields.index("ticker")
    ni = fields.index("name")
    ei = fields.index("exchange")

    tickers = {}
    for row in data["data"]:
        ticker = row[ti]
        exchange = row[ei]
        name = row[ni]
        if not ticker or not exchange or exchange not in US_EXCHANGES:
            continue
        # Skip tickers with weird characters (warrants, units, etc.)
        if any(c in ticker for c in " ^/"):
            continue
        tickers[ticker] = {"t": ticker, "n": _title_case(name), "e": exchange}

    logger.info("-> %d US tickers", len(tickers))
    return tickers


def fetch_eu_tickers() -> dict[str, dict]:
    """Fetch European tickers via pytickersymbols. Returns {ticker: {t, n, e}}."""
    try:
        from pytickersymbols import PyTickerSymbols
    except ImportError:
        logger.warning("pytickersymbols not installed, skipping EU tickers (pip install pytickersymbols)")
        return {}

    logger.info("Fetching European tickers via pytickersymbols...")
    pts = PyTickerSymbols()

    indices = pts.get_all_indices()
    tickers = {}

    for index in indices:
        for stock in pts.get_stocks_by_index(index):
            name = stock.get("name", "")
            for sym_info in stock.get("symbols", []):
                yahoo = sym_info.get("yahoo")
                if not yahoo:
                    continue
                # Determine exchange from suffix
                if "." in yahoo:
                    suffix = yahoo[yahoo.rindex("."):]
                    exchange = _suffix_to_exchange(suffix)
                else:
                    exchange = index
                if yahoo not in tickers:
                    tickers[yahoo] = {"t": yahoo, "n": name, "e": exchange}

    logger.info("-> %d EU tickers", len(tickers))
    return tickers


def fetch_asian_tickers() -> dict[str, dict]:
    """Fetch Korean + Chinese tickers via financedatabase. Returns {ticker: {t, n, e}}."""
    try:
        import financedatabase as fd
    except ImportError:
        logger.warning("financedatabase not installed, skipping Asian tickers (pip install financedatabase)")
        return {}

    logger.info("Fetching Asian tickers via financedatabase...")
    equities = fd.Equities()

    exchange_labels = {
        "KSC": "KOSPI", "KOE": "KOSDAQ",
        "SHH": "Shanghai", "SHZ": "Shenzhen",
    }

    # Only include tickers actually listed on the local exchanges
    country_exchanges = {
        "South Korea": {"KSC", "KOE"},
        "China": {"SHH", "SHZ"},
    }

    tickers = {}
    for country in ["South Korea", "China"]:
        df = equities.select(country=country)
        allowed = country_exchanges[country]
        for yahoo_ticker, row in df.iterrows():
            name = row.get("name")
            raw_exchange = row.get("exchange", "")
            if not isinstance(raw_exchange, str) or raw_exchange not in allowed:
                continue
            if not yahoo_ticker or not isinstance(name, str) or not name:
                continue
            exchange = exchange_labels.get(raw_exchange, raw_exchange)
            tickers[yahoo_ticker] = {"t": yahoo_ticker, "n": name, "e": exchange}

    logger.info("-> %d Asian tickers", len(tickers))
    return tickers


def _suffix_to_exchange(suffix: str) -> str:
    mapping = {
        ".L": "LSE", ".IL": "LSE",
        ".DE": "XETRA", ".F": "Frankfurt",
        ".PA": "Euronext Paris",
        ".AS": "Euronext Amsterdam",
        ".BR": "Euronext Brussels",
        ".LS": "Euronext Lisbon",
        ".MC": "BME Madrid",
        ".MI": "Borsa Italiana",
        ".ST": "Nasdaq Stockholm",
        ".CO": "Nasdaq Copenhagen",
        ".HE": "Nasdaq Helsinki",
        ".OL": "Oslo Bors",
        ".VI": "Vienna",
        ".SW": "SIX Swiss",
        ".IR": "Euronext Dublin",
        ".WA": "WSE Warsaw",
        ".PR": "Prague",
    }
    return mapping.get(suffix, suffix)


def _title_case(name: str) -> str:
    """Title-case company name, but keep short words lowercase."""
    if not name:
        return name
    # If already mixed case, leave it alone
    if name != name.upper() and name != name.lower():
        return name
    return name.title()


def main():
    us = fetch_us_tickers()
    eu = fetch_eu_tickers()
    asia = fetch_asian_tickers()

    # Merge: US takes priority on duplicates
    merged = {**asia, **eu, **us}

    result = sorted(merged.values(), key=lambda x: x["t"])
    logger.info("Total: %d tickers", len(result))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, separators=(",", ":"))

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    logger.info("Written to %s (%.0f KB)", OUTPUT_PATH, size_kb)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build data/tickers.json")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()
    setup_logging(level=logging.DEBUG if args.verbose else logging.INFO)
    main()
