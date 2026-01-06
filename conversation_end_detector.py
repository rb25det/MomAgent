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


def build_end_detector_prompt(context_messages, user_message):
    payload = {
        "context": context_messages or [],
        "user_message": user_message,
    }
    system = (
        "あなたは会話終了を判定するアシスタントです。与えられた直近の会話と最新のユーザ発話を見て、"
        "ユーザが会話を本当に終わらせようとしているかを判定し、JSONで返してください。\n\n"
        "【重要な判定ルール】\n"
        "1. ネガティブな内容（失敗、不採用、悩み）≠ 会話終了。むしろ相談欲求の可能性が高い。\n"
        "2. 会話終了の明確な合図：さようなら、またね、今日はここまで、じゃあね、なども別れ表現。\n"
        "3. 会話継続の合図：質問形式、新しい話題の提示、悩みの報告、相談欲求、今後について語る。\n"
        "4. ただし、長い説明の後に『以上』『それでいいです』など話の区切りがあり、その後新しい質問や話題がなければ終了の可能性。\n"
        "5. 文脈から疲労や心理的終わり（解決した、スッキリした等）が見られ、かつ続ける意欲が見られなければ終了と判定可。\n\n"
        "返却フォーマット: {\"ending\": true/false, \"confidence\": 0.0-1.0, \"reason\": \"判定根拠\"}\n"
        "例1 (終了): {\"ending\": true, \"confidence\": 0.95, \"reason\": \"『またね』という別れ表現\"}\n"
        "例2 (継続): {\"ending\": false, \"confidence\": 0.9, \"reason\": \"不採用の報告だが相談欲求が見られる\"}"
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
