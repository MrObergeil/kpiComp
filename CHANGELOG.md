# Changelog

## 2026-02-27 — Peer Drill-Down, Regional Comparison & Scoring

### Added
- **Stock database** (`data/stocks.json`): 603 enriched stocks from S&P 500, NASDAQ-100, Dow 30, FTSE 100, DAX 40 with sector, industry, market cap, and index membership
- `scripts/build_stock_db.py` build script for stock database (yfinance enrichment, pytickersymbols for EU indices)
- `stock_db.py` query module: get_stock, query_stocks, get_sectors, get_industries, get_market_cap_band
- `peers.py` cascading peer resolution: custom > industry+region > industry global > sector+cap band > sector+region > sector global
- `peer_groups.py` custom peer persistence (server-side JSON at `peer_groups/custom_peers.json`)
- **Peer selection modal**: browse, search, select/deselect peers, recalculate with custom peer set, save as custom
- **Region toggle**: Global / US / Europe button group above KPI table, re-analyzes with region filter
- **KPI sparklines**: inline SVG mini-charts replacing trend arrows, color-coded by direction
- **Expandable KPI rows**: click any KPI row to see year-by-year historical values
- **Score breakdown tooltip**: hover over rating circle to see Absolute / Relative / Trend scores
- **Colored percentage gaps**: difference column shows percentage with green/red text
- **URL sharing**: extended to `?ticker=AMZN&peers=BABA,JD&region=us`
- API endpoints: `GET /api/peers/{ticker}`, `PUT /api/peers/{ticker}`, `DELETE /api/peers/{ticker}`
- API endpoints: `GET /api/taxonomy/sectors`, `GET /api/taxonomy/industries`, `GET /api/stocks`
- `historical_yearly` and `peer_selection` in `/api/analyze` response
- Peer metadata (name, market_cap) in API response for modal display
- `peer_groups/` added to `.gitignore`

### Changed
- **Scoring weights**: absolute 35% / relative 55% / trend 10% (was 30/50/20)
- Peer comparison now uses stock database (603 stocks across 7 indices) instead of S&P 500 only
- Per-ticker KPI cache replaces per-sector cache (enables reuse across different peer sets)
- `/api/analyze/{ticker}` accepts `?peers=` and `?region=` query params
- `data.py` refactored: `analyze_stock()` accepts `peers` and `region` params, uses `peers.resolve_peers()`
- Fallback to legacy S&P 500 peer lookup when stock not in database
- Client-side recalculate() uses updated 35/55/10 weights
- `appState` object replaces `window._stockData` for state management
- Clickable peer count badges open the peer modal
- README updated with full API reference for all endpoints, new project structure, and peer system docs

## 2026-02-27

### Added
- Ticker autocomplete with ~14.9K US + European + Korean + Chinese tickers (SEC EDGAR + pytickersymbols + financedatabase)
- Korean (KOSPI/KOSDAQ) and Chinese (Shanghai/Shenzhen) market tickers with English company names
- `.KQ`, `.SS`, `.SZ` exchange suffixes for auto-resolve in data.py
- `scripts/build_tickers.py` build script to regenerate ticker data
- `GET /api/tickers` endpoint with 24h cache header
- GitHub Actions workflow for monthly automated ticker data refresh
- Client-side typeahead: prefix match on ticker, substring match on company name
- Keyboard navigation (Arrow Up/Down, Enter, Escape) in autocomplete dropdown
- Bumped ticker input maxlength to 20 for European tickers (e.g. BARC.L)

### Changed
- KPI table moved above sentiment indicator cards
- Stock price displayed inline with ticker/company name instead of separate row
- Replaced AGENTS.md with CLAUDE.md (Claude Code compatible config)
- Moved todo.txt content to GitHub issue #1
- NaN/Inf sanitization for JSON API responses
- Headline + summary scoring for sentiment (headline matches weighted 2x)
- Trainable keyword overrides via `train_data/news_keywords.json`
- Log-level validation on frontend log endpoint

### Added
- Sentiment training UI and API routes (`/train`, `/api/train/*`)
- Shares outstanding displayed in short interest card
- `current_price` field in API response

### Removed
- AGENTS.md, todo.txt, unused `None` fields from sentiment response

## 2026-02-26

### Added (UX)
- Shareable URLs: analysis results push `?ticker=AAPL` to URL, auto-analyzes on page load from URL params
- Current stock price displayed below company name in stock header
- Recent searches: last 8 tickers stored in localStorage, shown as clickable chips below search bar
- Sentiment/indicator cards in 2-column CSS grid layout (news + insider cards span full width)
- Mobile improvements: single-column grid, stacked score bars, tighter indicator gaps
- Dynamic page title updates to `TICKER -- Stock Rater` on analysis

### Added
- 5 sentiment indicators: short interest, insider trading, analyst consensus, options flow, Google Trends
- News sentiment & buzz indicator via Finnhub API (headline keyword scoring, bull/bear ratio)
- Reddit social buzz indicator via ApeWisdom API (mention volume, rank, trend)
- Rating system v2: 3-way scoring (absolute 30% + relative 50% + trend 20%), dynamic sector thresholds, 12 KPIs including FCF Yield and PEG Ratio
- KPI tooltips: hover over any KPI name to see its definition and formula
- Toggleable KPI exclusion: checkboxes to exclude KPIs from rating with instant client-side recalculation
- 5-year historical average column: shows stock's own historical KPI averages from financial statements
- Auto-resolve international exchange tickers (`.L`, `.TO`, `.AX`, etc.) when bare symbol fails
- Negative value handling for KPIs: exclude mode (P/E, Forward P/E treated as N/A when negative) and penalize mode (P/B, EV/EBITDA, D/E score 0 when negative)
- Flag tooltips on score column explaining why a KPI was excluded or penalized
- Sector median calculation now filters out negative values for affected KPIs
- Structured JSON logging with rotating file handler

### Fixed
- Tooltip readability on disabled KPI rows (opacity applied to text spans, not parent container)
- Tooltip clipping on first table row
- Blocking async handler, XSS sanitization, path handling, and input validation
- Datetime deprecation warnings (`datetime.utcnow()` → `datetime.now(timezone.utc)`)
- Strip exchange suffixes before calling Finnhub API

### Changed
- Sector peer fetching uses sector map + parallel thread pool for faster lookups

## 2026-02-25

### Fixed
- Updated yfinance to 1.2.0 to fix Yahoo Finance rate limiting

### Changed
- Updated README to reflect flat project structure

## Initial Release

### Added
- Stock rating on 1-10 value scale based on 10 financial KPIs
- Automatic sector detection via Yahoo Finance
- Comparison against S&P 500 sector peer medians
- Combined absolute + relative scoring algorithm
- Session-level caching of sector data (1 hour TTL)
- Web interface + REST API
