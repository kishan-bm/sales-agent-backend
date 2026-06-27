import json
import os
import time
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent.parent / ".cache"
CACHE_TTL = 86400  # 24 hours


def _path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe}.json"


def get(key: str) -> dict | None:
    p = _path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if time.time() - data["_ts"] > CACHE_TTL:
            p.unlink(missing_ok=True)
            return None
        return data["value"]
    except Exception:
        return None


def set(key: str, value: dict):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(key).write_text(json.dumps({"_ts": time.time(), "value": value}))


def invalidate(key: str):
    _path(key).unlink(missing_ok=True)
