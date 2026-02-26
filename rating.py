"""
Stock Rating Algorithm v1

Rates a stock on a scale of 1-10 based on financial KPIs.
1 = most expensive / worst value
10 = cheapest / best value

The score combines:
  - Absolute scoring: How does each KPI compare to universal "good/bad" thresholds?
  - Relative scoring: How does each KPI compare to the sector average?

Final score = weighted blend of absolute (40%) and relative (60%) scores.

KPIs used and their interpretation:
  - P/E Ratio (trailingPE): Lower is cheaper. Measures price relative to earnings.
  - Forward P/E (forwardPE): Lower is cheaper. Forward-looking valuation.
  - P/B Ratio (priceToBook): Lower is cheaper. Price relative to book value.
  - EV/EBITDA (enterpriseToEbitda): Lower is cheaper. Enterprise value efficiency.
  - Debt/Equity (debtToEquity): Lower is better. Financial leverage risk.
  - ROE (returnOnEquity): Higher is better. Profitability of equity.
  - Profit Margin (profitMargins): Higher is better. Earnings efficiency.
  - Revenue Growth (revenueGrowth): Higher is better. Top-line momentum.
  - Current Ratio (currentRatio): Higher is better (up to a point). Liquidity.
  - Dividend Yield (dividendYield): Higher is better (for value perspective).
"""

from dataclasses import dataclass
from typing import Optional
import math


# --- KPI Configuration ---

@dataclass
class KPIConfig:
    """Configuration for a single KPI in the rating algorithm."""
    key: str                # Yahoo Finance info dict key
    display_name: str       # Human-readable name
    weight: float           # Weight in the composite score (all weights sum to 1.0)
    lower_is_better: bool   # True for valuation metrics (P/E, P/B, etc.)
    # Absolute scoring thresholds: [best_value, worst_value]
    # For lower_is_better: best = low end, worst = high end
    # For higher_is_better: best = high end, worst = low end
    abs_best: float
    abs_worst: float
    format_as_pct: bool = False  # Display as percentage
    format_decimals: int = 2
    description: str = ""


KPI_CONFIGS = [
    KPIConfig(
        key="trailingPE", display_name="P/E Ratio (TTM)",
        weight=0.15, lower_is_better=True,
        abs_best=5.0, abs_worst=60.0,
        description="Price / trailing 12-month earnings. Lower means you're paying less per dollar of profit.",
    ),
    KPIConfig(
        key="forwardPE", display_name="Forward P/E",
        weight=0.12, lower_is_better=True,
        abs_best=5.0, abs_worst=50.0,
        description="Price / estimated future earnings. Based on analyst forecasts for the next 12 months.",
    ),
    KPIConfig(
        key="priceToBook", display_name="P/B Ratio",
        weight=0.10, lower_is_better=True,
        abs_best=0.5, abs_worst=20.0,
        description="Market price / book value per share. Below 1.0 suggests the stock trades below its net asset value.",
    ),
    KPIConfig(
        key="enterpriseToEbitda", display_name="EV/EBITDA",
        weight=0.12, lower_is_better=True,
        abs_best=3.0, abs_worst=40.0,
        description="Enterprise value / EBITDA. Accounts for debt, useful for comparing companies with different capital structures.",
    ),
    KPIConfig(
        key="debtToEquity", display_name="Debt/Equity",
        weight=0.10, lower_is_better=True,
        abs_best=0.0, abs_worst=300.0,
        description="Total debt / shareholder equity. Higher means more leverage and financial risk.",
    ),
    KPIConfig(
        key="returnOnEquity", display_name="ROE",
        weight=0.12, lower_is_better=False,
        abs_best=0.40, abs_worst=-0.10,
        format_as_pct=True,
        description="Net income / shareholder equity. Measures how efficiently the company turns equity into profit.",
    ),
    KPIConfig(
        key="profitMargins", display_name="Profit Margin",
        weight=0.10, lower_is_better=False,
        abs_best=0.40, abs_worst=-0.10,
        format_as_pct=True,
        description="Net income / revenue. Shows how much of each dollar earned the company keeps as profit.",
    ),
    KPIConfig(
        key="revenueGrowth", display_name="Revenue Growth",
        weight=0.09, lower_is_better=False,
        abs_best=0.50, abs_worst=-0.20,
        format_as_pct=True,
        description="Year-over-year revenue change. Measures top-line momentum and market demand.",
    ),
    KPIConfig(
        key="currentRatio", display_name="Current Ratio",
        weight=0.05, lower_is_better=False,
        abs_best=3.0, abs_worst=0.3,
        description="Current assets / current liabilities. Above 1.0 means the company can cover its short-term obligations.",
    ),
    KPIConfig(
        key="dividendYield", display_name="Dividend Yield",
        weight=0.05, lower_is_better=False,
        abs_best=0.06, abs_worst=0.0,
        format_as_pct=True,
        description="Annual dividends / share price. Higher yield means more income returned to shareholders.",
    ),
]


def get_kpi_keys() -> list[str]:
    """Return all KPI keys needed from Yahoo Finance."""
    return [cfg.key for cfg in KPI_CONFIGS]


def extract_kpis(info: dict) -> dict[str, Optional[float]]:
    """Extract relevant KPIs from a Yahoo Finance info dict."""
    kpis = {}
    for cfg in KPI_CONFIGS:
        val = info.get(cfg.key)
        if val is not None:
            try:
                kpis[cfg.key] = float(val)
            except (ValueError, TypeError):
                kpis[cfg.key] = None
        else:
            kpis[cfg.key] = None
    return kpis


def compute_sector_averages(all_kpis: list[dict[str, Optional[float]]]) -> dict[str, Optional[float]]:
    """Compute average KPIs across a list of stock KPI dicts."""
    averages = {}
    for cfg in KPI_CONFIGS:
        values = [kpi[cfg.key] for kpi in all_kpis if kpi.get(cfg.key) is not None]
        if values:
            # Use median instead of mean to reduce outlier impact
            values.sort()
            mid = len(values) // 2
            if len(values) % 2 == 0:
                averages[cfg.key] = (values[mid - 1] + values[mid]) / 2
            else:
                averages[cfg.key] = values[mid]
        else:
            averages[cfg.key] = None
    return averages


def _score_absolute(value: float, cfg: KPIConfig) -> float:
    """
    Score a KPI value on a 0-1 scale based on absolute thresholds.
    Returns 1.0 for best, 0.0 for worst.
    """
    if cfg.lower_is_better:
        # Lower is better: best is at abs_best (low), worst at abs_worst (high)
        if value <= cfg.abs_best:
            return 1.0
        if value >= cfg.abs_worst:
            return 0.0
        return 1.0 - (value - cfg.abs_best) / (cfg.abs_worst - cfg.abs_best)
    else:
        # Higher is better: best is at abs_best (high), worst at abs_worst (low)
        if value >= cfg.abs_best:
            return 1.0
        if value <= cfg.abs_worst:
            return 0.0
        return (value - cfg.abs_worst) / (cfg.abs_best - cfg.abs_worst)


def _score_relative(value: float, sector_avg: float, cfg: KPIConfig) -> float:
    """
    Score a KPI value on a 0-1 scale relative to the sector average.
    Returns 0.5 if equal to average, >0.5 if better, <0.5 if worse.
    """
    if sector_avg is None or sector_avg == 0:
        return 0.5  # No comparison possible

    # Calculate percentage difference from sector average
    pct_diff = (value - sector_avg) / abs(sector_avg)

    if cfg.lower_is_better:
        # For lower-is-better metrics, being below average is good
        pct_diff = -pct_diff

    # Map pct_diff to 0-1 scale using sigmoid-like function
    # At 0% diff -> 0.5, at +50% better -> ~0.85, at -50% worse -> ~0.15
    score = 1.0 / (1.0 + math.exp(-4.0 * pct_diff))
    return max(0.0, min(1.0, score))


def calculate_rating(
    stock_kpis: dict[str, Optional[float]],
    sector_averages: dict[str, Optional[float]],
    absolute_weight: float = 0.40,
    relative_weight: float = 0.60,
) -> dict:
    """
    Calculate the overall stock rating (1-10) and per-KPI breakdown.

    Returns:
        {
            "overall_rating": float (1-10),
            "absolute_score": float (1-10),
            "relative_score": float (1-10),
            "kpi_scores": {
                "trailingPE": {"absolute": float, "relative": float, "combined": float},
                ...
            }
        }
    """
    total_abs_weighted = 0.0
    total_rel_weighted = 0.0
    total_weight_used = 0.0
    kpi_scores = {}

    for cfg in KPI_CONFIGS:
        val = stock_kpis.get(cfg.key)
        avg = sector_averages.get(cfg.key)

        if val is None:
            kpi_scores[cfg.key] = {"absolute": None, "relative": None, "combined": None}
            continue

        abs_score = _score_absolute(val, cfg)
        rel_score = _score_relative(val, avg, cfg) if avg is not None else 0.5
        combined = absolute_weight * abs_score + relative_weight * rel_score

        kpi_scores[cfg.key] = {
            "absolute": round(abs_score, 3),
            "relative": round(rel_score, 3),
            "combined": round(combined, 3),
        }

        total_abs_weighted += abs_score * cfg.weight
        total_rel_weighted += rel_score * cfg.weight
        total_weight_used += cfg.weight

    # Normalize if some KPIs were missing
    if total_weight_used > 0:
        total_abs_weighted /= total_weight_used
        total_rel_weighted /= total_weight_used

    overall_raw = absolute_weight * total_abs_weighted + relative_weight * total_rel_weighted
    # Map 0-1 to 1-10
    overall_rating = round(1.0 + overall_raw * 9.0, 1)
    absolute_score = round(1.0 + total_abs_weighted * 9.0, 1)
    relative_score = round(1.0 + total_rel_weighted * 9.0, 1)

    return {
        "overall_rating": overall_rating,
        "absolute_score": absolute_score,
        "relative_score": relative_score,
        "kpi_scores": kpi_scores,
    }


def format_kpi_value(key: str, value: Optional[float]) -> str:
    """Format a KPI value for display."""
    if value is None:
        return "N/A"
    cfg = next((c for c in KPI_CONFIGS if c.key == key), None)
    if cfg is None:
        return str(value)
    if cfg.format_as_pct:
        return f"{value * 100:.{cfg.format_decimals}f}%"
    return f"{value:.{cfg.format_decimals}f}"
