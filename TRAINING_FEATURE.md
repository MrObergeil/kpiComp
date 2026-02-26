# Sentiment Training Feature

Temporary feature for tuning keyword-based sentiment scoring. Browse scored articles, flag misclassifications, and manage keyword overrides — all persisted. Designed to be removed once keyword tuning is complete.

## Architecture

### Files (all new)
- `train.py` — FastAPI APIRouter with training endpoints
- `train.html` — Self-contained training UI (inline CSS/JS)
- `train_data/` — Persistent JSON storage (gitignored)
  - `news_keywords.json` — keyword overrides for news indicator
  - `feedback.json` — article-level feedback log

### Modified files
- `sentiment.py` — changes:
  - Added imports: `json`, `pathlib.Path`
  - Added `_TRAIN_DATA_DIR` constant (line 29)
  - Added `_get_effective_keywords()` — merges base sets with `train_data/news_keywords.json`
  - Replaced `_score_headline()` with `_score_article(headline, summary, bullish, bearish)` — scores both headline (2x weight) and summary (1x weight), returns `(score, matched_keywords_dict)`
  - Added `_fetch_raw_articles(ticker)` — extracted Finnhub API call with cache that stores raw articles
  - Refactored `fetch_sentiment()` to use `_fetch_raw_articles` + `_score_article` + `_get_effective_keywords`. Return shape unchanged.
  - Added `fetch_articles(ticker)` — returns scored article list for training UI
- `main.py` — 2 lines added:
  - Line 26: `from train import router as train_router`
  - Line 33: `app.include_router(train_router)`
- `.gitignore` — added `train_data/` on line 10

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/train` | Serve training UI |
| GET | `/train/api/articles/{ticker}` | Scored articles for a ticker |
| GET | `/train/api/keywords/{indicator}` | Base + override keywords |
| POST | `/train/api/keywords/{indicator}` | Save keyword overrides |
| POST | `/train/api/feedback` | Submit article feedback |
| GET | `/train/api/feedback` | Retrieve past feedback |

## How to Use

1. Navigate to `/train`
2. Enter a ticker and click Fetch
3. Review articles — each shows headline, summary, score, and matched keyword pills
4. Thumbs up = correct score, thumbs down = pick the correct score
5. Manage keywords in the section below — add/remove words, save changes
6. Re-fetch articles to see updated scoring

## How to Extend (add a new indicator tab)

1. In the indicator module (e.g., `reddit_buzz.py`), add a `fetch_articles(ticker)` function returning `[{"headline", "summary", "source", "url", "datetime", "score", "matched_keywords"}, ...]`
2. Create keyword overlay pattern: `train_data/{indicator}_keywords.json`
3. In `train.py`, register the indicator in the keywords and articles endpoint handlers
4. In `train.html`, add a new tab and wire it to the existing fetch/render logic

## How to Remove

1. Delete files: `train.py`, `train.html`, `TRAINING_FEATURE.md`
2. Delete directory: `train_data/`
3. In `main.py`, remove these 2 lines:
   ```python
   from train import router as train_router
   app.include_router(train_router)
   ```
4. In `.gitignore`, remove the `train_data/` entry
5. Optional — revert `sentiment.py` changes (safe to leave as-is, they gracefully no-op):
   - Remove `_TRAIN_DATA_DIR`, `_get_effective_keywords()`, `_fetch_raw_articles()`, `fetch_articles()`
   - Replace `_score_article()` with the original `_score_headline()` (headline-only, single set lookup)
   - Restore `fetch_sentiment()` to directly call the Finnhub API and score headlines inline (see git history for original)

**Note:** The `sentiment.py` changes are safe to keep permanently. The keyword overlay pattern has zero overhead when no override file exists, and headline+summary scoring is strictly better than headline-only.
