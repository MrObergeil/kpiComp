"""
Stock Rater - FastAPI Application

Provides both:
  - A web interface (single page) for interactive use
  - A REST API endpoint for programmatic access
"""

import asyncio
import time
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

from data import analyze_stock, clear_cache
from train import router as train_router

app = FastAPI(
    title="Stock Rater",
    description="Rate stocks on a 1-10 value scale based on financial KPIs, with sector comparison.",
    version="1.0.0",
)
app.include_router(train_router)


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
async def api_analyze(ticker: str):
    """
    REST API endpoint: Analyze a stock ticker.

    Returns JSON with:
      - ticker, company_name, sector, industry
      - stock KPIs, sector averages, differences
      - overall rating (1-10) with breakdown
    """
    try:
        result = await asyncio.to_thread(analyze_stock, ticker)
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
