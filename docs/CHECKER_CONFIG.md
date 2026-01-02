# Response Checker Configuration

This file documents the configuration for the response-checker PoC.

Location: `config/response_checker_config.json`

Editable fields (edit the JSON file directly):

- `ENABLE_RESPONSE_CHECKER` (bool): Enable/disable the checker. Default `true`.
- `CHECKER_MODEL` (string): Model name used by the checker. Use a lightweight/faster model in production if available.
- `CHECKER_TIMEOUT_SEC` (int): Timeout (seconds) for checker LLM calls. Keep small (2-5s) to avoid latency.
- `CHECKER_MAX_REGEN` (int): Maximum number of automatic re-generations allowed when checker requests regeneration.
- `RECENT_HISTORY_FOR_CHECKER` (int): Number of recent messages passed to the checker for context.
- `CHECKER_LOG_PATH` (string): Path to checker events log (JSONL format).
- `OLLAMA_URL` (string): Ollama generate API URL.

Environment variables override the JSON config. Example env vars:

```
ENABLE_RESPONSE_CHECKER=false
CHECKER_TIMEOUT_SEC=3
CHECKER_MODEL=small-checker-model
```

Notes:
- The JSON file is intended to be human-editable. After edits, no restart is required for exports, but to apply env var changes set them in the shell/service and restart the process.
- For production, prefer a small dedicated checker model to reduce latency and cost.
