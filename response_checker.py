import json
import logging
import re
from pathlib import Path
import requests
from datetime import datetime

from config.settings import (
    CHECKER_MODEL,
    CHECKER_TIMEOUT_SEC,
    RECENT_HISTORY_FOR_CHECKER,
    CHECKER_LOG_PATH,
    OLLAMA_URL,
)

# ログパスは設定ファイルに従う
CHECKER_LOG = Path(CHECKER_LOG_PATH)
CHECKER_LOG.parent.mkdir(parents=True, exist_ok=True)


def _write_checker_log(event: dict):
    try:
        with CHECKER_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error(f"Failed to write checker log: {e}")


def _safe_parse_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        # try to extract {...} substring
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


# プロンプトは prompts/all_prompts.py で一元管理
from prompts.all_prompts import RESPONSE_CHECKER_SYSTEM_PROMPT, RESPONSE_CHECKER_RULES


def build_checker_prompt(context_messages, user_profile, user_message, candidate_reply, rules=None):
    rules = rules or RESPONSE_CHECKER_RULES

    payload = {
        "context": context_messages,
        "user_profile": user_profile or {},
        "user_message": user_message,
        "candidate_reply": candidate_reply,
        "rules": rules,
    }

    prompt = RESPONSE_CHECKER_SYSTEM_PROMPT + "\n\nInput JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    return prompt


def check_response(context_messages, user_profile, user_message, candidate_reply):
    """チェッカーに投げて判定結果を返す。失敗時は accept を返すフェールオーバーを行う。"""
    ts = datetime.now().isoformat()
    prompt = build_checker_prompt(context_messages, user_profile, user_message, candidate_reply)
    event = {
        "timestamp": ts,
        "user_message": user_message[:1000],
        "candidate_reply": candidate_reply[:2000],
        "checker_prompt_len": len(prompt),
    }

    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": CHECKER_MODEL, "prompt": prompt, "stream": False},
            timeout=CHECKER_TIMEOUT_SEC,
        )
        r.raise_for_status()
        body = r.json().get("response", "").strip()
        parsed = _safe_parse_json(body)
        if not parsed:
            # If checker returns non-json, be conservative: accept
            event.update({"status": "parse_failed", "raw": body[:2000]})
            event.update({"result": {"verdict": "accept", "confidence": 0.5}})
            _write_checker_log(event)
            return {"verdict": "accept", "confidence": 0.5}

        event.update({"status": "ok", "raw": body[:2000], "result": parsed})
        _write_checker_log(event)
        return parsed

    except requests.exceptions.Timeout:
        logging.warning("Checker timed out")
        event.update({"status": "timeout"})
        _write_checker_log(event)
        return {"verdict": "accept", "confidence": 0.2}
    except Exception as e:
        logging.error(f"Checker error: {e}")
        event.update({"status": "error", "error": str(e)})
        _write_checker_log(event)
        return {"verdict": "accept", "confidence": 0.1}
