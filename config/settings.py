"""
Central settings loader.

This module loads `config/settings.json` for human-editable defaults and allows
environment variable overrides. Import values from here across the codebase so
that adjustable parameters are centralized.
"""
import json
import os
from pathlib import Path

CFG_PATH = Path("config/settings.json")

# sane defaults
_defaults = {
    "OLLAMA_URL": "http://127.0.0.1:11434/api/generate",
    "GENERATED_MODEL_NAME": "elyza-mom",
    "RECENT_HISTORY_FOR_LLM": 30,
    "MIN_SCHEDULE_CONFIDENCE": 0.7,
    "CLASSIFIER_CONFIDENCE_THRESHOLD": 0.8,
    "CLASSIFIER_MODEL_NAME": "elyza-mom",
    "CLASSIFIER_TIMEOUT": 10.0,
    "LOGS_DIR": "logs",
    "RECENT_HISTORY_FOR_CHECKER": 10,
}

# load file overrides if present
if CFG_PATH.exists():
    try:
        with CFG_PATH.open("r", encoding="utf-8") as f:
            file_cfg = json.load(f)
            _defaults.update(file_cfg)
    except Exception:
        # keep defaults on error
        pass

# helpers for env overrides
def _env_str(key, default):
    return os.getenv(key, default)

def _env_int(key, default):
    v = os.getenv(key)
    if v is None:
        return int(default)
    try:
        return int(v)
    except Exception:
        return int(default)

def _env_float(key, default):
    v = os.getenv(key)
    if v is None:
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)

# primary settings (env vars override JSON)
OLLAMA_URL = _env_str("OLLAMA_URL", _defaults.get("OLLAMA_URL"))
GENERATED_MODEL_NAME = _env_str("GENERATED_MODEL_NAME", _defaults.get("GENERATED_MODEL_NAME"))
RECENT_HISTORY_FOR_LLM = _env_int("RECENT_HISTORY_FOR_LLM", _defaults.get("RECENT_HISTORY_FOR_LLM"))
MIN_SCHEDULE_CONFIDENCE = _env_float("MIN_SCHEDULE_CONFIDENCE", _defaults.get("MIN_SCHEDULE_CONFIDENCE"))
CLASSIFIER_CONFIDENCE_THRESHOLD = _env_float("CLASSIFIER_CONFIDENCE_THRESHOLD", _defaults.get("CLASSIFIER_CONFIDENCE_THRESHOLD"))
CLASSIFIER_MODEL_NAME = _env_str("CLASSIFIER_MODEL_NAME", _defaults.get("CLASSIFIER_MODEL_NAME"))
CLASSIFIER_TIMEOUT = _env_float("CLASSIFIER_TIMEOUT", _defaults.get("CLASSIFIER_TIMEOUT"))

LOGS_DIR = Path(_env_str("LOGS_DIR", _defaults.get("LOGS_DIR")))
LOGS_DIR.mkdir(parents=True, exist_ok=True)

RECENT_HISTORY_FOR_CHECKER = _env_int("RECENT_HISTORY_FOR_CHECKER", _defaults.get("RECENT_HISTORY_FOR_CHECKER"))

# Integrate checker_settings (keeps existing checker JSON/overrides functioning)
try:
    from .checker_settings import (
        ENABLE_RESPONSE_CHECKER,
        CHECKER_MODEL,
        CHECKER_TIMEOUT_SEC,
        CHECKER_MAX_REGEN,
        CHECKER_LOG_PATH,
    )
except Exception:
    ENABLE_RESPONSE_CHECKER = True
    CHECKER_MODEL = GENERATED_MODEL_NAME
    CHECKER_TIMEOUT_SEC = 4
    CHECKER_MAX_REGEN = 1
    CHECKER_LOG_PATH = str(LOGS_DIR / "checker_events.log")

# Classifier log path
CLASSIFIER_LOG_PATH = LOGS_DIR / "classifier_events.log"

__all__ = [
    "OLLAMA_URL",
    "GENERATED_MODEL_NAME",
    "RECENT_HISTORY_FOR_LLM",
    "MIN_SCHEDULE_CONFIDENCE",
    "CLASSIFIER_CONFIDENCE_THRESHOLD",
    "CLASSIFIER_MODEL_NAME",
    "CLASSIFIER_TIMEOUT",
    "LOGS_DIR",
    "RECENT_HISTORY_FOR_CHECKER",
    "ENABLE_RESPONSE_CHECKER",
    "CHECKER_MODEL",
    "CHECKER_TIMEOUT_SEC",
    "CHECKER_MAX_REGEN",
    "CHECKER_LOG_PATH",
    "CLASSIFIER_LOG_PATH",
]
