import json
import logging
import requests
import re
from datetime import datetime
from pathlib import Path

from config.settings import (
    OLLAMA_URL,
    ENABLE_END_DETECTOR,
    END_DETECTOR_TIMEOUT_SEC,
    END_DETECTOR_CONFIDENCE,
    RECENT_HISTORY_FOR_CHECKER,
    END_DETECTOR_LOG_PATH,
    GENERATED_MODEL_NAME,
)

logger = logging.getLogger(__name__)

# End-detector log path
END_DETECTOR_LOG = Path(END_DETECTOR_LOG_PATH)
END_DETECTOR_LOG.parent.mkdir(parents=True, exist_ok=True)


def _write_end_log(event: dict):
    try:
        with END_DETECTOR_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.error(f"Failed to write end-detector log: {e}")


def _safe_parse_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None


# プロンプトは prompts/all_prompts.py で一元管理
from prompts.all_prompts import END_DETECTOR_SYSTEM_PROMPT


def build_end_detector_prompt(context_messages, user_message):
    payload = {
        "context": context_messages or [],
        "user_message": user_message,
    }
    prompt = END_DETECTOR_SYSTEM_PROMPT + "\n\nInput JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    return prompt


def detect_conversation_end(context_messages, user_message):
    """Call LLM to detect whether the user is trying to end the conversation.

    Returns dict: {"ending": bool, "confidence": float, "reason": str}
    On failure returns {"ending": False, "confidence": 0.0}
    """
    if not ENABLE_END_DETECTOR:
        return {"ending": False, "confidence": 0.0}

    prompt = build_end_detector_prompt(context_messages, user_message)
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": GENERATED_MODEL_NAME, "prompt": prompt, "stream": False},
            timeout=END_DETECTOR_TIMEOUT_SEC,
        )
        r.raise_for_status()
        body = r.json().get("response", "").strip()
        parsed = _safe_parse_json(body)
        event = {"timestamp": datetime.utcnow().isoformat() + "Z", "user_message": user_message[:1000], "raw": body[:2000]}
        if not parsed:
            logger.debug("End detector parse failed; body: %s", body[:200])
            event.update({"status": "parse_failed"})
            _write_end_log(event)
            return {"ending": False, "confidence": 0.0}
        # normalize
        ending = bool(parsed.get("ending"))
        confidence = float(parsed.get("confidence", 0.0))
        reason = parsed.get("reason") or ""
        event.update({"status": "ok", "result": {"ending": ending, "confidence": confidence, "reason": reason}})
        _write_end_log(event)
        return {"ending": ending, "confidence": confidence, "reason": reason}
    except requests.exceptions.Timeout:
        logger.warning("End detector timed out")
        event = {"timestamp": datetime.utcnow().isoformat() + "Z", "user_message": user_message[:1000], "status": "timeout"}
        _write_end_log(event)
        return {"ending": False, "confidence": 0.0}
    except Exception as e:
        logger.error(f"End detector error: {e}")
        event = {"timestamp": datetime.utcnow().isoformat() + "Z", "user_message": user_message[:1000], "status": "error", "error": str(e)}
        _write_end_log(event)
        return {"ending": False, "confidence": 0.0}
