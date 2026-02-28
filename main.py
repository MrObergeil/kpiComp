"""
Stock Rater - FastAPI Application

Provides both:
  - A web interface (single page) for interactive use
  - A REST API endpoint for programmatic access
"""

import asyncio
import json
import time
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, field_validator

from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

from data import analyze_stock, clear_cache
from train import router as train_router
import stock_db
import peer_groups

app = FastAPI(
    title="Stock Rater",
    description="Rate stocks on a 1-10 value scale based on financial KPIs, with sector comparison.",
    version="2.0.0",
)
app.include_router(train_router)

# --- Ticker autocomplete data (loaded once at startup) ---
_tickers_path = Path(__file__).parent / "data" / "tickers.json"
_tickers_data: list = []
if _tickers_path.exists():
    with open(_tickers_path) as f:
        _tickers_data = json.load(f)
    logger.info(f"Loaded {len(_tickers_data)} tickers for autocomplete")


# --- Middleware ---

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code}",
        extra={"duration_ms": duration_ms, "status_code": response.status_code},
    )
    return response


# --- REST API ---

@app.get("/api/analyze/{ticker}", response_class=JSONResponse)
async def api_analyze(
    ticker: str,
    peers: Optional[str] = Query(None, description="Comma-separated peer tickers"),
    region: Optional[str] = Query(None, description="Region filter: us, europe"),
):
    """
    REST API endpoint: Analyze a stock ticker.

    Query params:
      - peers: Comma-separated list of peer tickers (e.g. ?peers=MSFT,GOOG)
      - region: Filter peers by region (us, europe)
    """
    try:
        peer_list = None
        if peers:
            peer_list = [p.strip().upper() for p in peers.split(",") if p.strip()]

        rgn = None
        if region and region.lower().strip() in ("us", "europe"):
            rgn = region.lower().strip()

        result = await asyncio.to_thread(analyze_stock, ticker, peers=peer_list, region=rgn)
        return JSONResponse(content=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing '{ticker}': {str(e)}")


@app.post("/api/clear-cache")
async def api_clear_cache():
    """Clear the sector data cache."""
    clear_cache()
    return {"status": "ok", "message": "Cache cleared."}


@app.get("/api/tickers")
async def api_tickers():
    """Return full ticker list for client-side autocomplete."""
    return JSONResponse(
        content=_tickers_data,
        headers={"Cache-Control": "public, max-age=86400"},
    )


# --- Peer CRUD ---

class PeerSetRequest(BaseModel):
    peers: list[str]

    @field_validator("peers")
    @classmethod
    def validate_peers(cls, v):
        if len(v) < 2:
            raise ValueError("Need at least 2 peers")
        if len(v) > 50:
            raise ValueError("Maximum 50 peers allowed")
        return [p.upper().strip() for p in v]


@app.get("/api/peers/{ticker}")
async def api_get_peers(ticker: str):
    """Get auto-detected and custom peers for a ticker."""
    from peers import resolve_peers

    clean = ticker.upper().strip()
    stock = stock_db.get_stock(clean)
    custom = peer_groups.get_custom_peers(clean)

    auto_result = None
    if stock:
        auto_result = resolve_peers(
            ticker=clean,
            sector=stock.get("sector", ""),
            industry=stock.get("industry"),
        )

    return {
        "ticker": clean,
        "custom_peers": custom,
        "auto_peers": {
            "tickers": auto_result.tickers if auto_result else [],
            "level": auto_result.level if auto_result else None,
            "message": auto_result.message if auto_result else "Stock not in database",
        } if True else None,
        "in_database": stock is not None,
    }


@app.put("/api/peers/{ticker}")
async def api_set_peers(ticker: str, req: PeerSetRequest):
    """Save custom peer set for a ticker."""
    clean = ticker.upper().strip()
    peer_groups.set_custom_peers(clean, req.peers)
    return {"status": "ok", "ticker": clean, "peers": req.peers}


@app.delete("/api/peers/{ticker}")
async def api_delete_peers(ticker: str):
    """Remove custom peer override for a ticker."""
    clean = ticker.upper().strip()
    existed = peer_groups.delete_custom_peers(clean)
    return {"status": "ok", "ticker": clean, "deleted": existed}


# --- Taxonomy / Stock DB ---

@app.get("/api/taxonomy/sectors")
async def api_sectors():
    """List sectors with stock counts from the database."""
    return stock_db.get_sectors()


@app.get("/api/taxonomy/industries")
async def api_industries(sector: str = Query(..., description="Sector name")):
    """List industries within a sector."""
    return stock_db.get_industries(sector)


@app.get("/api/stocks")
async def api_stocks(
    sector: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    index: Optional[str] = Query(None),
):
    """Query the stock database with optional filters."""
    results = stock_db.query_stocks(
        sector=sector, industry=industry, region=region, index=index,
    )
    return results


# --- Frontend Log Endpoint ---

class FrontendLog(BaseModel):
    level: str
    message: str
    context: dict = {}
    url: Optional[str] = None
    userAgent: Optional[str] = None
    ts: Optional[str] = None

frontend_logger = logging.getLogger("frontend")

@app.post("/api/log")
async def receive_frontend_log(log: FrontendLog):
    _VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
    level_name = log.level.upper()
    log_level = getattr(logging, level_name) if level_name in _VALID_LEVELS else logging.INFO
    extra = {"source": "frontend"}
    extra.update(log.context)
    frontend_logger.log(log_level, log.message, extra=extra)
    return {"status": "ok"}


# --- Web Interface ---

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the single-page web interface."""
    index_path = Path(__file__).parent / "index.html"
    with open(index_path, "r") as f:
        return HTMLResponse(content=f.read())
