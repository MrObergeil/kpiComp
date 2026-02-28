"""
Custom peer group persistence.

Stores user-defined peer sets per ticker in peer_groups/custom_peers.json.
Thread-safe via threading.Lock.
"""

import json
import threading
from pathlib import Path

_STORAGE_DIR = Path(__file__).parent / "peer_groups"
_STORAGE_PATH = _STORAGE_DIR / "custom_peers.json"
_lock = threading.Lock()


def _load() -> dict[str, list[str]]:
    if not _STORAGE_PATH.exists():
        return {}
    try:
        return json.loads(_STORAGE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict[str, list[str]]) -> None:
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    _STORAGE_PATH.write_text(json.dumps(data, indent=2))


def get_custom_peers(ticker: str) -> list[str] | None:
    """Get custom peer list for a ticker. Returns None if not set."""
    with _lock:
        data = _load()
    return data.get(ticker.upper().strip())


def set_custom_peers(ticker: str, peers: list[str]) -> None:
    """Save custom peer list for a ticker."""
    with _lock:
        data = _load()
        data[ticker.upper().strip()] = [p.upper().strip() for p in peers]
        _save(data)


def delete_custom_peers(ticker: str) -> bool:
    """Remove custom peer override. Returns True if existed."""
    with _lock:
        data = _load()
        key = ticker.upper().strip()
        if key in data:
            del data[key]
            _save(data)
            return True
        return False


def list_custom_peer_tickers() -> list[str]:
    """List all tickers with custom peer sets."""
    with _lock:
        data = _load()
    return list(data.keys())
