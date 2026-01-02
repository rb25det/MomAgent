# 詳細設計書：お母さんAI 予定応答機能（判定器導入版）

## 1. アーキテクチャ概略

```
┌────────────────────────────────────────────────────────────────┐
│                      Web Frontend (chat.html)                  │
│                  /api/chat (user_message)                      │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│                     Flask Backend (app.py)                      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  api_chat()                                              │  │
│  │  ├─ normalize(user_message)                              │  │
│  │  ├─ classify_schedule_intent(text) ← 【NEW】            │  │
│  │  ├─ Route Decision                                       │  │
│  │  │  ├─ IF intent==schedule_query && conf>=threshold     │  │
│  │  │  │  └─ handle_schedule_query(msg, judgment)          │  │
│  │  │  │     ├─ compute_date_range(scope)                 │  │
│  │  │  │     ├─ filter_schedules(date_range)               │  │
│  │  │  │     └─ format_and_return(items)                   │  │
│  │  │  └─ ELSE                                              │  │
│  │  │     └─ ask(user_message, safety_instruction)         │  │
│  │  ├─ log_event(...) ← 【NEW】                             │  │
│  │  └─ update_session(chat_history)                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  classify_schedule_intent(text) ← 【NEW Module】         │  │
│  │  ├─ Prepare prompt                                       │  │
│  │  ├─ Call LLM (Ollama)                                    │  │
│  │  ├─ Parse JSON response                                  │  │
│  │  └─ Return judgment dict                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  handle_schedule_query(msg, judgment) ← 【ENHANCED】     │  │
│  │  ├─ scope = judgment["scope"]                            │  │
│  │  ├─ compute_date_range(scope) ← 【NEW】                │  │
│  │  ├─ filter_schedules(date_range)                         │  │
│  │  └─ format_reply()                                       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  log_event(timestamp, text, judgment, reply) ← 【NEW】  │  │
│  │  └─ Write JSON line to logs/classifier_events.log        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [session]                                                       │
│  ├─ profile, mom_settings, schedules                           │
│  └─ chat_history                                               │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│              External Services (Ollama)                          │
│  ├─ classify_schedule_intent API call ← 【NEW】               │
│  └─ ask() API call (existing)                                  │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. 判定器（分類器）の詳細仕様

### 2.1 関数シグネチャ

```python
def classify_schedule_intent(
    text: str,
    session_meta: dict | None = None,
    use_llm: bool = True
) -> dict:
    """
    ユーザ発話から予定問い合わせ意図を分類する。
    
    Args:
        text (str): ユーザ発話テキスト（日本語）
        session_meta (dict | None): セッション情報（有無判定等）
        use_llm (bool): LLM分類器を使用するか。Falseの場合は正規表現等の軽量判定
    
    Returns:
        dict: {
            "intent": "schedule_query" | "not_schedule",
            "scope": "today" | "tomorrow" | "week" | "month" | "next" | "upcoming" | "unspecified",
            "start_date": "YYYY-MM-DD" | None,
            "end_date": "YYYY-MM-DD" | None,
            "confidence": 0.0 ~ 1.0,
            "reasoning": str,
            "error": str | None  # エラーが発生した場合
        }
    
    Raises:
        TimeoutError: LLM呼び出しタイムアウト
    """
    pass
```

### 2.2 実装戦略（ハイブリッドアプローチ）

#### Step 1: 軽量フィルタ（正規表現）

```python
def _quick_filter(text: str) -> tuple[bool, float]:
    """
    正規表現で明らかに予定問い合わせ/非問い合わせを判定（高速）。
    
    Returns:
        (is_schedule_likely, base_confidence)
    """
    text_lower = text.lower()
    
    # 明らかな肯定シグナル → High confidence
    strong_positive = (
        r"(予定|スケジュール|schedule)" + r"(を?|は?)" + r"(教え|見せ|確認|知り|一覧|見たい)"
    )
    if re.search(strong_positive, text):
        return True, 0.95
    
    # 時間キー + 疑問符
    time_key_pattern = r"(今日|明日|今週|来週|今月|次|直近|これから)"
    question_mark = r"[?？]"
    if re.search(time_key_pattern, text) and re.search(question_mark, text):
        return True, 0.85
    
    # 明らかな否定（説明）
    negative_pattern = r"予定が(立て込ん|詰ま|いっぱい|忙し)"
    if re.search(negative_pattern, text):
        return False, 0.95
    
    # グレーゾーン → LLMへ
    return None, 0.50
```

#### Step 2: LLM分類（LLM分類器）

明らかでない場合、LLMの分類器タスク用プロンプトを使用。

```python
def _classify_with_llm(text: str, base_confidence: float) -> dict:
    """
    LLMを用いて詳細な意図分類を実行。
    
    Returns:
        dict: 分類結果
    """
    # プロンプト（下記 2.3 参照）
    system_prompt = CLASSIFIER_SYSTEM_PROMPT
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
        # Ollama呼び出し（タイムアウト: 3秒）
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": CLASSIFIER_MODEL_NAME,  # 別途設定（主モデルでもOK）
                "prompt": system_prompt + user_prompt,
                "stream": False
            },
            timeout=3.0
        )
        response.raise_for_status()
        
        # JSON抽出
        result_text = response.json().get("response", "").strip()
        judgment = json.loads(result_text)  # または正規表現で抽出
        
        # Confidence計算
        llm_confidence = judgment.get("confidence_base", 0.5)
        final_confidence = adjust_confidence(
            base_confidence,
            llm_confidence,
            text
        )
        
        judgment["confidence"] = final_confidence
        judgment["error"] = None
        return judgment
        
    except (requests.Timeout, json.JSONDecodeError, requests.RequestException) as e:
        print(f"LLM classifier error: {e}")
        return {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "reasoning": f"LLM分類器エラー: {type(e).__name__}",
            "error": str(e)
        }
```

#### Step 3: 信頼度調整

```python
def adjust_confidence(
    quick_conf: float,
    llm_conf: float,
    text: str
) -> float:
    """
    正規表現とLLMの信頼度を統合。
    
    - quick_conf > 0.9: 既に確信度高い → LLMの結果で若干調整
    - quick_conf is None or < 0.6: LLM結果を信頼
    - その他: 重み付き平均
    """
    if quick_conf is None or quick_conf < 0.5:
        return llm_conf
    if quick_conf > 0.9:
        # 既に確信あり。LLM結果で少し微調整
        return 0.95 * quick_conf + 0.05 * llm_conf
    # グレーゾーン
    return 0.6 * llm_conf + 0.4 * quick_conf
```

### 2.3 分類器用LLMプロンプト（システムプロンプト）

```
システムロール:
あなたは、ユーザの発話が「スケジュール・予定に関する問い合わせ」であるか否かを、
高精度で分類する専門の分類器です。以下の指示に従い、JSON形式で判定結果を返してください。

指示:
1. ユーザ発話を受け取ります。
2. 以下の観点から判定してください：
   - その発話は「スケジュール・予定」に関する質問（問い合わせ）であるか？
   - もしそうなら、どの時間範囲（スコープ）について聞かれているか？
3. 判定根拠を簡潔に述べてください。

判定の詳細:

【intent】
- "schedule_query": ユーザが現在のスケジュール・予定について「教えて」「確認」「見たい」等、
  事実確認を求めている。
- "not_schedule": スケジュール問い合わせではない。感想、雑談、予定立案要望、その他の依頼。

【scope】（schedule_query の場合のみ有効）
- "today": 当日の予定
- "tomorrow": 翌日の予定
- "week": 今週の予定（月～日）
- "month": 今月の予定
- "next": 次の1件（最も近い予定1つ）
- "upcoming": 直近複数件（3件程度）
- "unspecified": スコープが不明確（「予定ってある？」等）

【confidence_base】（LLMの確信度）
- 0.9以上: 明確な予定問い合わせと判定
- 0.7～0.9: 可能性が高いが、若干の曖昧さ
- 0.5～0.7: グレーゾーン
- 0.5未満: not_schedule の可能性が高い

ネガティブシグナル（not_schedule の例）:
- 「予定が立て込んでる」→ 説明・感想であり、事実確認ではない
- 「予定を立てたい」→ 予定の追加/作成要望。確認ではない
- 「予定を変更したい」→ 編集要望。確認ではない
- 文脈上、予定に無関係な発話

出力フォーマット（JSON）:
{
    "intent": "schedule_query" | "not_schedule",
    "scope": "today" | "tomorrow" | "week" | "month" | "next" | "upcoming" | "unspecified",
    "confidence_base": 0.0 ~ 1.0 の浮動小数点数,
    "reasoning": "判定の根拠（1-2文）"
}

例:
入力: "今日の予定を教えて"
出力: {
    "intent": "schedule_query",
    "scope": "today",
    "confidence_base": 0.98,
    "reasoning": "明確な予定問い合わせ。時間キー『今日』と動詞『教えて』がある。"
}

入力: "予定が立て込んでる"
出力: {
    "intent": "not_schedule",
    "scope": "not_applicable",
    "confidence_base": 0.95,
    "reasoning": "話者の状況説明/感想であり、予定確認を求めていない。"
}

---

ユーザ発話を分類してください。
```

### 2.4 デフォルト判定器モデル

- **初期**: メインモデル（`elyza-mom`）を流用。分類タスク用にプロンプトを特化させる。
- **将来**: 専用軽量分類モデルに置き換え可（速度向上）。
- **環境変数**: `CLASSIFIER_MODEL_NAME` で指定可能。

### 2.5 分類器関数の統合実装スケルトン

```python
CLASSIFIER_MODEL_NAME = "elyza-mom"  # または専用モデル名
CLASSIFIER_SYSTEM_PROMPT = """..."""  # 上記 2.3
CLASSIFIER_CONFIDENCE_THRESHOLD = 0.80  # 設定可能

def classify_schedule_intent(
    text: str,
    session_meta: dict | None = None,
    use_llm: bool = True
) -> dict:
    """ユーザ発話から予定問い合わせ意図を分類."""
    
    text = (text or "").strip()
    if not text:
        return {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "reasoning": "空の入力",
            "error": None
        }
    
    # Step 1: 軽量フィルタ
    is_likely, base_conf = _quick_filter(text)
    
    # Step 2: LLMが必要か判定
    if use_llm and (is_likely is None or (0.5 < base_conf < 0.9)):
        # グレーゾーン → LLM
        return _classify_with_llm(text, base_conf)
    elif is_likely is True:
        return {
            "intent": "schedule_query",
            "scope": "unspecified",  # 後で詳細化可
            "confidence": base_conf,
            "reasoning": "正規表現で強い肯定シグナル検出",
            "error": None
        }
    else:
        return {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": base_conf if base_conf else 0.5,
            "reasoning": "スケジュール問い合わせではない",
            "error": None
        }
```

---

## 3. 日付範囲計算（`compute_date_range` 関数）

### 3.1 関数シグネチャ

```python
def compute_date_range(
    scope: str,
    reference_date: date | None = None
) -> tuple[date, date] | None:
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
    pass
```

### 3.2 実装例

```python
from datetime import date, timedelta

def compute_date_range(scope: str, reference_date: date | None = None) -> tuple[date, date] | None:
    """スコープから日付範囲を計算（日本仕様：週は月曜始まり）"""
    
    if reference_date is None:
        reference_date = date.today()
    
    if scope == "today":
        return (reference_date, reference_date)
    
    elif scope == "tomorrow":
        tomorrow = reference_date + timedelta(days=1)
        return (tomorrow, tomorrow)
    
    elif scope == "week":
        # 月曜始まり
        monday = reference_date - timedelta(days=reference_date.weekday())
        sunday = monday + timedelta(days=6)
        return (monday, sunday)
    
    elif scope == "month":
        first_day = reference_date.replace(day=1)
        if reference_date.month == 12:
            last_day = first_day.replace(year=first_day.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = first_day.replace(month=first_day.month + 1, day=1) - timedelta(days=1)
        return (first_day, last_day)
    
    elif scope in ("next", "upcoming", "unspecified"):
        return None  # ルール処理で別途処理
    
    else:
        return None
```

---

## 4. ロギング機構

### 4.1 ログスキーマ

```json
{
  "timestamp": "2026-01-02T15:30:45.123456Z",
  "event_type": "schedule_classification",
  "user_message": "今日の予定は？",
  "classifier_intent": "schedule_query",
  "classifier_scope": "today",
  "classifier_confidence": 0.98,
  "classifier_reasoning": "明確な予定問い合わせ",
  "chosen_path": "rule-based",
  "reply_text": "・15:00 会議\n・18:00 夕食",
  "processing_time_ms": 45,
  "error": null
}
```

### 4.2 ロギング関数

```python
import json
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
CLASSIFIER_LOG_PATH = LOG_DIR / "classifier_events.log"

def log_event(
    user_message: str,
    judgment: dict,
    chosen_path: str,  # "rule-based" or "llm"
    reply_text: str,
    processing_time_ms: float,
    error: str | None = None
) -> None:
    """
    分類イベントをJSON Lines形式でログに記録。
    
    Args:
        user_message (str): ユーザの発話
        judgment (dict): 分類器の判定結果
        chosen_path (str): 選択された処理路（rule-based / llm）
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
    except Exception as e:
        print(f"Logging error: {e}")
```

### 4.3 ログ集計スクリプト（運用用）

```python
def analyze_classifier_log(log_file_path: Path = CLASSIFIER_LOG_PATH) -> dict:
    """
    ロギング結果を集計し、精度・エラー率を計算。
    
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
            "false_positive_detected": list,  # 手動レビュー必須
        }
    """
    pass
```

---

## 5. `api_chat` フローの統合詳細

### 5.1 修正前後の比較

#### **Before** (`app.py` 既存)
```python
@app.route("/api/chat", methods=["POST"])
def api_chat():
    init_session()
    if not is_setup_complete():
        return jsonify({"ok": False, "error": "setup_not_complete"}), 400

    data = request.get_json() or {}
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"ok": False, "error": "no_message"}), 400

    session["chat_history"].append({"role": "user", "text": user_message})
    reply = ask(user_message)  # ← 直接LLMに投げる
    session["chat_history"].append({"role": "assistant", "text": reply})
    session.modified = True

    return jsonify({"ok": True, "reply": reply})
```

#### **After** (判定器統合版)
```python
import time

@app.route("/api/chat", methods=["POST"])
def api_chat():
    init_session()
    if not is_setup_complete():
        return jsonify({"ok": False, "error": "setup_not_complete"}), 400

    data = request.get_json() or {}
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"ok": False, "error": "no_message"}), 400

    session["chat_history"].append({"role": "user", "text": user_message})
    
    # ===== NEW: Classification Phase =====
    start_time = time.time()
    
    judgment = classify_schedule_intent(
        user_message,
        session_meta={"has_schedules": len(session.get("schedules", [])) > 0},
        use_llm=True
    )
    
    # ===== NEW: Routing Decision =====
    if (judgment.get("intent") == "schedule_query" 
        and judgment.get("confidence", 0) >= CLASSIFIER_CONFIDENCE_THRESHOLD):
        # Rule-based processing
        reply = handle_schedule_query(user_message, judgment)
        chosen_path = "rule-based"
    else:
        # LLM processing with safety instruction
        safety_instruction = (
            "\n\nIMPORTANT: ユーザが予定について聞いても、"
            "具体的な予定の事実（日時、内容）を述べないこと。"
            "予定管理画面で確認するよう案内してください。"
        )
        reply = ask(user_message, system_prompt_amendment=safety_instruction)
        chosen_path = "llm"
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    # ===== NEW: Logging =====
    log_event(
        user_message=user_message,
        judgment=judgment,
        chosen_path=chosen_path,
        reply_text=reply,
        processing_time_ms=elapsed_ms,
        error=judgment.get("error")
    )
    
    # Session update
    session["chat_history"].append({"role": "assistant", "text": reply})
    session.modified = True

    return jsonify({"ok": True, "reply": reply})
```

### 5.2 `handle_schedule_query` の拡張

現行の `handle_schedule_query` に judgment パラメータを追加：

```python
def handle_schedule_query(
    user_message: str,
    judgment: dict | None = None
) -> str:
    """
    スケジュール問い合わせを処理し、登録済み予定から回答を生成。
    
    Args:
        user_message (str): ユーザ発話
        judgment (dict | None): 分類器の判定結果。Noneの場合は従来のルール処理
    
    Returns:
        str: 応答テキスト
    """
    
    schedules = session.get("schedules") or []
    if not schedules:
        return "予定がまだ入ってないわよ。まずは予定を追加しなさい。"
    
    now = datetime.now()
    
    # judgment がある場合は scope を優先
    if judgment:
        scope = judgment.get("scope")
    else:
        # Fallback: 従来のルール判定（既存コード）
        scope = None  # infer from user_message
    
    # Date range の計算
    if scope and scope != "unspecified":
        date_range = compute_date_range(scope)
        if date_range:
            start_date, end_date = date_range
            # 範囲内の予定をフィルタ
            filtered = [
                it for it in schedules
                if _is_in_range(it, start_date, end_date)
            ]
            # ... (既存の整形・応答ロジック)
    
    # scope が next / upcoming / unspecified の場合は既存ロジック
    # ... (既存コード継続)
```

### 5.3 エラーハンドリング

```python
@app.route("/api/chat", methods=["POST"])
def api_chat():
    # ... 前文同じ ...
    
    try:
        judgment = classify_schedule_intent(user_message)
    except TimeoutError:
        print("Classifier timeout. Falling back to LLM.")
        judgment = {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "error": "Classifier timeout"
        }
        chosen_path = "llm"  # Fallback
        reply = ask(user_message)
    except Exception as e:
        print(f"Classifier error: {e}")
        judgment = {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "error": str(e)
        }
        chosen_path = "llm"  # Fallback
        reply = ask(user_message)
    
    # ... 以下同じ ...
```

---

## 6. `ask()` 関数の改良（安全プロンプト対応）

### 6.1 現在のシグネチャ

```python
def ask(prompt: str) -> str:
    """..."""
```

### 6.2 改良版シグネチャ

```python
def ask(
    prompt: str,
    system_prompt_amendment: str | None = None
) -> str:
    """
    LLMに質問を投げて回答を得る。
    
    Args:
        prompt (str): ユーザプロンプト
        system_prompt_amendment (str | None): 
            システムプロンプトに追加する指示（安全プロンプト等）
    
    Returns:
        str: LLMの応答
    """
    try:
        # system_prompt_amendment があれば、プロンプトの冒頭に追加
        if system_prompt_amendment:
            full_prompt = system_prompt_amendment + "\n\n" + prompt
        else:
            full_prompt = prompt
        
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": GENERATED_MODEL_NAME,
                "prompt": full_prompt,
                "stream": False
            },
            timeout=300,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.RequestException as e:
        print("LLM error:", e)
        return "ごめん、接続がうまくいかないみたい。ollama が起動しているか確認してみて。"
```

---

## 7. 設定・初期化（`init_session` 等）

### 7.1 設定値の追加

```python
# == Configuration ==
CLASSIFIER_CONFIDENCE_THRESHOLD = 0.80  # 環境変数で上書き可
CLASSIFIER_MODEL_NAME = "elyza-mom"     # 環境変数で上書き可
CLASSIFIER_USE_LLM = True                # False なら正規表現のみ

# ログ設定
ENABLE_CLASSIFIER_LOGGING = True
```

### 7.2 Mom Settings への組み込み（オプション）

将来的にUIから調整可能にする場合：

```python
MOM_MULTI_KEYS = {
    "listen_style",
    "schedule_completion_fields",
}

# mom_settings に追加可能
# {
#   "...",
#   "classifier_threshold": 0.80,
#   "classifier_enabled": true,
#   "use_llm_classifier": true
# }
```

---

## 8. テスト計画

### 8.1 ユニットテスト

| テスト対象 | テスト項目 | 成功基準 |
|-----------|-----------|---------|
| `classify_schedule_intent()` | 肯定例（「今日の予定は？」） | intent=schedule_query, confidence >= 0.85 |
| | 否定例（「予定が立て込んでる」） | intent=not_schedule, confidence >= 0.85 |
| | グレーゾーン（「予定ってある？」） | confidence 0.5～0.8（LLM判定） |
| `compute_date_range()` | scope="today" | (本日, 本日) |
| | scope="week" | (月曜, 日曜) |
| | scope="month" | (1日, 末日) |
| `log_event()` | 正常系 | JSONログが1行記録される |
| | ファイルI/Oエラー | エラーログ出力、処理継続 |

### 8.2 統合テスト

| シナリオID | 入力 | 期待動作 | 合格基準 |
|-----------|------|---------|---------|
| IT-01 | 「今日の予定は？」 | judge + rule処理 → 予定一覧 | ✅ rule応答のみ |
| IT-02 | 「予定が立て込んでる」 | judge (low) → LLM処理 | ✅ LLM応答のみ |
| IT-03 | LLMタイムアウト | judge timeout → LLM fallback | ✅ graceful fallback |
| IT-04 | 予定なし + 「今日の予定？」 | rule処理 → 「予定がない」 | ✅ 正確な応答 |

### 8.3 精度評価テスト

- テストセット: 最低100発話
- 評価指標: Precision, Recall, F1 Score
- 目標: F1 >= 0.90

---

## 9. デプロイメント

### 9.1 段階的ロールアウト

| フェーズ | 内容 | 期間 |
|---------|------|------|
| **Phase 0: Test** | ローカル開発環境でのテスト | 1週 |
| **Phase 1: Shadow** | 分類器は実行するが、結果を使わず（ログのみ） | 1週 |
| **Phase 2: Gradual** | 信頼度閾値を段階的に引き上げ（0.95 → 0.90 → 0.85 → 0.80） | 2週 |
| **Phase 3: Full** | 本番運用（閾値0.80）、ユーザ反応監視 | 継続 |

### 9.2 フィーチャーフラグ

```python
CLASSIFIER_ENABLED = os.getenv("CLASSIFIER_ENABLED", "true").lower() == "true"
CLASSIFIER_CONFIDENCE_THRESHOLD = float(os.getenv("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.80"))

# api_chat 内
if CLASSIFIER_ENABLED:
    judgment = classify_schedule_intent(user_message)
    # ... routing ...
else:
    # fallback: 従来のルール処理のみ
    judgment = {"intent": "not_schedule"}
```

---

## 10. 監視・運用

### 10.1 週次メトリクス集計

```python
def weekly_classifier_report(log_file: Path = CLASSIFIER_LOG_PATH) -> dict:
    """
    1週間分のログを集計し、運用レポートを生成。
    """
    results = analyze_classifier_log(log_file)
    
    report = {
        "week": datetime.now().isocalendar()[1],
        "total_events": results["total_events"],
        "schedule_query_ratio": results["schedule_query_count"] / results["total_events"],
        "avg_confidence_schedule": results["avg_confidence_schedule"],
        "rule_based_ratio": results["rule_based_count"] / results["total_events"],
        "error_rate": results["error_count"] / results["total_events"],
        "recommendations": [
            # 自動生成
        ]
    }
    return report
```

### 10.2 アラート条件

- Error rate > 5% → 警告ログ出力、判定器の状態確認
- False Positive > 3% → 閾値引き上げ検討
- 平均処理時間 > 200ms → 分類器の最適化検討

---

## 11. 実装チェックリスト

- [ ] `classify_schedule_intent()` 関数実装
- [ ] `_quick_filter()` 実装
- [ ] `_classify_with_llm()` 実装
- [ ] 分類器用LLMプロンプト調整・テスト
- [ ] `compute_date_range()` 関数実装
- [ ] `log_event()` 関数実装
- [ ] `analyze_classifier_log()` 関数実装
- [ ] `api_chat` フロー統合
- [ ] `ask()` 関数改良（安全プロンプト対応）
- [ ] ユニットテスト実装
- [ ] 統合テスト実装
- [ ] 精度評価テスト（100発話セット）
- [ ] ロギング・集計スクリプト
- [ ] 環境変数・設定ファイル対応
- [ ] ドキュメント更新
- [ ] コード レビュー＆マージ

---

**バージョン**: 1.0  
**作成日**: 2026-01-02  
**ステータス**: ドラフト
