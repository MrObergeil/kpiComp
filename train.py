"""
Sentiment training endpoints. Separate router for easy removal.
See TRAINING_FEATURE.md for usage and removal instructions.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sentiment import fetch_articles, _BULLISH, _BEARISH, _TRAIN_DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter()

_KEYWORDS_FILE = _TRAIN_DATA_DIR / "news_keywords.json"
_FEEDBACK_FILE = _TRAIN_DATA_DIR / "feedback.json"

_EMPTY_OVERRIDES = {"bullish_add": [], "bullish_remove": [], "bearish_add": [], "bearish_remove": []}


def _ensure_train_dir():
    _TRAIN_DATA_DIR.mkdir(exist_ok=True)


def _read_overrides(indicator: str) -> dict:
    path = _TRAIN_DATA_DIR / f"{indicator}_keywords.json"
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_EMPTY_OVERRIDES)


def _write_overrides(indicator: str, overrides: dict):
    _ensure_train_dir()
    path = _TRAIN_DATA_DIR / f"{indicator}_keywords.json"
    path.write_text(json.dumps(overrides, indent=2))


def _read_feedback() -> list:
    try:
        return json.loads(_FEEDBACK_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _append_feedback(entry: dict):
    _ensure_train_dir()
    entries = _read_feedback()
    entries.append(entry)
    _FEEDBACK_FILE.write_text(json.dumps(entries, indent=2))


# --- Serve UI ---

@router.get("/train", response_class=HTMLResponse)
async def train_page():
    path = Path(__file__).parent / "train.html"
    with open(path, "r") as f:
        return HTMLResponse(content=f.read())


# --- Articles ---

@router.get("/train/api/articles/{ticker}")
async def get_articles(ticker: str):
    import asyncio
    articles = await asyncio.to_thread(fetch_articles, ticker)
    if articles is None:
        raise HTTPException(status_code=404, detail=f"Could not fetch articles for '{ticker}'")
    return {"ticker": ticker.upper().strip(), "articles": articles}


# --- Keywords ---

_BASE_KEYWORDS = {
    "news": {"bullish": sorted(_BULLISH), "bearish": sorted(_BEARISH)},
}


@router.get("/train/api/keywords/{indicator}")
async def get_keywords(indicator: str):
    if indicator not in _BASE_KEYWORDS:
        raise HTTPException(status_code=404, detail=f"Unknown indicator '{indicator}'")
    base = _BASE_KEYWORDS[indicator]
    overrides = _read_overrides(indicator)

    effective_bullish = set(base["bullish"]) | set(overrides.get("bullish_add", [])) - set(overrides.get("bullish_remove", []))
    effective_bearish = set(base["bearish"]) | set(overrides.get("bearish_add", [])) - set(overrides.get("bearish_remove", []))

    return {
        "indicator": indicator,
        "base_bullish": base["bullish"],
        "base_bearish": base["bearish"],
        "overrides": overrides,
        "effective_bullish": sorted(effective_bullish),
        "effective_bearish": sorted(effective_bearish),
    }


class KeywordOverrides(BaseModel):
    bullish_add: list[str] = []
    bullish_remove: list[str] = []
    bearish_add: list[str] = []
    bearish_remove: list[str] = []


@router.post("/train/api/keywords/{indicator}")
async def save_keywords(indicator: str, overrides: KeywordOverrides):
    if indicator not in _BASE_KEYWORDS:
        raise HTTPException(status_code=404, detail=f"Unknown indicator '{indicator}'")
    data = {
        "bullish_add": sorted(set(w.lower().strip() for w in overrides.bullish_add if w.strip())),
        "bullish_remove": sorted(set(w.lower().strip() for w in overrides.bullish_remove if w.strip())),
        "bearish_add": sorted(set(w.lower().strip() for w in overrides.bearish_add if w.strip())),
        "bearish_remove": sorted(set(w.lower().strip() for w in overrides.bearish_remove if w.strip())),
    }
    _write_overrides(indicator, data)
    return {"status": "ok", "overrides": data}


# --- Feedback ---

class FeedbackEntry(BaseModel):
    indicator: str = "news"
    ticker: str
    headline: str
    summary: str = ""
    computed_score: float
    correct_score: float
    matched_keywords: dict = {}
    source: str = ""


@router.post("/train/api/feedback")
async def submit_feedback(entry: FeedbackEntry):
    record = entry.model_dump()
    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    _append_feedback(record)
    return {"status": "ok"}


@router.get("/train/api/feedback")
async def get_feedback():
    return {"feedback": _read_feedback()}
