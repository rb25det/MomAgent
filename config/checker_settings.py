"""
Checker settings loader.

This module loads `config/response_checker_config.json` and allows
overrides via environment variables. Edit the JSON file for human-editable
defaults; env vars (e.g. CHECKER_TIMEOUT_SEC) take precedence.

Fields available:
- ENABLE_RESPONSE_CHECKER: bool
- CHECKER_MODEL: string
- CHECKER_TIMEOUT_SEC: int
- CHECKER_MAX_REGEN: int
- RECENT_HISTORY_FOR_CHECKER: int
- CHECKER_LOG_PATH: path string
- OLLAMA_URL: string

Modify the JSON file to change defaults; use env vars for per-machine overrides.
"""
import json
import os
from pathlib import Path

CFG_PATH = Path("config/response_checker_config.json")

# defaults
_cfg = {
    "ENABLE_RESPONSE_CHECKER": True,
    "CHECKER_MODEL": "elyza-mom",
    "CHECKER_TIMEOUT_SEC": 4,
    "CHECKER_MAX_REGEN": 1,
    "RECENT_HISTORY_FOR_CHECKER": 10,
    "CHECKER_LOG_PATH": "logs/checker_events.log",
    "OLLAMA_URL": "http://127.0.0.1:11434/api/generate",
}

if CFG_PATH.exists():
    try:
        with CFG_PATH.open("r", encoding="utf-8") as f:
            file_cfg = json.load(f)
            _cfg.update(file_cfg)
    except Exception:
        # keep defaults on error
        pass

# allow env var overrides
def _env_bool(key, default):
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes")

def _env_int(key, default):
    v = os.getenv(key)
    if v is None:
        return default
    try:
        return int(v)
    except Exception:
        return default

ENABLE_RESPONSE_CHECKER = _env_bool("ENABLE_RESPONSE_CHECKER", _cfg.get("ENABLE_RESPONSE_CHECKER", True))
CHECKER_MODEL = os.getenv("CHECKER_MODEL", _cfg.get("CHECKER_MODEL"))
CHECKER_TIMEOUT_SEC = _env_int("CHECKER_TIMEOUT_SEC", _cfg.get("CHECKER_TIMEOUT_SEC", 4))
CHECKER_MAX_REGEN = _env_int("CHECKER_MAX_REGEN", _cfg.get("CHECKER_MAX_REGEN", 1))
RECENT_HISTORY_FOR_CHECKER = _env_int("RECENT_HISTORY_FOR_CHECKER", _cfg.get("RECENT_HISTORY_FOR_CHECKER", 10))
CHECKER_LOG_PATH = os.getenv("CHECKER_LOG_PATH", _cfg.get("CHECKER_LOG_PATH"))
OLLAMA_URL = os.getenv("OLLAMA_URL", _cfg.get("OLLAMA_URL"))

__all__ = [
    "ENABLE_RESPONSE_CHECKER",
    "CHECKER_MODEL",
    "CHECKER_TIMEOUT_SEC",
    "CHECKER_MAX_REGEN",
    "RECENT_HISTORY_FOR_CHECKER",
    "CHECKER_LOG_PATH",
    "OLLAMA_URL",
]
