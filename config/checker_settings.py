"""
Compatibility shim: expose checker settings by importing the centralized
`config.settings`. This keeps any old imports working while `config/settings.json`
is the single source of truth.
"""
from .settings import (
    ENABLE_RESPONSE_CHECKER,
    CHECKER_MODEL,
    CHECKER_TIMEOUT_SEC,
    CHECKER_MAX_REGEN,
    RECENT_HISTORY_FOR_CHECKER,
    CHECKER_LOG_PATH,
    OLLAMA_URL,
)

__all__ = [
    "ENABLE_RESPONSE_CHECKER",
    "CHECKER_MODEL",
    "CHECKER_TIMEOUT_SEC",
    "CHECKER_MAX_REGEN",
    "RECENT_HISTORY_FOR_CHECKER",
    "CHECKER_LOG_PATH",
    "OLLAMA_URL",
]
