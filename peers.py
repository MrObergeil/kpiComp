"""
Peer selection logic with cascading fallback.

Resolves the best peer set for a given stock based on:
1. Custom peers (if provided) - use directly
2. Industry peers in region (if >= min_peers)
3. Industry peers global (if >= min_peers)
4. Sector peers with market cap band in region (if >= min_peers)
5. Sector peers in region (if >= min_peers)
6. Full sector global (last resort)
"""

import logging
from dataclasses import dataclass

import stock_db

logger = logging.getLogger(__name__)


@dataclass
class PeerResult:
    tickers: list[str]
    level: str  # custom, industry, sector_cap_band, sector
    region: str | None  # us, europe, None (global)
    total_available: int
    message: str


def resolve_peers(
    ticker: str,
    sector: str,
    industry: str | None = None,
    region: str | None = None,
    custom_peers: list[str] | None = None,
    min_peers: int = 5,
) -> PeerResult:
    """
    Resolve peer set with cascading fallback.

    Args:
        ticker: The stock being analyzed (excluded from peers).
        sector: Stock's sector.
        industry: Stock's industry (optional).
        region: Filter to 'us' or 'europe' (None = global).
        custom_peers: User-specified peer list (bypasses cascade).
        min_peers: Minimum peers before falling to next level.
    """
    ticker_upper = ticker.upper().strip()

    # 1. Custom peers
    if custom_peers is not None:
        peers = [p for p in custom_peers if p.upper().strip() != ticker_upper]
        logger.info(f"{ticker_upper}: custom peers, count={len(peers)}")
        return PeerResult(
            tickers=peers,
            level="custom",
            region=region,
            total_available=len(peers),
            message=f"{len(peers)} custom peers",
        )

    def _filter(stocks: list[dict], exclude: str = ticker_upper) -> list[str]:
        return [s["ticker"] for s in stocks if s["ticker"].upper() != exclude]

    def _region_filter(stocks: list[dict], rgn: str | None) -> list[dict]:
        if not rgn:
            return stocks
        rl = rgn.lower().strip()
        return [s for s in stocks if (s.get("region") or "").lower().strip() == rl]

    # 2. Industry peers in region
    if industry:
        industry_stocks = stock_db.get_stocks_by_industry(sector, industry)
        if region:
            regional = _region_filter(industry_stocks, region)
            peers = _filter(regional)
            if len(peers) >= min_peers:
                logger.info(f"{ticker_upper}: level=industry region={region} count={len(peers)}")
                return PeerResult(
                    tickers=peers,
                    level="industry",
                    region=region,
                    total_available=len(_filter(industry_stocks)),
                    message=f"{len(peers)} industry peers ({region})",
                )
            logger.debug(f"{ticker_upper}: industry+{region} has {len(peers)} peers (need {min_peers}), falling back")

        # 3. Industry peers global
        peers = _filter(industry_stocks)
        if len(peers) >= min_peers:
            logger.info(f"{ticker_upper}: level=industry region=global count={len(peers)}")
            return PeerResult(
                tickers=peers,
                level="industry",
                region=None,
                total_available=len(peers),
                message=f"{len(peers)} industry peers (global)",
            )
        logger.debug(f"{ticker_upper}: industry global has {len(peers)} peers (need {min_peers}), falling back")

    # 4. Sector peers with market cap band in region
    cap_band = stock_db.get_market_cap_band(ticker_upper)
    if cap_band:
        min_cap, max_cap = cap_band
        sector_cap_stocks = stock_db.query_stocks(
            sector=sector, min_cap=min_cap, max_cap=max_cap, region=region
        )
        peers = _filter(sector_cap_stocks)
        if len(peers) >= min_peers:
            logger.info(f"{ticker_upper}: level=sector_cap_band region={region} count={len(peers)}")
            return PeerResult(
                tickers=peers,
                level="sector_cap_band",
                region=region,
                total_available=len(peers),
                message=f"{len(peers)} sector peers (similar market cap{', ' + region if region else ''})",
            )
        logger.debug(f"{ticker_upper}: sector_cap_band has {len(peers)} peers (need {min_peers}), falling back")

    # 5. Sector peers in region
    if region:
        sector_regional = stock_db.query_stocks(sector=sector, region=region)
        peers = _filter(sector_regional)
        if len(peers) >= min_peers:
            logger.info(f"{ticker_upper}: level=sector region={region} count={len(peers)}")
            return PeerResult(
                tickers=peers,
                level="sector",
                region=region,
                total_available=len(peers),
                message=f"{len(peers)} sector peers ({region})",
            )
        logger.debug(f"{ticker_upper}: sector+{region} has {len(peers)} peers (need {min_peers}), falling back to global")

    # 6. Full sector global (last resort)
    all_sector = stock_db.get_stocks_by_sector(sector)
    peers = _filter(all_sector)
    logger.info(f"{ticker_upper}: level=sector region=global count={len(peers)} (last resort)")
    return PeerResult(
        tickers=peers,
        level="sector",
        region=None,
        total_available=len(peers),
        message=f"{len(peers)} sector peers (global)",
    )
