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
)

logger = logging.getLogger(__name__)


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


def build_end_detector_prompt(context_messages, user_message):
    payload = {
        "context": context_messages or [],
        "user_message": user_message,
    }
    system = (
        "あなたは会話終了を判定するアシスタントです。与えられた直近の会話と最新のユーザ発話を見て、"
        "ユーザが会話を終わらせようとしているか(別れの挨拶、切り上げ、会話を終了する意図)を判定し、"
        "JSONで返してください。返却例: {\"ending\": true, \"confidence\": 0.85, \"reason\": \"挨拶的表現\"}"
    )
    prompt = system + "\n\nInput JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
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
            json={"model": "elyza-mom", "prompt": prompt, "stream": False},
            timeout=END_DETECTOR_TIMEOUT_SEC,
        )
        r.raise_for_status()
        body = r.json().get("response", "").strip()
        parsed = _safe_parse_json(body)
        if not parsed:
            logger.debug("End detector parse failed; body: %s", body[:200])
            return {"ending": False, "confidence": 0.0}
        # normalize
        ending = bool(parsed.get("ending"))
        confidence = float(parsed.get("confidence", 0.0))
        reason = parsed.get("reason") or ""
        return {"ending": ending, "confidence": confidence, "reason": reason}
    except requests.exceptions.Timeout:
        logger.warning("End detector timed out")
        return {"ending": False, "confidence": 0.0}
    except Exception as e:
        logger.error(f"End detector error: {e}")
        return {"ending": False, "confidence": 0.0}
