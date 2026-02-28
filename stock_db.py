"""
Stock database query module.

Lazy-loads data/stocks.json (index constituents with sector/industry/marketCap).
Provides O(1) lookups and filtered queries for peer comparison.
"""

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent / "data" / "stocks.json"
_db: dict[str, dict] | None = None
_db_lock = threading.Lock()


def _load_db() -> dict[str, dict]:
    global _db
    if _db is not None:
        return _db
    with _db_lock:
        if _db is not None:
            return _db
        if not _DB_PATH.exists():
            _db = {}
            logger.info("Stock DB not found at %s", _DB_PATH)
            return _db
        with open(_DB_PATH) as f:
            _db = json.load(f)
        logger.info("Stock DB loaded: %d stocks from %s", len(_db), _DB_PATH)
        return _db


def get_stock(ticker: str) -> dict | None:
    """Get a single stock entry by ticker. Returns None if not in DB."""
    return _load_db().get(ticker.upper().strip())


def get_stocks_by_sector(sector: str) -> list[dict]:
    """Get all stocks in a given sector."""
    db = _load_db()
    sector_lower = sector.lower().strip()
    return [s for s in db.values() if (s.get("sector") or "").lower().strip() == sector_lower]


def get_stocks_by_industry(sector: str, industry: str) -> list[dict]:
    """Get all stocks matching sector + industry."""
    db = _load_db()
    sector_lower = sector.lower().strip()
    industry_lower = industry.lower().strip()
    return [
        s for s in db.values()
        if (s.get("sector") or "").lower().strip() == sector_lower
        and (s.get("industry") or "").lower().strip() == industry_lower
    ]


def query_stocks(
    sector: str | None = None,
    industry: str | None = None,
    region: str | None = None,
    index: str | None = None,
    min_cap: float | None = None,
    max_cap: float | None = None,
) -> list[dict]:
    """Query stocks with optional filters. All filters are AND-combined."""
    db = _load_db()
    results = list(db.values())

    if sector:
        sl = sector.lower().strip()
        results = [s for s in results if (s.get("sector") or "").lower().strip() == sl]
    if industry:
        il = industry.lower().strip()
        results = [s for s in results if (s.get("industry") or "").lower().strip() == il]
    if region:
        rl = region.lower().strip()
        results = [s for s in results if (s.get("region") or "").lower().strip() == rl]
    if index:
        results = [s for s in results if index in (s.get("indices") or [])]
    if min_cap is not None:
        results = [s for s in results if (s.get("market_cap") or 0) >= min_cap]
    if max_cap is not None:
        results = [s for s in results if (s.get("market_cap") or 0) <= max_cap]

    return results


def get_sectors() -> list[dict]:
    """Get list of sectors with stock counts."""
    db = _load_db()
    counts: dict[str, int] = {}
    for s in db.values():
        sec = s.get("sector")
        if sec:
            counts[sec] = counts.get(sec, 0) + 1
    return [{"sector": k, "count": v} for k, v in sorted(counts.items())]


def get_industries(sector: str) -> list[dict]:
    """Get industries within a sector, with stock counts."""
    stocks = get_stocks_by_sector(sector)
    counts: dict[str, int] = {}
    for s in stocks:
        ind = s.get("industry")
        if ind:
            counts[ind] = counts.get(ind, 0) + 1
    return [{"industry": k, "count": v} for k, v in sorted(counts.items())]


def get_industries_multi(sectors: list[str]) -> list[dict]:
    """Get union of industries across multiple sectors, with stock counts."""
    sectors_lower = {s.lower().strip() for s in sectors}
    db = _load_db()
    counts: dict[str, int] = {}
    for s in db.values():
        if (s.get("sector") or "").lower().strip() in sectors_lower:
            ind = s.get("industry")
            if ind:
                counts[ind] = counts.get(ind, 0) + 1
    result = [{"industry": k, "count": v} for k, v in sorted(counts.items())]
    logger.debug("get_industries_multi: %d sectors -> %d industries", len(sectors), len(result))
    return result


def get_all_tickers() -> list[str]:
    """Get all tickers in the database."""
    return list(_load_db().keys())


def get_market_cap_band(ticker: str, factor: float = 3.0) -> tuple[float, float] | None:
    """Get market cap band (1/factor to factor) around a stock's market cap."""
    stock = get_stock(ticker)
    if not stock or not stock.get("market_cap"):
        return None
    cap = stock["market_cap"]
    return (cap / factor, cap * factor)
