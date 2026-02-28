"""
Stock Rating Algorithm v2

Rates a stock on a scale of 1-10 based on financial KPIs.
1 = most expensive / worst value
10 = cheapest / best value

The score combines:
  - Absolute scoring: How does each KPI compare to sector-relative thresholds?
  - Relative scoring: How does each KPI compare to the sector/industry average?
  - Trend scoring: Is the KPI improving or deteriorating over time?

Final score = weighted blend of absolute (35%) + relative (55%) + trend (10%).
When trend data is unavailable, redistributes proportionally to abs + rel.

KPIs used (12):
  - P/E Ratio (trailingPE): Lower is cheaper.
  - Forward P/E (forwardPE): Lower is cheaper.
  - P/B Ratio (priceToBook): Lower is cheaper.
  - EV/EBITDA (enterpriseToEbitda): Lower is cheaper.
  - Debt/Equity (debtToEquity): Lower is better.
  - ROE (returnOnEquity): Higher is better.
  - Profit Margin (profitMargins): Higher is better.
  - Revenue Growth (revenueGrowth): Higher is better.
  - Current Ratio (currentRatio): Higher is better.
  - Dividend Yield (dividendYield): Higher is better.
  - FCF Yield (fcfYield): Higher is better. Free cash flow / market cap.
  - PEG Ratio (pegRatio): Lower is better. P/E adjusted for growth.
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
    # How to handle negative values: "allow" (default), "exclude" (treat as N/A), "penalize" (score 0)
    negative_handling: str = "allow"
    negative_reason: str = ""  # Human-readable reason shown in UI tooltips
    format_as_pct: bool = False  # Display as percentage
    format_decimals: int = 2
    description: str = ""


KPI_CONFIGS = [
    KPIConfig(
        key="trailingPE", display_name="P/E Ratio (TTM)",
        weight=0.12, lower_is_better=True,
        abs_best=5.0, abs_worst=60.0,
        negative_handling="exclude",
        negative_reason="Negative earnings make P/E meaningless as a valuation metric",
        description="Price / trailing 12-month earnings. Lower means you're paying less per dollar of profit.",
    ),
    KPIConfig(
        key="forwardPE", display_name="Forward P/E",
        weight=0.10, lower_is_better=True,
        abs_best=5.0, abs_worst=50.0,
        negative_handling="exclude",
        negative_reason="Expected losses make forward P/E meaningless",
        description="Price / estimated future earnings. Based on analyst forecasts for the next 12 months.",
    ),
    KPIConfig(
        key="priceToBook", display_name="P/B Ratio",
        weight=0.08, lower_is_better=True,
        abs_best=0.5, abs_worst=20.0,
        negative_handling="penalize",
        negative_reason="Negative book value indicates liabilities exceed assets",
        description="Market price / book value per share. Below 1.0 suggests the stock trades below its net asset value.",
    ),
    KPIConfig(
        key="enterpriseToEbitda", display_name="EV/EBITDA",
        weight=0.11, lower_is_better=True,
        abs_best=3.0, abs_worst=40.0,
        negative_handling="penalize",
        negative_reason="Negative EBITDA indicates operating losses",
        description="Enterprise value / EBITDA. Accounts for debt, useful for comparing companies with different capital structures.",
    ),
    KPIConfig(
        key="debtToEquity", display_name="Debt/Equity",
        weight=0.09, lower_is_better=True,
        abs_best=0.0, abs_worst=300.0,
        negative_handling="penalize",
        negative_reason="Negative equity indicates balance sheet insolvency",
        description="Total debt / shareholder equity. Higher means more leverage and financial risk.",
    ),
    KPIConfig(
        key="returnOnEquity", display_name="ROE",
        weight=0.11, lower_is_better=False,
        abs_best=0.40, abs_worst=-0.10,
        format_as_pct=True,
        description="Net income / shareholder equity. Measures how efficiently the company turns equity into profit.",
    ),
    KPIConfig(
        key="profitMargins", display_name="Profit Margin",
        weight=0.09, lower_is_better=False,
        abs_best=0.40, abs_worst=-0.10,
        format_as_pct=True,
        description="Net income / revenue. Shows how much of each dollar earned the company keeps as profit.",
    ),
    KPIConfig(
        key="revenueGrowth", display_name="Revenue Growth",
        weight=0.08, lower_is_better=False,
        abs_best=0.50, abs_worst=-0.20,
        format_as_pct=True,
        description="Year-over-year revenue change. Measures top-line momentum and market demand.",
    ),
    KPIConfig(
        key="currentRatio", display_name="Current Ratio",
        weight=0.04, lower_is_better=False,
        abs_best=3.0, abs_worst=0.3,
        description="Current assets / current liabilities. Above 1.0 means the company can cover its short-term obligations.",
    ),
    KPIConfig(
        key="dividendYield", display_name="Dividend Yield",
        weight=0.04, lower_is_better=False,
        abs_best=0.06, abs_worst=0.0,
        format_as_pct=True,
        description="Annual dividends / share price. Higher yield means more income returned to shareholders.",
    ),
    KPIConfig(
        key="fcfYield", display_name="FCF Yield",
        weight=0.08, lower_is_better=False,
        abs_best=0.10, abs_worst=-0.02,
        negative_handling="allow",
        format_as_pct=True,
        description="Free cash flow / market cap. Measures how much real cash the business generates relative to its price.",
    ),
    KPIConfig(
        key="pegRatio", display_name="PEG Ratio",
        weight=0.06, lower_is_better=True,
        abs_best=0.5, abs_worst=3.0,
        negative_handling="exclude",
        negative_reason="Negative PEG indicates negative earnings growth — ratio is meaningless",
        description="P/E divided by earnings growth rate. Adjusts valuation for growth — below 1.0 suggests undervalued relative to growth.",
    ),
]


def get_kpi_keys() -> list[str]:
    """Return all KPI keys needed from Yahoo Finance."""
    return [cfg.key for cfg in KPI_CONFIGS]


def extract_kpis(info: dict) -> dict[str, Optional[float]]:
    """Extract relevant KPIs from a Yahoo Finance info dict."""
    kpis = {}
    for cfg in KPI_CONFIGS:
        if cfg.key == "fcfYield":
            fcf = info.get("freeCashflow")
            mcap = info.get("marketCap")
            if fcf is not None and mcap is not None and mcap > 0:
                try:
                    kpis[cfg.key] = float(fcf) / float(mcap)
                except (ValueError, TypeError):
                    kpis[cfg.key] = None
            else:
                kpis[cfg.key] = None
            continue

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
    """Compute median KPIs across a list of stock KPI dicts."""
    averages = {}
    for cfg in KPI_CONFIGS:
        values = [kpi[cfg.key] for kpi in all_kpis if kpi.get(cfg.key) is not None]
        # Exclude negative values for KPIs where negatives are meaningless or distressed
        if cfg.negative_handling != "allow":
            values = [v for v in values if v >= 0]
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


def compute_sector_thresholds(peers_kpis: list[dict], min_peers: int = 5) -> dict[str, tuple | None]:
    """
    Compute dynamic absolute thresholds from sector peer data.
    Uses 20th/80th percentile as good/bad boundaries.
    Returns {kpi_key: (best, worst) | None}.
    """
    thresholds = {}
    for cfg in KPI_CONFIGS:
        values = [kpi[cfg.key] for kpi in peers_kpis if kpi.get(cfg.key) is not None]
        if cfg.negative_handling != "allow":
            values = [v for v in values if v >= 0]
        if len(values) >= min_peers:
            values.sort()
            n = len(values)
            p20 = values[int(n * 0.2)]
            p80 = values[min(int(n * 0.8), n - 1)]
            if abs(p20 - p80) < 1e-10:
                thresholds[cfg.key] = None
            elif cfg.lower_is_better:
                # Lower-is-better: p20 (low) = good, p80 (high) = bad
                thresholds[cfg.key] = (p20, p80)
            else:
                # Higher-is-better: p80 (high) = good, p20 (low) = bad
                thresholds[cfg.key] = (p80, p20)
        else:
            thresholds[cfg.key] = None
    return thresholds


def _score_absolute(value: float, cfg: KPIConfig, thresholds: tuple | None = None) -> float:
    """
    Score a KPI value on a 0-1 scale based on absolute thresholds.
    Uses dynamic sector thresholds when provided, falls back to static config.
    """
    best = thresholds[0] if thresholds else cfg.abs_best
    worst = thresholds[1] if thresholds else cfg.abs_worst

    if cfg.lower_is_better:
        if value <= best:
            return 1.0
        if value >= worst:
            return 0.0
        return 1.0 - (value - best) / (worst - best)
    else:
        if value >= best:
            return 1.0
        if value <= worst:
            return 0.0
        return (value - worst) / (best - worst)


def _score_relative(value: float, sector_avg: float, cfg: KPIConfig) -> float:
    """
    Score a KPI value on a 0-1 scale relative to a comparison average.
    Returns 0.5 if equal to average, >0.5 if better, <0.5 if worse.
    """
    if sector_avg is None or sector_avg == 0:
        return 0.5  # No comparison possible

    pct_diff = (value - sector_avg) / abs(sector_avg)

    if cfg.lower_is_better:
        pct_diff = -pct_diff

    score = 1.0 / (1.0 + math.exp(-4.0 * pct_diff))
    return max(0.0, min(1.0, score))


def _score_trend(yearly_data: list | None, cfg: KPIConfig) -> float | None:
    """
    Score the improvement trend of a KPI over time.
    Returns 0-1 (0.5 = flat, >0.5 = improving, <0.5 = deteriorating).
    Returns None if insufficient data (need >= 2 points).
    """
    if not yearly_data or len(yearly_data) < 2:
        return None

    sorted_data = sorted(yearly_data, key=lambda x: x[0])
    values = [v for _, v in sorted_data]

    recent = values[-1]
    prior_avg = sum(values[:-1]) / len(values[:-1])

    if abs(prior_avg) < 1e-10:
        return 0.5

    improvement_ratio = (recent - prior_avg) / abs(prior_avg)

    if cfg.lower_is_better:
        improvement_ratio = -improvement_ratio

    score = 1.0 / (1.0 + math.exp(-3.0 * improvement_ratio))
    return max(0.0, min(1.0, score))


def calculate_rating(
    stock_kpis: dict[str, Optional[float]],
    sector_averages: dict[str, Optional[float]],
    industry_averages: dict[str, Optional[float]] | None = None,
    sector_thresholds: dict[str, tuple | None] | None = None,
    historical_yearly: dict[str, list | None] | None = None,
    absolute_weight: float = 0.35,
    relative_weight: float = 0.55,
    trend_weight: float = 0.10,
) -> dict:
    """
    Calculate the overall stock rating (1-10) and per-KPI breakdown.

    Uses 3-way scoring: absolute (35%) + relative (55%) + trend (10%).
    Prefers industry averages over sector averages for relative scoring.
    Uses dynamic sector thresholds for absolute scoring when available.
    When trend data is unavailable for a KPI, redistributes that weight.
    """
    total_abs_weighted = 0.0
    total_rel_weighted = 0.0
    total_trend_weighted = 0.0
    total_weight_used = 0.0
    total_trend_weight_used = 0.0
    kpi_scores = {}

    for cfg in KPI_CONFIGS:
        val = stock_kpis.get(cfg.key)
        # Prefer industry average, fall back to sector
        comparison_avg = None
        if industry_averages and industry_averages.get(cfg.key) is not None:
            comparison_avg = industry_averages[cfg.key]
        else:
            comparison_avg = sector_averages.get(cfg.key)

        if val is None:
            kpi_scores[cfg.key] = {
                "absolute": None, "relative": None, "trend": None,
                "combined": None, "flag": None, "flag_reason": None,
            }
            continue

        # Handle negative values per KPI config
        if val < 0 and cfg.negative_handling == "exclude":
            kpi_scores[cfg.key] = {
                "absolute": None, "relative": None, "trend": None,
                "combined": None, "flag": "excluded", "flag_reason": cfg.negative_reason,
            }
            continue

        if val < 0 and cfg.negative_handling == "penalize":
            kpi_scores[cfg.key] = {
                "absolute": 0.0, "relative": 0.0, "trend": None,
                "combined": 0.0, "flag": "penalized", "flag_reason": cfg.negative_reason,
            }
            total_weight_used += cfg.weight
            continue

        # Get dynamic thresholds for this KPI
        kpi_thresholds = sector_thresholds.get(cfg.key) if sector_thresholds else None

        abs_score = _score_absolute(val, cfg, kpi_thresholds)
        rel_score = _score_relative(val, comparison_avg, cfg) if comparison_avg is not None else 0.5

        # Trend scoring
        yearly = historical_yearly.get(cfg.key) if historical_yearly else None
        trend_score = _score_trend(yearly, cfg)

        # Compute combined score with weight redistribution if trend unavailable
        if trend_score is not None:
            combined = absolute_weight * abs_score + relative_weight * rel_score + trend_weight * trend_score
            total_trend_weighted += trend_score * cfg.weight
            total_trend_weight_used += cfg.weight
        else:
            # Redistribute trend weight proportionally to abs/rel
            aw = absolute_weight / (absolute_weight + relative_weight)
            rw = relative_weight / (absolute_weight + relative_weight)
            combined = aw * abs_score + rw * rel_score

        kpi_scores[cfg.key] = {
            "absolute": round(abs_score, 3),
            "relative": round(rel_score, 3),
            "trend": round(trend_score, 3) if trend_score is not None else None,
            "combined": round(combined, 3),
            "flag": None,
            "flag_reason": None,
        }

        total_abs_weighted += abs_score * cfg.weight
        total_rel_weighted += rel_score * cfg.weight
        total_weight_used += cfg.weight

    # Normalize
    if total_weight_used > 0:
        total_abs_weighted /= total_weight_used
        total_rel_weighted /= total_weight_used

    trend_aggregate = None
    if total_trend_weight_used > 0:
        total_trend_weighted /= total_trend_weight_used
        trend_aggregate = total_trend_weighted

    # Overall raw score
    if trend_aggregate is not None:
        overall_raw = absolute_weight * total_abs_weighted + relative_weight * total_rel_weighted + trend_weight * trend_aggregate
    else:
        aw = absolute_weight / (absolute_weight + relative_weight)
        rw = relative_weight / (absolute_weight + relative_weight)
        overall_raw = aw * total_abs_weighted + rw * total_rel_weighted

    overall_rating = round(1.0 + overall_raw * 9.0, 1)
    absolute_score = round(1.0 + total_abs_weighted * 9.0, 1)
    relative_score = round(1.0 + total_rel_weighted * 9.0, 1)
    trend_score_mapped = round(1.0 + trend_aggregate * 9.0, 1) if trend_aggregate is not None else None

    return {
        "overall_rating": overall_rating,
        "absolute_score": absolute_score,
        "relative_score": relative_score,
        "trend_score": trend_score_mapped,
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
