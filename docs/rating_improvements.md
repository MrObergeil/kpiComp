# Rating System Improvements

## Original System (v1)

The v1 rating system scored stocks on 10 KPIs using a 2-dimensional approach:

- **10 KPIs**: P/E, Forward P/E, P/B, EV/EBITDA, Debt/Equity, ROE, Profit Margin, Revenue Growth, Current Ratio, Dividend Yield
- **Scoring**: 40% absolute (static thresholds) + 60% relative (vs sector median)
- **Thresholds**: Fixed values for all sectors (e.g., P/E 5-60 range regardless of sector)
- **Comparison**: Sector-level only (Technology = SaaS = Semiconductors = Hardware)

### Limitations

1. **Sector-blind thresholds** — P/E 25 penalized equally for tech and utilities
2. **No cash flow metrics** — Earnings are easily manipulated; FCF is not
3. **No growth adjustment** — P/E penalizes fast growers with no PEG-style correction
4. **Snapshot-only** — No credit for improving or deteriorating fundamentals
5. **Sector too broad** — SaaS companies compared against semiconductor firms

---

## Improvements Implemented (v2)

### 1. Dynamic Sector-Relative Thresholds

**Problem**: Static absolute thresholds (P/E 5-60) ignore that "normal" ranges differ dramatically by sector. A utility at P/E 20 is expensive; a tech stock at P/E 20 is cheap.

**Solution**: `compute_sector_thresholds()` uses the 20th and 80th percentile of sector peer values as dynamic "good" and "bad" thresholds.

- For lower-is-better KPIs: p20 = good, p80 = bad
- For higher-is-better KPIs: p80 = good, p20 = bad
- Requires >= 5 peers with valid data; falls back to static thresholds otherwise
- If p20 == p80 (no differentiation), scores 0.5

**Rationale**: A stock's absolute score now reflects whether it's cheap or expensive *for its sector*, not against a universal standard.

### 2. Industry-Level Granularity

**Problem**: Sector-level comparison is too broad. Within Technology, SaaS companies have fundamentally different profiles than semiconductor manufacturers.

**Solution**: `get_industry_peers_kpis()` filters sector peers by yfinance's `industry` field. If >= 5 industry peers exist, their median is used for relative scoring instead of the sector median.

- Falls back to sector comparison when < 5 industry peers
- UI indicates when industry comparison is active
- Industry peer count shown in stock metadata

**Rationale**: Comparing MSFT to other "Software - Infrastructure" companies is more meaningful than comparing it to all Technology stocks.

### 3. FCF Yield (New KPI)

**Problem**: All existing metrics use earnings-based valuation. Earnings are subject to accounting choices (depreciation methods, one-time charges). Free cash flow is harder to manipulate.

**Solution**: FCF Yield = Free Cash Flow / Market Cap

- Weight: 8%
- Higher is better (more cash generation per dollar of price)
- abs_best: 10%, abs_worst: -2%
- negative_handling: "allow" — negative FCF scores naturally low
- Historical: computed from `t.cashflow` "Free Cash Flow" row

**Rationale**: FCF measures actual cash the business generates. A stock can have positive earnings but negative FCF (and vice versa). This adds a genuinely different signal.

### 4. PEG Ratio (New KPI)

**Problem**: P/E penalizes fast-growing companies. A stock with P/E 40 and 40% earnings growth is arguably cheaper than P/E 15 with 5% growth.

**Solution**: PEG Ratio = P/E / Earnings Growth Rate

- Weight: 6%
- Lower is better (below 1.0 suggests undervalued relative to growth)
- abs_best: 0.5, abs_worst: 3.0
- negative_handling: "exclude" — negative PEG (from negative growth) is meaningless
- Historical: computed from historical P/E and YoY net income growth (only when both positive)

**Rationale**: PEG adjusts valuation for growth, giving a fairer picture for high-growth stocks.

### 5. Trend Scoring

**Problem**: Ratings are snapshot-only. A company whose margins are rapidly improving gets the same score as one whose margins are deteriorating, if they happen to be at the same level today.

**Solution**: `_score_trend()` compares the most recent year's KPI value against the average of prior years.

- `improvement_ratio = (recent - prior_avg) / abs(prior_avg)`
- Flipped for lower-is-better metrics
- Mapped through sigmoid: `1 / (1 + exp(-3 * improvement_ratio))`
- Requires >= 2 data points; None otherwise

**Scoring split**: 30% absolute + 50% relative + 20% trend (was 40/60/0)

When trend data is unavailable for a KPI, its trend weight redistributes proportionally:
- ~37.5% absolute + ~62.5% relative (close to the old 40/60 split)

**Rationale**: Trend direction matters for investment decisions. An improving business is worth more than a deteriorating one at the same current metrics.

---

## New Weight Distribution

| KPI | v1 Weight | v2 Weight | Change |
|-----|-----------|-----------|--------|
| P/E Ratio (TTM) | 15% | 12% | -3% |
| Forward P/E | 12% | 10% | -2% |
| P/B Ratio | 10% | 8% | -2% |
| EV/EBITDA | 12% | 11% | -1% |
| Debt/Equity | 10% | 9% | -1% |
| ROE | 12% | 11% | -1% |
| Profit Margin | 10% | 9% | -1% |
| Revenue Growth | 9% | 8% | -1% |
| Current Ratio | 5% | 4% | -1% |
| Dividend Yield | 5% | 4% | -1% |
| **FCF Yield** | -- | **8%** | new |
| **PEG Ratio** | -- | **6%** | new |

Weight reductions were spread across all existing KPIs, with larger reductions on valuation multiples (P/E, Forward P/E, P/B) since FCF Yield and PEG Ratio partially overlap their signal.

---

## 3-Way Scoring Formula

```
per_kpi_score = 0.30 * absolute + 0.50 * relative + 0.20 * trend

# If trend is None for a KPI:
per_kpi_score = 0.375 * absolute + 0.625 * relative

overall = sum(per_kpi_score * weight) / sum(weight)
rating = 1.0 + overall * 9.0  # maps 0-1 to 1-10
```

---

## Fallback Behavior

| Scenario | Behavior |
|---|---|
| < 5 sector peers for dynamic thresholds | Use static abs_best/abs_worst from KPIConfig |
| < 5 industry peers | Use sector median for relative scoring |
| p20 == p80 in dynamic thresholds | Score 0.5 (can't differentiate) |
| KPI value is None | Skip KPI, redistribute weight to remaining KPIs |
| Negative P/E, Forward P/E, PEG | Excluded (meaningless ratios) |
| Negative P/B, EV/EBITDA, D/E | Penalized (score 0 — distressed signal) |
| Negative FCF | Allowed — scores naturally low through normal scoring |
| No historical data | Trend = None, weight goes to abs/rel |
| Only 1 year of history | Trend = None (need >= 2 data points) |
| FCF missing from yfinance | fcfYield = None, weight redistributed |
| Sector average is 0 or None | Relative score defaults to 0.5 |

---

## Future Improvement Ideas

- **Momentum scoring**: Price performance vs peers over 3/6/12 months
- **Quality composite**: Combine ROE, margins, and FCF consistency into a single quality factor
- **Insider activity**: Insider buying/selling as a sentiment signal
- **Analyst consensus**: Forward estimates convergence/divergence
- **Sub-industry granularity**: More specific industry classification than yfinance provides
- **International peers**: Extend beyond S&P 500 for non-US stocks
- **Configurable weights**: Let users adjust KPI weights in the UI
- **Sector-specific KPIs**: Different KPI sets for financials (NIM, CET1) vs tech (Rule of 40)
