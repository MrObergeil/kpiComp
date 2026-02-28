# Changelog

## 2026-02-28 — Expand Stock DB: DAX, EURO STOXX 50, Russell 2000

### Added
- **EURO STOXX 50** index via Wikipedia scrape (50 tickers with home-exchange suffixes)
- **Russell 2000** index via iShares IWM ETF holdings CSV (~1939 tickers)
- `get_eurostoxx50_tickers()` and `get_russell2000_tickers()` in `build_stock_db.py`
- Total unique tickers: ~2957 (up from ~1600)

### Changed
- Removed CAC 40 from pytickersymbols fetch (covered by EURO STOXX 50)

## 2026-02-28 — Multi-Select Sector & Industry Filters

### Changed
- **Sector scan**: sector and industry pickers are now multi-select dropdowns — scan across multiple sectors/industries in one pass
- `sector_scan.py`: `sector`/`industry` params replaced with comma-separated `sectors`/`industries`, unions results by ticker
- `sector_scan.html`: custom `MultiSelect` dropdown component with checkboxes, All/None actions, click-outside-to-close
- `main.py`: new `GET /api/taxonomy/industries-multi` endpoint accepting comma-separated sectors
- `stock_db.py`: new `get_industries_multi()` returns union of industries across sectors

## 2026-02-28 — Sector Scan

### Added
- **Sector scan page** (`/sector-scan`): scan an entire sector or industry, rank all stocks by value score in a sortable table
- `sector_scan.py` router with SSE streaming endpoint for real-time scan progress
- `sector_scan.html` UI: sector/industry pickers, region toggle, progress bar, sortable results table with toggleable KPI columns
- Column preferences saved to localStorage
- Click any row to open the stock in the main analyzer
- Stocks scored against the scanned peer set using existing rating algorithm (absolute + relative, no trend)
- 10 parallel workers, per-ticker KPI cache reused across scans

### Changed
- `data.py`: renamed `_fetch_peer_kpis` to `fetch_ticker_kpis` (now public for reuse by sector scan)
- `main.py`: mounted sector_scan_router
- Added nav links to sector-scan from index.html and train.html

## 2026-02-28 — Expand European Ticker Coverage

### Changed
- `build_tickers.py`: merged `fetch_asian_tickers()` into `fetch_fd_tickers()` — now pulls European equities from financedatabase in addition to Asian markets
- Filters to primary exchanges only (PAR, AMS, LSE, FRA, MIL, MCE, STO, CPH, HEL, OSL, EBS, VIE, ATH, PRA, BRU, LIS) — excludes OTC pink sheets, German regional exchanges, and duplicate listings
- Ticker count: ~14.9K → ~19.8K (+~5K European equities from 19 countries)
- Fixes stocks like ETL.PA (Eutelsat) not appearing in autocomplete because they weren't in any pytickersymbols index

## 2026-02-28 — Multi-Ticker Dedup & Sentiment Merging

### Added
- **Ticker dedup**: companies with multiple tickers (e.g., Rheinmetall: RHM.F, RHMB.F, RNMBF, RNMBY) now show one autocomplete result — the primary home-exchange listing
- **Exchange tier heuristic**: picks primary ticker per company using exchange priority (NASDAQ/NYSE/XETRA > Frankfurt/Paris > OTC/ADR), with shorter ticker as tiebreaker
- **Sentiment merging**: `fetch_sentiment_multi()` and `fetch_articles_multi()` in `sentiment.py` — fetch articles across all ticker aliases, deduplicate by headline, score merged set
- **`/api/ticker-aliases/{ticker}` endpoint**: returns all tickers sharing the same company name
- **`p` (primary) field** on ticker data served by `/api/tickers` — client uses this for dedup

### Changed
- `filterTickers()` in `index.html` deduplicates autocomplete results by company name, keeping primary ticker
- `analyze_stock()` in `data.py` accepts `ticker_aliases` param, uses `fetch_sentiment_multi()` when aliases exist
- `train.py` `/train/api/articles/{ticker}` merges articles across aliases via `fetch_articles_multi()`
- `_ticker_to_aliases` dict built at startup in `main.py`, exposed via `app.state` for router access

## 2026-02-28 — Logging Infrastructure Improvements

### Added
- **Env-based log level**: `LOG_LEVEL` env var (default `INFO`) controls root log level in `logging_config.py`
- **Request ID middleware**: every HTTP request gets a `uuid4` request ID, threaded through logs as `request_id` field, returned as `X-Request-ID` response header, stored on `request.state.request_id`
- **Logging in silent modules**: `peers.py` (cascade level + peer count at INFO, fallback steps at DEBUG), `stock_db.py` (DB load at INFO), `rating.py` (final score at DEBUG), `sentiment_score.py` (composite score + weight redistribution at DEBUG)
- **`--verbose` flag** on `scripts/build_stock_db.py` and `scripts/build_tickers.py` for DEBUG output

### Changed
- Build scripts (`build_stock_db.py`, `build_tickers.py`) migrated from `print()` to structured JSON logging via `setup_logging()`
- `train.py` logger now used for keyword override saves and feedback submissions
- `setup_logging()` signature changed: `level` param defaults to `None` (reads from `LOG_LEVEL` env) instead of hardcoded `logging.INFO`

## 2026-02-28 — Expand Stock Database with S&P 400 & S&P 600

### Added
- **S&P MidCap 400** and **S&P SmallCap 600** index scraping in `scripts/build_stock_db.py` via Wikipedia + `pandas.read_html()`
- `get_sp400_tickers()` and `get_sp600_tickers()` functions with shared `_scrape_wikipedia_tickers()` helper
- User-Agent header to avoid Wikipedia 403s
- ~1000 net new mid/small-cap US stocks (total ~1576, up from ~603)
- Index slugs `sp400` and `sp600` in stock entries

## 2026-02-28 — Feedback Loop in Sentiment Scoring

### Added
- **Feedback overrides**: user corrections from training UI now feed back into `_score_article()` — corrected headlines use the user's score instead of re-computing keywords
- **Keyword accuracy stats**: `GET /train/api/keyword-stats` endpoint analyzes feedback to show per-keyword correct/incorrect counts
- **Problem Keywords sidebar**: training UI shows keywords with <50% accuracy (min 3 appearances) with one-click remove

## 2026-02-28 — Composite Sentiment Score & UI Polish

### Added
- **Composite sentiment score**: weighted signal from 4 directional indicators (analyst consensus 35%, options flow 30%, news sentiment 20%, insider trading 15%) displayed as -1.0 to +1.0 gauge above sentiment cards
- Registry-based indicator system (`sentiment_score.py`) — add/remove indicators by editing one list
- Auto weight redistribution when indicators are unavailable, with confidence levels (high/medium/low)
- Per-indicator breakdown chips showing individual scores and effective weights
- `python-dotenv` loading for `FINNHUB_API_KEY` via `.env` file

### Fixed
- Region toggle buttons overlapping — moved border to parent container
- Region switching now does smooth in-place reload instead of full page flash

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
