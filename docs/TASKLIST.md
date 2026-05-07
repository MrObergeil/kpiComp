# Tasklist

Running list of planned work and follow-ups. Move items to CHANGELOG.md once done.

## Open

### Setup / Environment
- [ ] **Real `FINNHUB_API_KEY`** — currently a placeholder in `.env`. Without it, three modules silently degrade:
  - `analyst_ratings.py` — analyst recommendation trends
  - `insider_trading.py` — insider buy/sell signals
  - `sentiment.py` — Finnhub news source (other sources still work)
- [ ] **Starlette version pin conflict** — `pip install` flagged `sse-starlette 3.4.1 requires starlette>=0.49.1` but `fastapi==0.115.6` pins `starlette<0.42`. Either remove `sse-starlette` if unused, or upgrade FastAPI. Check `grep -rn sse_starlette` first.
- [ ] **Pin `python-dotenv` in `requirements.txt`** — used by `main.py` (`from dotenv import load_dotenv`) but not in requirements.

### Known gaps / observations
- [ ] No automated tests anywhere in the repo — consider a minimal pytest smoke suite for the API endpoints.
- [ ] No `Dockerfile` / no process manager — currently launched manually with uvicorn.

## Ideas / Backlog
- **Reverse proxy (Caddy)** — once 3+ services run on `homelab`, drop a Caddy in front so everything lives on port 80/443 with path/subdomain routing (e.g. `homelab.local/kpicomp` instead of `:8000`). Caddy auto-handles HTTPS via internal CA for `.local` too.
- **Static DHCP lease** — user-side step, reserve `192.168.178.21` in the Fritz!Box admin UI as belt-and-suspenders for when mDNS misbehaves.

## Done
- **2026-05-07 — Basic auth + stable hostname + LAN access docs**
  - HTTP Basic middleware in `main.py` (`APP_USERNAME` / `APP_PASSWORD` env vars, `secrets.compare_digest`, logs failed attempts)
  - `.env` populated with random password; `.env.example` updated with placeholders
  - Hostname changed to `homelab` → `homelab.local` resolves via mDNS from Linux/macOS/Windows/mobile
  - `docs/README.md` got `Authentication` and `LAN Access` sections
