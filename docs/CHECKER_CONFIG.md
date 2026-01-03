# Response Checker Configuration

This file documents the configuration for the response-checker PoC.

Location: `config/settings.json` (preferred single source of truth)

Editable fields (in `config/settings.json`) that affect the checker:

- `ENABLE_RESPONSE_CHECKER` (bool): Enable/disable the checker. Default: `true`.
- `CHECKER_MODEL` (string): Model name used by the checker. Default: `elyza-mom`.
- `CHECKER_TIMEOUT_SEC` (int): Timeout (seconds) for checker LLM calls. Default: `8`.
- `CHECKER_MAX_REGEN` (int): Maximum number of automatic re-generations allowed when checker requests regeneration. Default: `1`.
- `RECENT_HISTORY_FOR_CHECKER` (int): Number of recent messages passed to the checker for context. Default: `10`.
- `CHECKER_LOG_PATH` (string): Path to checker events log (JSONL format). Default: `logs/checker_events.log`.
- `OLLAMA_URL` (string): Ollama generate API URL.

Environment variables override the JSON config. Example env vars:

```
ENABLE_RESPONSE_CHECKER=false
CHECKER_TIMEOUT_SEC=3
CHECKER_MODEL=small-checker-model
```

Notes:
- `config/settings.json` is the single human-editable source for these values. The application also supports environment-variable overrides.
- After editing `config/settings.json`, restart the service to apply changes (env vars require setting before process start).
- For production, prefer a smaller/faster checker model and a conservative `CHECKER_TIMEOUT_SEC` to limit latency.
