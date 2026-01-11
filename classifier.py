"""
分類器モジュール：ユーザ発話から予定問い合わせ意図を判定する。

このモジュールは以下の機能を提供：
- ルールベース判定（正規表現）
- LLMベース判定（Ollama）
- ハイブリッド判定（両者を組み合わせ）
- ロギング・分析
"""

import json
import re
import logging
import requests
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, date, timedelta
from pathlib import Path

# ロギング設定
logger = logging.getLogger(__name__)

from config.settings import (
    OLLAMA_URL,
    CLASSIFIER_MODEL_NAME,
    CLASSIFIER_TIMEOUT,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    LOGS_DIR,
)

# プロンプトは prompts/all_prompts.py で一元管理
from prompts.all_prompts import CLASSIFIER_SYSTEM_PROMPT

CLASSIFIER_LOG_PATH = LOGS_DIR / "classifier_events.log"


# =========================
# ルールベース判定（軽量フィルタ）
# =========================

def _quick_filter(text: str) -> Tuple[Optional[bool], float]:
    """
    正規表現で明らかに予定問い合わせ/非問い合わせを判定（高速）。
    
    Args:
        text (str): ユーザ発話
    
    Returns:
        tuple: (is_schedule_likely, base_confidence)
            - is_schedule_likely: True/False/None（グレーゾーン）
            - base_confidence: 0.0 ~ 1.0
    """
    text = (text or "").strip()
    if not text:
        return False, 0.0
    
    text_lower = text.lower()
    
    # 強い肯定シグナル: 予定キー + 動詞
    strong_positive_pattern = (
        r"(予定|スケジュール|schedule)" + 
        r"(?:を|は)?" + 
        r"(教え|見せ|確認|知り|一覧|見たい|して|ある)"
    )
    if re.search(strong_positive_pattern, text):
        logger.debug(f"Quick filter: Strong positive detected for '{text}'")
        return True, 0.95
    
    # 時間キー + 疑問符（あるいは疑問表現）→ 肯定シグナル
    time_key_pattern = r"(今日|明日|今週|来週|今月|次|直近|これから)"
    question_mark = r"[?？]"
    has_time_key = re.search(time_key_pattern, text)
    has_question = re.search(question_mark, text)

    # 質問を示す日本語表現（疑問符が無くてもよく使われる語）
    jp_question_words = re.search(r"(か$|かな$|かしら$|だっけ$|あったっけ|教えて|なにあったっけ|あるっけ|なにあった)", text)

    if has_time_key and (has_question or jp_question_words):
        logger.debug(f"Quick filter: Time key + question detected for '{text}'")
        return True, 0.95
    
    # 明らかな否定（説明・感想）
    negative_pattern = r"予定が(立て込ん|詰ま|いっぱい|忙し|ある)"
    if re.search(negative_pattern, text):
        logger.debug(f"Quick filter: Clear negative detected for '{text}'")
        return False, 0.95
    
    # 予定立案要望
    if re.search(r"予定を(立て|作|組|組み立て)", text):
        logger.debug(f"Quick filter: Schedule creation request detected for '{text}'")
        return False, 0.90
    
    # グレーゾーン: 時間キーはあるが疑問表現がない、または単に「予定」のみ
    if has_time_key or re.search(r"(予定|schedule)", text):
        logger.debug(f"Quick filter: Gray zone detected for '{text}'")
        return None, 0.50
    
    # 明らかに予定無関連
    logger.debug(f"Quick filter: Not schedule related for '{text}'")
    return False, 0.20


# =========================
# LLM分類関数
# =========================

def _classify_with_llm(text: str, base_confidence: float) -> Dict[str, Any]:
    """
    LLMを用いて詳細な意図分類を実行。
    
    Args:
        text (str): ユーザ発話
        base_confidence (float): 正規表現判定の基礎信頼度
    
    Returns:
        dict: 分類結果（以下を含む）
            - intent: "schedule_query" | "not_schedule"
            - scope: スコープ文字列
            - confidence: 0.0 ~ 1.0 の最終信頼度
            - reasoning: 判定根拠
            - error: エラーメッセージ（エラーがあれば）
    """
    user_prompt = f"""以下のユーザ発話を分類してください。JSON形式で返してください。

発話: "{text}"

返却フォーマット:
{{
    "intent": "schedule_query" | "not_schedule",
    "scope": "today" | "tomorrow" | "week" | "month" | "next" | "upcoming" | "unspecified",
    "confidence_base": 0.0 ~ 1.0,
    "reasoning": "判定根拠"
}}
"""
    
    try:
        logger.debug(f"LLM classification request for: '{text}'")
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": CLASSIFIER_MODEL_NAME,
                "prompt": CLASSIFIER_SYSTEM_PROMPT + user_prompt,
                "stream": False
            },
            timeout=CLASSIFIER_TIMEOUT
        )
        response.raise_for_status()
        
        # レスポンス解析
        result_text = response.json().get("response", "").strip()
        logger.debug(f"LLM response: {result_text[:200]}")
        
        # JSON抽出（複数行の場合がある）
        try:
            judgment = json.loads(result_text)
        except json.JSONDecodeError:
            # 正規表現でJSON部分を抽出
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                judgment = json.loads(json_match.group())
            else:
                raise json.JSONDecodeError("No JSON found in response", result_text, 0)
        
        # 信頼度調整
        llm_confidence = judgment.get("confidence_base", 0.5)
        final_confidence = _adjust_confidence(base_confidence, llm_confidence, text)
        
        judgment["confidence"] = final_confidence
        judgment["error"] = None
        
        logger.info(
            f"Classification result: intent={judgment['intent']}, "
            f"scope={judgment.get('scope')}, confidence={final_confidence:.2f}"
        )
        return judgment
        
    except requests.Timeout:
        logger.error(f"LLM classifier timeout for: '{text}'")
        return {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "reasoning": "分類器タイムアウト",
            "error": "TimeoutError"
        }
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in LLM response: {e}")
        return {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "reasoning": "分類器応答解析失敗",
            "error": "JSONDecodeError"
        }
    except requests.RequestException as e:
        logger.error(f"LLM request error: {e}")
        return {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "reasoning": "分類器通信エラー",
            "error": str(type(e).__name__)
        }


def _adjust_confidence(
    quick_conf: float,
    llm_conf: float,
    text: str
) -> float:
    """
    正規表現とLLMの信頼度を統合。
    
    Args:
        quick_conf (float): 正規表現による基礎信頼度
        llm_conf (float): LLMによる信頼度
        text (str): 入力テキスト（オプション）
    
    Returns:
        float: 統合信頼度
    """
    if quick_conf is None or quick_conf < 0.5:
        # グレーゾーン → LLMの判定を信頼
        return llm_conf
    if quick_conf > 0.9:
        # 既に確信度高い → LLMで微調整
        return 0.95 * quick_conf + 0.05 * llm_conf
    # グレーゾーン（0.5～0.9）
    return 0.6 * llm_conf + 0.4 * quick_conf


# =========================
# メイン分類関数
# =========================

def classify_schedule_intent(
    text: str,
    session_meta: Optional[Dict[str, Any]] = None,
    use_llm: bool = True
) -> Dict[str, Any]:
    """
    ユーザ発話から予定問い合わせ意図を分類する。
    
    Args:
        text (str): ユーザ発話テキスト（日本語）
        session_meta (dict | None): セッション情報（予定有無など）
        use_llm (bool): LLM分類器を使用するか。Falseなら正規表現のみ
    
    Returns:
        dict: {
            "intent": "schedule_query" | "not_schedule",
            "scope": "today" | "tomorrow" | "week" | "month" | "next" | "upcoming" | "unspecified",
            "start_date": "YYYY-MM-DD" | None,
            "end_date": "YYYY-MM-DD" | None,
            "confidence": 0.0 ~ 1.0,
            "reasoning": str,
            "error": str | None
        }
    """
    text = (text or "").strip()
    
    if not text:
        return {
            "intent": "not_schedule",
            "scope": "unspecified",
            "start_date": None,
            "end_date": None,
            "confidence": 0.0,
            "reasoning": "空の入力",
            "error": None
        }
    
    logger.info(f"Classifying: '{text}'")
    
    # Step 1: 軽量フィルタ
    is_likely, base_conf = _quick_filter(text)
    
    # Step 2: LLMが必要か判定
    if use_llm and (is_likely is None or (0.5 < base_conf < 0.9)):
        # グレーゾーン → LLM分類器へ
        judgment = _classify_with_llm(text, base_conf)
    elif is_likely is True:
        # 既に確信 → スコープを推定して簡易応答
        scope = _infer_scope_from_text(text)
        judgment = {
            "intent": "schedule_query",
            "scope": scope,
            "confidence": base_conf,
            "reasoning": "正規表現で強い肯定シグナル検出",
            "error": None
        }
    else:
        # 非予定問い合わせ
        judgment = {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": base_conf if base_conf else 0.5,
            "reasoning": "スケジュール問い合わせではない",
            "error": None
        }
    
    # 日付範囲の計算（スコープから）
    date_range = compute_date_range(judgment.get("scope"))
    judgment["start_date"] = date_range[0].isoformat() if date_range else None
    judgment["end_date"] = date_range[1].isoformat() if date_range else None
    
    return judgment


def _infer_scope_from_text(text: str) -> str:
    """
    ユーザ発話からスコープを推定（ルールベース）。
    
    Args:
        text (str): ユーザ発話
    
    Returns:
        str: "today", "tomorrow", "week", "month", "next", "upcoming", "unspecified"
    """
    text_lower = text.lower()
    
    if "今日" in text:
        return "today"
    elif "明日" in text:
        return "tomorrow"
    elif "今週" in text or "この週" in text:
        return "week"
    elif "来週" in text or "来週" in text:
        return "week"
    elif "今月" in text or "この月" in text:
        return "month"
    elif "来月" in text:
        return "month"
    elif any(w in text for w in ("次", "直近")):
        return "next"
    elif "これから" in text or "upcoming" in text_lower:
        return "upcoming"
    else:
        return "unspecified"


# =========================
# 日付範囲計算
# =========================

def compute_date_range(
    scope: str,
    reference_date: Optional[date] = None
) -> Optional[Tuple[date, date]]:
    """
    スコープ文字列をローカルな日付範囲に変換。
    
    Args:
        scope (str): "today", "tomorrow", "week", "month", "next", "upcoming", "unspecified"
        reference_date (date | None): 基準日。Noneの場合は本日
    
    Returns:
        tuple[date, date] | None:
            - (start_date, end_date) for range-based scopes
            - None for non-range scopes ("next", "upcoming", "unspecified")
    """
    if reference_date is None:
        reference_date = date.today()
    
    if scope == "today":
        return (reference_date, reference_date)
    
    elif scope == "tomorrow":
        tomorrow = reference_date + timedelta(days=1)
        return (tomorrow, tomorrow)
    
    elif scope == "week":
        # 月曜始まり（日本仕様）
        monday = reference_date - timedelta(days=reference_date.weekday())
        sunday = monday + timedelta(days=6)
        return (monday, sunday)
    
    elif scope == "month":
        # 当月1日～末日
        first_day = reference_date.replace(day=1)
        if reference_date.month == 12:
            last_day = first_day.replace(year=first_day.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = first_day.replace(month=first_day.month + 1, day=1) - timedelta(days=1)
        return (first_day, last_day)
    
    elif scope in ("next", "upcoming", "unspecified"):
        return None
    
    else:
        logger.warning(f"Unknown scope: {scope}")
        return None


# =========================
# ロギング・分析
# =========================

def log_event(
    user_message: str,
    judgment: Dict[str, Any],
    chosen_path: str,
    reply_text: str,
    processing_time_ms: float,
    error: Optional[str] = None
) -> None:
    """
    分類イベントをJSON Lines形式でログに記録。
    
    Args:
        user_message (str): ユーザの発話
        judgment (dict): 分類器の判定結果
        chosen_path (str): 選択された処理路（"rule-based" or "llm"）
        reply_text (str): システムの返信
        processing_time_ms (float): 処理時間（ミリ秒）
        error (str | None): エラーが発生した場合の説明
    """
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "schedule_classification",
        "user_message": user_message,
        "classifier_intent": judgment.get("intent"),
        "classifier_scope": judgment.get("scope"),
        "classifier_confidence": judgment.get("confidence"),
        "classifier_reasoning": judgment.get("reasoning"),
        "chosen_path": chosen_path,
        "reply_text": reply_text,
        "processing_time_ms": processing_time_ms,
        "error": error
    }
    
    try:
        with open(CLASSIFIER_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        logger.debug("Event logged successfully")
    except Exception as e:
        logger.error(f"Failed to log event: {e}")


def analyze_classifier_log(log_file_path: Path = CLASSIFIER_LOG_PATH) -> Dict[str, Any]:
    """
    ロギング結果を集計し、精度・エラー率を計算。
    
    Args:
        log_file_path (Path): ロググフォイルパス
    
    Returns:
        dict: {
            "total_events": int,
            "schedule_query_count": int,
            "not_schedule_count": int,
            "avg_confidence_schedule": float,
            "avg_confidence_not": float,
            "rule_based_count": int,
            "llm_count": int,
            "error_count": int,
        }
    """
    if not log_file_path.exists():
        logger.warning(f"Log file not found: {log_file_path}")
        return {
            "total_events": 0,
            "schedule_query_count": 0,
            "not_schedule_count": 0,
            "avg_confidence_schedule": 0.0,
            "avg_confidence_not": 0.0,
            "rule_based_count": 0,
            "llm_count": 0,
            "error_count": 0,
        }
    
    total = 0
    schedule_count = 0
    not_schedule_count = 0
    rule_count = 0
    llm_count = 0
    error_count = 0
    
    schedule_confidences = []
    not_schedule_confidences = []
    
    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                    total += 1
                    
                    intent = event.get("classifier_intent")
                    conf = event.get("classifier_confidence", 0.0)
                    path = event.get("chosen_path")
                    
                    if intent == "schedule_query":
                        schedule_count += 1
                        schedule_confidences.append(conf)
                    else:
                        not_schedule_count += 1
                        not_schedule_confidences.append(conf)
                    
                    if path == "rule-based":
                        rule_count += 1
                    elif path == "llm":
                        llm_count += 1
                    
                    if event.get("error"):
                        error_count += 1
                except json.JSONDecodeError:
                    logger.warning(f"Skipping malformed JSON line: {line[:100]}")
                    continue
    except Exception as e:
        logger.error(f"Error analyzing log file: {e}")
    
    avg_conf_schedule = (
        sum(schedule_confidences) / len(schedule_confidences)
        if schedule_confidences else 0.0
    )
    avg_conf_not = (
        sum(not_schedule_confidences) / len(not_schedule_confidences)
        if not_schedule_confidences else 0.0
    )
    
    return {
        "total_events": total,
        "schedule_query_count": schedule_count,
        "not_schedule_count": not_schedule_count,
        "avg_confidence_schedule": avg_conf_schedule,
        "avg_confidence_not": avg_conf_not,
        "rule_based_count": rule_count,
        "llm_count": llm_count,
        "error_count": error_count,
    }
