"""
Sector Scan — scan an entire sector/industry, rank stocks by value score.
Uses SSE to stream per-stock progress to the frontend.
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse

from data import fetch_ticker_kpis, _sanitize_for_json
from rating import (
    KPI_CONFIGS,
    compute_sector_averages,
    compute_sector_thresholds,
    calculate_rating,
)
import stock_db

logger = logging.getLogger(__name__)

router = APIRouter()

_SCAN_WORKERS = 10


@router.get("/sector-scan", response_class=HTMLResponse)
async def sector_scan_page():
    html_path = Path(__file__).parent / "sector_scan.html"
    return HTMLResponse(content=html_path.read_text())


@router.get("/sector-scan/api/stream")
async def sector_scan_stream(
    sectors: list[str] = Query(..., description="Sector names (repeated param)"),
    industries: list[str] = Query(None, description="Industry names (repeated param, optional)"),
    region: str = Query(None, description="Region filter: us, europe"),
):
    sector_list = [s.strip() for s in sectors if s.strip()]
    industry_set = None
    if industries:
        industry_set = {i.strip().lower() for i in industries if i.strip()}

    logger.info(
        "Sector scan: sectors=%s, industries=%s, region=%s",
        sector_list, list(industry_set) if industry_set else None, region,
    )

    # Union stocks across all selected sectors, dedup by ticker
    seen = {}
    for sec in sector_list:
        for s in stock_db.query_stocks(sector=sec, region=region):
            t = s.get("ticker")
            if not t or t in seen:
                continue
            if industry_set and (s.get("industry") or "").lower().strip() not in industry_set:
                continue
            seen[t] = s

    stocks = list(seen.values())
    tickers = [s["ticker"] for s in stocks]
    logger.info("Sector scan: %d stocks matched across %d sectors", len(tickers), len(sector_list))

    async def generate():
        total = len(tickers)
        yield {"event": "start", "data": json.dumps({"total": total})}

        if total == 0:
            yield {"event": "done", "data": json.dumps({"message": "No stocks found"})}
            return

        loop = asyncio.get_running_loop()
        all_kpis = []
        ticker_meta = {}  # ticker -> {name, industry, market_cap}
        failed = []
        completed = 0
        t0 = time.monotonic()

        # Map ticker to stock_db metadata for name/industry/cap
        for s in stocks:
            t = s.get("ticker")
            if t:
                ticker_meta[t] = {
                    "name": s.get("name", t),
                    "industry": s.get("industry", ""),
                    "market_cap": s.get("market_cap"),
                }

        async def fetch_one(pool, ticker):
            result = await loop.run_in_executor(pool, fetch_ticker_kpis, ticker)
            return ticker, result

        with ThreadPoolExecutor(max_workers=_SCAN_WORKERS) as pool:
            tasks = [fetch_one(pool, t) for t in tickers]
            for coro in asyncio.as_completed(tasks):
                try:
                    ticker, result = await coro
                except Exception as e:
                    logger.warning(f"Scan fetch failed: {e}")
                    completed += 1
                    continue

                completed += 1
                if result is not None:
                    all_kpis.append(result)
                    status = "ok"
                else:
                    failed.append(ticker)
                    status = "failed"

                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "completed": completed,
                        "total": total,
                        "ticker": ticker,
                        "status": status,
                    }),
                }

        elapsed = round(time.monotonic() - t0, 1)

        if not all_kpis:
            logger.warning("Sector scan: all %d stocks failed to fetch in %.1fs", total, elapsed)
            yield {"event": "done", "data": json.dumps({
                "message": "All stocks failed to fetch",
                "elapsed": elapsed,
            })}
            return

        # Score all stocks against the scanned peer set
        sector_avgs = compute_sector_averages(all_kpis)
        sector_thresh = compute_sector_thresholds(all_kpis)

        scored = []
        for kpis in all_kpis:
            ticker = kpis.get("_ticker", "?")
            rating_result = calculate_rating(
                stock_kpis=kpis,
                sector_averages=sector_avgs,
                sector_thresholds=sector_thresh,
            )
            meta = ticker_meta.get(ticker, {})
            row = {
                "ticker": ticker,
                "name": kpis.get("_name") or meta.get("name", ticker),
                "industry": kpis.get("_industry") or meta.get("industry", ""),
                "market_cap": kpis.get("_market_cap") or meta.get("market_cap"),
                "score": rating_result["overall_rating"],
                "absolute_score": rating_result["absolute_score"],
                "relative_score": rating_result["relative_score"],
            }
            # Add raw KPI values for table display
            for cfg in KPI_CONFIGS:
                row[cfg.key] = kpis.get(cfg.key)
            scored.append(row)

        scored.sort(key=lambda r: r["score"], reverse=True)

        logger.info(
            "Sector scan complete: %d scored, %d failed in %.1fs",
            len(scored), len(failed), elapsed,
        )

        yield {
            "event": "result",
            "data": json.dumps(_sanitize_for_json({
                "stocks": scored,
                "stats": {
                    "scored": len(scored),
                    "failed": len(failed),
                    "failed_tickers": failed,
                    "elapsed": elapsed,
                },
                "sector_averages": sector_avgs,
            })),
        }

        yield {"event": "done", "data": json.dumps({"message": "ok"})}

    return EventSourceResponse(generate())
