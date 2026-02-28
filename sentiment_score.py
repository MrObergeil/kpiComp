"""Composite sentiment score from directional indicators.

Registry-based: add/remove indicators by editing the INDICATORS list.
Each indicator normalizes to 0.0-1.0 (0.5 = neutral, >0.5 = bullish).
Missing indicators redistribute weight proportionally.
"""

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class SentimentIndicator:
    key: str                              # API response key
    name: str                             # display name
    weight: float                         # default weight (sum should be 1.0)
    extract: Callable[[dict], Optional[float]]  # returns 0.0-1.0 or None


def _extract_analyst(data: dict) -> Optional[float]:
    if not data or not data.get("available"):
        return None
    score = data.get("consensus_score")
    if score is None:
        return None
    # -2.0 to +2.0 → 0.0 to 1.0
    return max(0.0, min(1.0, (score + 2.0) / 4.0))


def _extract_options(data: dict) -> Optional[float]:
    if not data or not data.get("available"):
        return None
    pc = data.get("pc_ratio")
    if pc is None:
        return None
    # Lower pc_ratio = more bullish. Clamp to 0-2 range, invert.
    return max(0.0, min(1.0, 1.0 - min(pc, 2.0) / 2.0))


def _extract_news(data: dict) -> Optional[float]:
    if not data or not data.get("available"):
        return None
    if not data.get("sufficient_data", True):
        return None
    ratio = data.get("bull_bear_ratio")
    if ratio is None:
        return None
    return max(0.0, min(1.0, ratio))


def _extract_insider(data: dict) -> Optional[float]:
    if not data or not data.get("available"):
        return None
    buys = data.get("buy_count", 0)
    sells = data.get("sell_count", 0)
    total = buys + sells
    if total == 0:
        return None  # no transactions = no signal
    score = buys / total
    if data.get("cluster_buy"):
        score = min(1.0, score + 0.05)
    return score


# --- Registry ---
# Add/remove indicators here. Weights should sum to 1.0.
INDICATORS: list[SentimentIndicator] = [
    SentimentIndicator("analyst_ratings", "Analyst Consensus", 0.35, _extract_analyst),
    SentimentIndicator("options_sentiment", "Options Flow", 0.30, _extract_options),
    SentimentIndicator("sentiment", "News Sentiment", 0.20, _extract_news),
    SentimentIndicator("insider_trading", "Insider Trading", 0.15, _extract_insider),
]


def _label_from_score(score: float) -> str:
    if score >= 0.3:
        return "Bullish"
    if score >= 0.1:
        return "Slightly Bullish"
    if score > -0.1:
        return "Neutral"
    if score > -0.3:
        return "Slightly Bearish"
    return "Bearish"


def compute_composite_sentiment(analysis_data: dict) -> Optional[dict]:
    """Compute weighted composite from available directional indicators.

    Args:
        analysis_data: dict with keys matching indicator registry keys.

    Returns:
        Composite result dict or None if fewer than 2 indicators available.
    """
    breakdown = []
    available_weight = 0.0

    for ind in INDICATORS:
        raw = ind.extract(analysis_data.get(ind.key) or {})
        breakdown.append({
            "name": ind.name,
            "key": ind.key,
            "raw_score": raw,
            "weight": ind.weight,
            "available": raw is not None,
        })
        if raw is not None:
            available_weight += ind.weight

    available_count = sum(1 for b in breakdown if b["available"])
    if available_count < 2:
        return None

    # Redistribute weights and compute weighted average
    weighted_sum = 0.0
    for b in breakdown:
        if b["available"]:
            effective_weight = b["weight"] / available_weight
            b["effective_weight"] = effective_weight
            mapped = (b["raw_score"] - 0.5) * 2.0  # 0-1 → -1 to +1
            b["mapped_score"] = round(mapped, 3)
            weighted_sum += b["raw_score"] * effective_weight
        else:
            b["effective_weight"] = 0.0
            b["mapped_score"] = None

    # Convert 0-1 internal to -1 to +1 display
    composite = round((weighted_sum - 0.5) * 2.0, 3)

    confidence = "high" if available_count >= 4 else "medium" if available_count >= 3 else "low"

    return {
        "score": composite,
        "label": _label_from_score(composite),
        "confidence": confidence,
        "indicators_used": available_count,
        "indicators_total": len(INDICATORS),
        "breakdown": breakdown,
    }
