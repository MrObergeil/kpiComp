# Stock Rater

A web application that rates stocks on a **1–10 value scale** based on financial KPIs, benchmarked against S&P 500 sector peers.

- **1** = Most expensive / worst value  
- **10** = Cheapest / best value

## Features

- Enter **any stock ticker** — not limited to S&P 500
- Automatic sector detection via Yahoo Finance
- Comparison against **S&P 500 sector peer medians**
- 12 financial KPIs with weighted scoring (including FCF Yield and PEG Ratio)
- **3-way scoring**: absolute (vs dynamic sector thresholds) + relative (vs industry/sector) + trend (improving/deteriorating)
- **Industry-level comparison** when 5+ industry peers are available
- Session-level caching of sector data (1 hour TTL)
- Clean web interface + REST API for programmatic use

## KPIs Used

| KPI | Weight | Interpretation |
|---|---|---|
| P/E Ratio (TTM) | 12% | Lower = cheaper |
| Forward P/E | 10% | Lower = cheaper |
| P/B Ratio | 8% | Lower = cheaper |
| EV/EBITDA | 11% | Lower = cheaper |
| Debt/Equity | 9% | Lower = less risk |
| ROE | 11% | Higher = more profitable |
| Profit Margin | 9% | Higher = more efficient |
| Revenue Growth | 8% | Higher = faster growing |
| Current Ratio | 4% | Higher = more liquid |
| Dividend Yield | 4% | Higher = more income |
| FCF Yield | 8% | Higher = more cash generation |
| PEG Ratio | 6% | Lower = cheaper relative to growth |

## Rating Algorithm

Each KPI gets three sub-scores:
- **Absolute score**: compared against dynamic sector-relative thresholds (20th/80th percentile of peers)
- **Relative score**: compared against the industry or sector median (using a sigmoid function)
- **Trend score**: is the metric improving or deteriorating over the past 5 years?

Final rating = **30% absolute + 50% relative + 20% trend**, mapped to a 1–10 scale.

When trend data is unavailable, it redistributes to ~37.5% absolute + ~62.5% relative. When industry peers are available (5+), relative scoring uses industry comparison instead of the broader sector.

See [docs/rating_improvements.md](rating_improvements.md) for detailed rationale and edge case handling.

## Setup & Run

### Prerequisites
- Python 3.10+
- Internet connection (for Yahoo Finance data)

### Install

```bash
cd kpiComp
pip install -r requirements.txt
```

### Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

## REST API

### Analyze a stock

```
GET /api/analyze/{ticker}
```

**Example:**
```bash
curl http://localhost:8000/api/analyze/MSFT
```

**Response:**
```json
{
  "ticker": "MSFT",
  "company_name": "Microsoft Corporation",
  "sector": "Technology",
  "industry": "Software—Infrastructure",
  "stock_kpis": { ... },
  "sector_averages": { ... },
  "sector_peer_count": 72,
  "industry_peer_count": 12,
  "industry_comparison_active": true,
  "rating": {
    "overall_rating": 5.4,
    "absolute_score": 4.8,
    "relative_score": 5.8,
    "trend_score": 6.2,
    "kpi_scores": { ... }
  },
  "kpi_comparison": [ ... ]
}
```

### Clear cache

```
POST /api/clear-cache
```

## Logging

Structured JSON logging to rotating files and stdout. Covers backend requests, data fetching, and frontend errors.

### Log Location

```
logs/app.log          # current log file
logs/app.log.1-3      # rotated backups (5MB each, 3 max)
```

### Log Format

Each line is a JSON object:
```json
{"ts": "2026-02-26T14:30:00.123+00:00", "level": "INFO", "logger": "data", "msg": "...", "duration_ms": 1234}
```

### What's Logged

- **All HTTP requests** — method, path, status code, response time (via middleware)
- **Ticker searches** — logged from the frontend on each analysis
- **Data fetch events** — cache hits/misses, sector peer fetching with timing
- **Errors** — backend exceptions with tracebacks, frontend JS errors and API failures
- **Silent failures** — cashflow, dividend, and ticker resolution failures (at DEBUG level)

### Frontend Error Reporting

Frontend JS errors and API failures are sent to `POST /api/log` via `sendBeacon`. These appear in the same log file under `"logger": "frontend"`.

### Useful Commands

```bash
# Recent errors
grep '"level": "ERROR"' logs/app.log

# Frontend errors only
grep '"logger": "frontend"' logs/app.log

# Ticker search history
grep "ticker_search" logs/app.log

# Slow requests (>5s) — requires jq
jq 'select(.duration_ms > 5000)' logs/app.log

# Response times
grep "duration_ms" logs/app.log
```

### Configuration

Logging is configured in `logging_config.py`. Defaults: INFO level, 5MB rotation, 3 backups.

## Project Structure

```
kpiComp/
├── main.py              # FastAPI app (routes, middleware, web interface)
├── data.py              # Yahoo Finance data fetching + caching + analysis pipeline
├── rating.py            # Rating algorithm (KPI configs, scoring, formatting)
├── sp500.py             # S&P 500 ticker list
├── logging_config.py    # JSON logging configuration
├── index.html           # Single-page web frontend
├── requirements.txt
├── logs/                # Log files (gitignored)
└── docs/
    ├── README.md
    └── rating_improvements.md  # Detailed changelog of rating system v1 → v2
```

## Notes

- First analysis for a given sector will be slow (~1-2 minutes) as it fetches data for all S&P 500 stocks in that sector. Subsequent analyses in the same sector use cached data.
- The S&P 500 list is a static snapshot. Update `sp500.py` periodically for accuracy.
- Rating algorithm weights and thresholds can be tuned in `rating.py`.
- Data is sourced from Yahoo Finance and is for informational purposes only — not financial advice.
