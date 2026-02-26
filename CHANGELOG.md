# Changelog

## 2026-02-26

### Added
- KPI tooltips: hover over any KPI name to see its definition and formula
- Toggleable KPI exclusion: checkboxes to exclude KPIs from rating with instant client-side recalculation
- 5-year historical average column: shows stock's own historical KPI averages from financial statements
- Auto-resolve international exchange tickers (`.L`, `.TO`, `.AX`, etc.) when bare symbol fails

### Added
- Negative value handling for KPIs: exclude mode (P/E, Forward P/E treated as N/A when negative) and penalize mode (P/B, EV/EBITDA, D/E score 0 when negative)
- Flag tooltips on score column explaining why a KPI was excluded or penalized
- Sector median calculation now filters out negative values for affected KPIs

### Fixed
- Tooltip readability on disabled KPI rows (opacity applied to text spans, not parent container)

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
