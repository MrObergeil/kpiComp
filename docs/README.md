# Stock Rater

A web application that rates stocks on a **1--10 value scale** based on financial KPIs, benchmarked against sector peers from major US and European indices.

- **1** = Most expensive / worst value
- **10** = Cheapest / best value

## Features

- Enter **any stock ticker** -- not limited to index constituents
- **603-stock database** covering S&P 500, NASDAQ-100, Dow 30, FTSE 100, DAX 40 with sector/industry/market cap data
- **Cascading peer resolution**: industry > sector+cap band > sector, with optional region filtering
- **Custom peer sets**: select your own comparison group, save per-ticker
- **Region toggle**: compare against Global / US / Europe peers
- 12 financial KPIs with weighted scoring (including FCF Yield and PEG Ratio)
- **3-way scoring**: absolute (35%) + relative (55%) + trend (10%)
- **Industry-level comparison** when 5+ industry peers available
- **KPI sparklines**: mini inline charts showing 5-year KPI trends
- **Expandable KPI rows**: click to see year-by-year historical values
- **Score breakdown tooltip**: hover over rating to see Absolute/Relative/Trend split
- 5 sentiment indicators: news, Reddit buzz, insider trading, analyst consensus, options flow
- Shareable URLs with ticker, peer set, and region params
- Per-ticker KPI caching (1h TTL)
- Web interface + REST API

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
- **Absolute score** (35%): compared against dynamic sector-relative thresholds (20th/80th percentile of peers)
- **Relative score** (55%): compared against the industry or sector median (sigmoid function)
- **Trend score** (10%): is the metric improving or deteriorating over the past 5 years?

Final rating = **35% absolute + 55% relative + 10% trend**, mapped to a 1--10 scale.

When trend data is unavailable, it redistributes proportionally to absolute + relative. When industry peers are available (5+), relative scoring uses industry comparison instead of the broader sector.

### Peer Resolution Cascade

When analyzing a stock, the system picks the best available peer set:

1. **Custom peers** (if saved or passed via URL) -- used directly
2. **Industry peers in selected region** (if >= 5)
3. **Industry peers globally** (if >= 5)
4. **Sector peers with similar market cap** (1/3x--3x) in region (if >= 5)
5. **Sector peers in region** (if >= 5)
6. **Full sector globally** (last resort)

Stocks not in the database fall back to S&P 500 sector matching.

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

### Rebuild Stock Database

Run quarterly or after index rebalancing (~15-30 min):

```bash
python scripts/build_stock_db.py
```

### Rebuild Ticker Autocomplete Data

```bash
python scripts/build_tickers.py
```

## REST API

All endpoints return JSON. Base URL: `http://localhost:8000`

---

### `GET /api/analyze/{ticker}`

Analyze a stock ticker. Returns KPIs, rating, peer comparison, sentiment data.

**Query params:**

| Param | Type | Description |
|---|---|---|
| `peers` | string | Comma-separated peer tickers (e.g. `MSFT,GOOG,AMZN`). Overrides auto peer resolution. |
| `region` | string | Filter peers by region: `us` or `europe`. Omit for global. |

**Examples:**

```bash
# Basic analysis
curl http://localhost:8000/api/analyze/AAPL

# With custom peers
curl "http://localhost:8000/api/analyze/AMZN?peers=BABA,JD,SHOP,MELI,SE"

# US peers only
curl "http://localhost:8000/api/analyze/SAP.DE?region=us"

# Custom peers + region
curl "http://localhost:8000/api/analyze/TSLA?peers=RIVN,LCID,NIO&region=us"
```

**Response includes:**

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "current_price": 182.52,
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "stock_kpis": { "trailingPE": 28.5, "..." : "..." },
  "sector_averages": { "trailingPE": 25.1, "..." : "..." },
  "sector_peer_count": 82,
  "industry_peer_count": 1,
  "industry_comparison_active": false,
  "rating": {
    "overall_rating": 5.4,
    "absolute_score": 4.8,
    "relative_score": 5.8,
    "trend_score": 6.2,
    "kpi_scores": { "..." : "..." }
  },
  "kpi_comparison": [ "..." ],
  "peer_selection": {
    "level": "sector",
    "region": null,
    "count": 82,
    "total_available": 82,
    "message": "82 sector peers (global)",
    "is_custom": false,
    "tickers": ["ACN", "ADBE", "..."]
  },
  "peer_metadata": [
    { "ticker": "ACN", "name": "Accenture plc", "industry": "IT Services", "market_cap": 210000000000 }
  ],
  "historical_yearly": {
    "trailingPE": [["2021-09-25", 27.3], ["2022-09-24", 24.1], "..."],
    "..." : "..."
  },
  "sentiment": { "..." : "..." },
  "reddit_buzz": { "..." : "..." },
  "short_interest": { "..." : "..." },
  "insider_trading": { "..." : "..." },
  "analyst_ratings": { "..." : "..." },
  "options_sentiment": { "..." : "..." },
  "google_trends": { "..." : "..." }
}
```

---

### `GET /api/peers/{ticker}`

Get auto-detected and custom peers for a ticker.

```bash
curl http://localhost:8000/api/peers/AAPL
```

```json
{
  "ticker": "AAPL",
  "custom_peers": null,
  "auto_peers": {
    "tickers": ["ACN", "ADBE", "..."],
    "level": "sector",
    "message": "82 sector peers (global)"
  },
  "in_database": true
}
```

---

### `PUT /api/peers/{ticker}`

Save a custom peer set for a ticker. Persists to disk.

```bash
curl -X PUT http://localhost:8000/api/peers/AMZN \
  -H "Content-Type: application/json" \
  -d '{"peers": ["BABA", "JD", "SHOP", "MELI", "SE"]}'
```

```json
{ "status": "ok", "ticker": "AMZN", "peers": ["BABA", "JD", "SHOP", "MELI", "SE"] }
```

Validation: 2--50 peers required.

---

### `DELETE /api/peers/{ticker}`

Remove custom peer override. Reverts to auto peer resolution.

```bash
curl -X DELETE http://localhost:8000/api/peers/AMZN
```

```json
{ "status": "ok", "ticker": "AMZN", "deleted": true }
```

---

### `GET /api/taxonomy/sectors`

List all sectors in the stock database with stock counts.

```bash
curl http://localhost:8000/api/taxonomy/sectors
```

```json
[
  { "sector": "Basic Materials", "count": 32 },
  { "sector": "Technology", "count": 82 },
  "..."
]
```

---

### `GET /api/taxonomy/industries?sector={sector}`

List industries within a sector.

```bash
curl "http://localhost:8000/api/taxonomy/industries?sector=Technology"
```

```json
[
  { "industry": "Consumer Electronics", "count": 1 },
  { "industry": "Information Technology Services", "count": 8 },
  { "industry": "Semiconductors", "count": 18 },
  "..."
]
```

---

### `GET /api/stocks`

Query the stock database with optional filters. All filters are AND-combined.

**Query params:**

| Param | Type | Description |
|---|---|---|
| `sector` | string | Filter by sector (e.g. `Technology`) |
| `industry` | string | Filter by industry (e.g. `Semiconductors`) |
| `region` | string | `us` or `europe` |
| `index` | string | Index slug: `sp500`, `nasdaq100`, `dow30`, `ftse100`, `dax40` |

```bash
# All European tech stocks
curl "http://localhost:8000/api/stocks?sector=Technology&region=europe"

# FTSE 100 financials
curl "http://localhost:8000/api/stocks?sector=Financial%20Services&index=ftse100"

# All semiconductors
curl "http://localhost:8000/api/stocks?industry=Semiconductors"
```

```json
[
  {
    "ticker": "NVDA",
    "name": "NVIDIA Corporation",
    "sector": "Technology",
    "industry": "Semiconductors",
    "market_cap": 2800000000000,
    "region": "US",
    "indices": ["nasdaq100", "sp500"]
  },
  "..."
]
```

---

### `GET /api/tickers`

Full ticker list (~14.9K entries) for client-side autocomplete. Cached for 24h.

```bash
curl http://localhost:8000/api/tickers
```

```json
[
  { "t": "AAPL", "n": "Apple Inc", "e": "Nasdaq" },
  { "t": "BARC.L", "n": "Barclays Plc", "e": "LSE" },
  "..."
]
```

---

### `POST /api/clear-cache`

Clear all in-memory caches (ticker KPIs, sector data, sentiment, etc.).

```bash
curl -X POST http://localhost:8000/api/clear-cache
```

```json
{ "status": "ok", "message": "Cache cleared." }
```

---

### `POST /api/log`

Receive frontend log entries. Used internally by the web UI.

```bash
curl -X POST http://localhost:8000/api/log \
  -H "Content-Type: application/json" \
  -d '{"level": "ERROR", "message": "Something broke", "context": {}}'
```

---

### Training UI Endpoints

The sentiment training UI is served at `/train` and uses these API routes:

| Endpoint | Method | Description |
|---|---|---|
| `/train` | GET | Serve training UI page |
| `/train/api/articles/{ticker}` | GET | Fetch scored articles for a ticker |
| `/train/api/keywords/{indicator}` | GET | Get base + override keywords |
| `/train/api/keywords/{indicator}` | POST | Save keyword overrides |
| `/train/api/feedback` | GET | Retrieve stored feedback |
| `/train/api/feedback` | POST | Submit new feedback entry |

## Logging

Structured JSON logging to rotating files and stdout.

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

### Useful Commands

```bash
# Recent errors
grep '"level": "ERROR"' logs/app.log

# Frontend errors only
grep '"logger": "frontend"' logs/app.log

# Ticker search history
grep "ticker_search" logs/app.log

# Slow requests (>5s)
jq 'select(.duration_ms > 5000)' logs/app.log
```

## Project Structure

```
kpiComp/
├── main.py                  # FastAPI app (routes, middleware)
├── data.py                  # Yahoo Finance data fetching + analysis pipeline
├── rating.py                # Rating algorithm (KPI configs, scoring)
├── stock_db.py              # Stock database queries (loads data/stocks.json)
├── peers.py                 # Cascading peer resolution logic
├── peer_groups.py           # Custom peer persistence
├── sp500.py                 # S&P 500 ticker list (legacy, seed data)
├── sentiment.py             # News sentiment via Finnhub
├── reddit_buzz.py           # Reddit mentions via ApeWisdom
├── insider_trading.py       # SEC Form 4 via Finnhub
├── analyst_ratings.py       # Analyst consensus via Finnhub
├── options_sentiment.py     # Options flow via yfinance
├── google_trends.py         # Search interest via pytrends
├── logging_config.py        # JSON logging configuration
├── train.py                 # Sentiment training UI routes
├── index.html               # Single-page web frontend
├── requirements.txt
├── data/
│   ├── tickers.json         # ~14.9K tickers for autocomplete
│   └── stocks.json          # 603 enriched stocks for peer comparison
├── scripts/
│   ├── build_tickers.py     # Rebuild tickers.json
│   └── build_stock_db.py    # Rebuild stocks.json
├── peer_groups/             # Custom peer sets (gitignored, runtime data)
├── train_data/              # Sentiment training data (gitignored)
├── logs/                    # Log files (gitignored)
└── docs/
    ├── README.md
    └── rating_improvements.md
```

## Notes

- First analysis for a given sector may be slow (~1-2 min) as it fetches KPIs for all peer stocks. Subsequent analyses reuse cached per-ticker data.
- The stock database (`data/stocks.json`) is a point-in-time snapshot. Run `scripts/build_stock_db.py` quarterly.
- Stocks not in the database fall back to S&P 500 sector matching.
- Rating algorithm weights and thresholds can be tuned in `rating.py`.
- Data sourced from Yahoo Finance -- for informational purposes only, not financial advice.
