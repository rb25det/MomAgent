import json
import subprocess
import time
import logging
from pathlib import Path
from datetime import datetime

import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
)
from werkzeug.datastructures import MultiDict

from prompts.builder import build_prompt
from classifier import (
    classify_schedule_intent,
    compute_date_range,
    log_event,
    analyze_classifier_log,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
)
import os
from uuid import uuid4

# 環境変数で LLM 分類器を有効化/無効化できる（デフォルト: True）
USE_LLM_CLASSIFIER = os.getenv("USE_LLM_CLASSIFIER", "true").lower() == "true"

# LLM に渡す会話履歴の件数（最新 N 件）
RECENT_HISTORY_FOR_LLM = 30

# =========================
# 基本設定
# =========================

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
GENERATED_MODEL_NAME = "elyza-mom"

CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "mom_config.json"

MODELFILE_PATH = Path("Modelfile")

# ログ保存ディレクトリ（セッション別ログをここに作る）
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # 開発用。適当なランダム文字列に変えてOK


# =========================
# ★ 追加：複数選択キーを常に list で保存するための定義
# =========================

PROFILE_MULTI_KEYS = {
    "active_time_slots",
    "topic_weights",
}

MOM_MULTI_KEYS = {
    "listen_style",
}


# =========================
# helpers（セッション・予定）
# =========================

def init_session():
    if "profile" not in session:
        session["profile"] = {}
    if "mom_settings" not in session:
        session["mom_settings"] = {}
    if "schedules" not in session:
        session["schedules"] = []
    if "chat_history" not in session:
        session["chat_history"] = []
    # セッション固有ログファイルを準備
    if "session_log" not in session:
        sid = uuid4().hex
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = LOGS_DIR / f"chat_{sid}_{ts}.txt"
        session["session_id"] = sid
        session["session_log"] = str(path)
        # ヘッダを書き込む
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New session started\n")
    if "model_ready" not in session:
        session["model_ready"] = False


def add_chat_message(role: str, text: str, max_messages: int = 10) -> None:
    """セッションの chat_history にメッセージを追加し、長さを制限するヘルパー。

    既定で最新の `max_messages` 件のみ保持することで、セッション Cookie の肥大化を防ぐ。
    """
    history = session.get("chat_history") or []
    history.append({"role": role, "text": text})
    # 保持件数を超えたら古いものを削除
    if len(history) > max_messages:
        history = history[-max_messages:]
    session["chat_history"] = history
    session.modified = True
    # セッションログに追記
    try:
        log_path = session.get("session_log")
        if log_path:
            p = Path(log_path)
            with p.open("a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                role_label = "あなた" if role == "user" else "お母さん"
                f.write(f"[{ts}] {role_label}> {text}\n")
    except Exception as e:
        logging.error(f"Failed to write session log: {e}")


def is_setup_complete() -> bool:
    return bool(session.get("model_ready"))


def clear_chat_history():
    session["chat_history"] = []
    session.modified = True
    # 新しいセッションログを開始（セッションをクリアしたときは別ファイルへ）
    try:
        sid = uuid4().hex
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = LOGS_DIR / f"chat_{sid}_{ts}.txt"
        session["session_id"] = sid
        session["session_log"] = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Session cleared, new log started\n")
        session.modified = True
    except Exception as e:
        logging.error(f"Failed to rotate session log: {e}")


def sort_schedules_for_display(schedules):
    def keyfn(s):
        pr = int(s.get("priority", "3"))
        date = s.get("date", "9999-12-31")
        time = s.get("time", "23:59")
        return (pr, date, time)
    return sorted(schedules, key=keyfn)


def require_setup_or_redirect():
    if not is_setup_complete():
        return redirect(url_for("profile"))
    return None


# =========================
# Ollama API 呼び出し（チャット用）
# =========================

def ask(prompt: str, system_prompt_amendment: str = "") -> str:
    """
    LLMに質問を投げて回答を得る。
    
    Args:
        prompt (str): ユーザプロンプト
        system_prompt_amendment (str): システムプロンプトに追加する指示（安全プロンプト等）
    
    Returns:
        str: LLMの応答
    """
    try:
        # system_prompt_amendment があれば、ユーザプロンプトの冒頭に追加
        # （Ollama API では "prompt" フィールドはシステムプロンプト後のユーザ入力部分）
        if system_prompt_amendment:
            full_prompt = system_prompt_amendment + "\n\n" + prompt
        else:
            full_prompt = prompt
        
        logging.debug(f"Calling Ollama with model='{GENERATED_MODEL_NAME}', prompt length={len(full_prompt)}")
        
        r = requests.post(
            OLLAMA_URL,
            json={"model": GENERATED_MODEL_NAME, "prompt": full_prompt, "stream": False},
            timeout=120,  # 120秒でタイムアウト
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        logging.debug(f"LLM response length: {len(response)}")
        return response
    except requests.exceptions.Timeout:
        logging.error("LLM request timed out after 120 seconds")
        return "ごめん、回答に時間がかかってしまったわ。もう一度聞いてみてくれる？"
    except requests.exceptions.RequestException as e:
        logging.error(f"LLM error: {e}")
        return "ごめん、接続がうまくいかないみたい。ollama が起動しているか確認してみて。"


# =========================
# Modelfile の生成
# =========================

def write_modelfile(config: dict):
    system_prompt = build_prompt(config)
    content = f"""FROM dsasai/llama3-elyza-jp-8b

SYSTEM \"\"\"{system_prompt}
\"\"\"

PARAMETER temperature 0.7
PARAMETER num_ctx 8192
"""
    MODELFILE_PATH.write_text(content, encoding="utf-8")


# =========================
# JSON 作成処理
# =========================

def write_config_json(profile: dict, mom_form: MultiDict) -> dict:
    # profile から値を取り出し（正規化済み：複数選択は list）
    active_slots = profile.get("active_time_slots") or []
    topics = profile.get("topic_weights") or []

    def to_int_or_none(v):
        if v is None or v == "":
            return None
        try:
            return int(v)
        except ValueError:
            return None

    def to_float_or_none(v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except ValueError:
            return None

    age = to_int_or_none(profile.get("age"))
    avg_sleep = to_float_or_none(profile.get("average_sleep_hours"))
    breakfast_level = to_int_or_none(profile.get("breakfast_frequency"))
    exercise_per_week = to_int_or_none(profile.get("exercise_frequency_per_week"))

    # mom_settings
    strict_kind = to_float_or_none(mom_form.get("strict_kind")) or 0.0
    quiet_talkative = to_float_or_none(mom_form.get("quiet_talkative")) or 0.0
    dialect_type = mom_form.get("dialect_type") or "normal"

    listen_styles = mom_form.getlist("listen_style")
    listen_deeply = 1.0 if "listen_deeply" in listen_styles else 0.0
    give_clear_advice = 1.0 if "give_clear_advice" in listen_styles else 0.0
    praise_a_lot = 1.0 if "praise_a_lot" in listen_styles else 0.0

    topic_initiation_frequency = to_float_or_none(mom_form.get("topic_initiation_frequency")) or 0.5
    topic_weight_seriousness = to_float_or_none(mom_form.get("topic_weight_seriousness")) or 0.5

    config = {
        "user": {
            "nickname": profile.get("nickname"),
            "gender": profile.get("gender"),
            "age": age,
            "grade": profile.get("grade") or None,
            "role_status": profile.get("role_status") or None,
            "life": {
                "wake_time_weekday": profile.get("wake_time_weekday"),
                "sleep_time_weekday": profile.get("sleep_time_weekday"),
                "wake_time_holiday": profile.get("wake_time_holiday"),
                "sleep_time_holiday": profile.get("sleep_time_holiday"),
                "average_sleep_hours": avg_sleep,
                "active_time_slots": list(active_slots),
            },
            "health": {
                "breakfast_frequency_level": breakfast_level,
                "exercise_frequency_per_week": exercise_per_week,
            },
            "topic_weights": {t: 1.0 for t in topics},
            "worry_now": profile.get("worry_now") or "",
        },
        "mother_model": {
            "strict_kind": strict_kind,
            "quiet_talkative": quiet_talkative,
            "dialect_type": dialect_type,
            "listen_deeply": listen_deeply,
            "give_clear_advice": give_clear_advice,
            "praise_a_lot": praise_a_lot,
            "topic_initiation_frequency": topic_initiation_frequency,
            "topic_weight_seriousness": topic_weight_seriousness,
        },
        "generated_model_name": GENERATED_MODEL_NAME,
    }

    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return config


def dict_to_multidict(d: dict) -> MultiDict:
    items = []
    for k, v in (d or {}).items():
        if isinstance(v, list):
            for vv in v:
                items.append((k, vv))
        else:
            items.append((k, v))
    return MultiDict(items)


def rebuild_model(profile_data: dict, mom_settings_data: dict) -> None:
    """プロフィール・お母さん設定からカスタムモデルを再構築。
    
    Ollama CREATE コマンドに 60 秒のタイムアウトを設定。
    タイムアウトやエラーが発生した場合はログ出力して処理を続行。
    """
    mom_form = dict_to_multidict(mom_settings_data)
    config = write_config_json(profile_data, mom_form)
    write_modelfile(config)

    try:
        subprocess.run(
            ["ollama", "create", GENERATED_MODEL_NAME, "-f", str(MODELFILE_PATH)],
            check=True,
            timeout=60,  # 60秒でタイムアウト
        )
        logging.info(f"Model '{GENERATED_MODEL_NAME}' rebuilt successfully")
    except subprocess.TimeoutExpired:
        logging.warning(f"Ollama model rebuild timed out after 60 seconds. Continuing anyway.")
        # タイムアウトしても処理は継続（既存モデルを使用）
    except subprocess.CalledProcessError as e:
        logging.error(f"Ollama model rebuild failed: {e}")
        # エラーが発生しても処理は継続
    except Exception as e:
        logging.error(f"Unexpected error during model rebuild: {e}")

    clear_chat_history()
    session["model_ready"] = True
    session.modified = True


def normalize_form_to_dict(form: MultiDict, multi_keys) -> dict:
    """
    ★ 重要：複数選択は必ず list、単一は string に正規化して dict 化する
    """
    out = {}
    for key in form.keys():
        vals = form.getlist(key)
        if key in multi_keys:
            out[key] = vals
        else:
            out[key] = vals[0] if vals else ""
    return out


# =========================
# routes
# =========================

@app.route("/")
def index():
    init_session()
    # 初期設定完了済みなら start へ（→ チャット開始画面）
    if is_setup_complete():
        return redirect(url_for("chat_page"))
    return redirect(url_for("profile"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    init_session()

    if request.method == "POST":
        # ★ 修正：複数選択を常に list として保存
        profile_data = normalize_form_to_dict(request.form, PROFILE_MULTI_KEYS)
        session["profile"] = profile_data
        session.modified = True

        # 初回セットアップ中：次はお母さん設定へ
        if not is_setup_complete():
            session["model_ready"] = False
            session.modified = True
            return redirect(url_for("mom_settings_page"))

        # セットアップ後：mom_settings があれば再構築して chat へ
        if session.get("mom_settings"):
            try:
                rebuild_model(session["profile"], session["mom_settings"])
            except subprocess.CalledProcessError as e:
                print("ollama create error:", e)
                session["model_ready"] = False
                session.modified = True
                return "<p>モデル再構築に失敗しました。`ollama create` のログを確認してください。</p>", 500
            return redirect(url_for("chat_page"))

        # mom_settingsが無いなら設定へ
        session["model_ready"] = False
        session.modified = True
        return redirect(url_for("mom_settings_page"))

    return render_template("profile.html")


@app.route("/mom_settings", methods=["GET", "POST"])
def mom_settings_page():
    init_session()

    if request.method == "POST":
        # ★ 修正：複数選択を常に list として保存
        mom_settings_data = normalize_form_to_dict(request.form, MOM_MULTI_KEYS)
        session["mom_settings"] = mom_settings_data
        session.modified = True

        profile_data = session.get("profile") or {}
        if not profile_data:
            session["model_ready"] = False
            session.modified = True
            return redirect(url_for("profile"))

        was_ready_before = is_setup_complete()  # ★ここがポイント（再構築前の状態を保存）

        try:
            rebuild_model(profile_data, mom_settings_data)
        except subprocess.CalledProcessError as e:
            print("ollama create error:", e)
            session["model_ready"] = False
            session.modified = True
            return "<p>モデル生成に失敗しました。`ollama create` のログを確認してください。</p>", 500

        # ★初回セットアップ（= 以前readyじゃない）なら start
        # ★設定変更（= 以前readyだった）なら chat に戻す
        if was_ready_before:
            return redirect(url_for("chat_page"))
        return redirect(url_for("start_page"))

    return render_template("mom_settings.html")


@app.route("/start")
def start_page():
    init_session()
    if not is_setup_complete():
        return redirect(url_for("profile"))
    return render_template("start.html")


@app.route("/chat", methods=["GET"])
def chat_page():
    init_session()
    if not is_setup_complete():
        return redirect(url_for("profile"))

    if not session.get("chat_history"):
        # より自然でお母さんらしい初期一言に変更
        add_chat_message("assistant", "久しぶりね、元気で過ごしてる？何か話したいことある？")

    return render_template("chat.html", history=session.get("chat_history"))


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    チャットAPI。ユーザ発話を受け取り、以下の処理を実行：
    1. 発話から予定問い合わせ意図を判定
    2. 予定問い合わせなら ルールベース処理（schedule query）
    3. それ以外なら LLM処理（安全プロンプト付き）
    """
    init_session()
    if not is_setup_complete():
        return jsonify({"ok": False, "error": "setup_not_complete"}), 400

    data = request.get_json() or {}
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"ok": False, "error": "no_message"}), 400

    add_chat_message("user", user_message)
    
    # ===== Phase 1: Classification (高速なルール判定のみ) =====
    # 注: use_llm=False なので、LLM呼び出しなし → 高速
    start_time = time.time()

    # use_llm は環境変数でデフォルト制御（USE_LLM_CLASSIFIER）し、
    # リクエスト JSON の 'use_llm' フィールドまたはクエリパラメータで上書き可能。
    use_llm = USE_LLM_CLASSIFIER
    # JSON body がある場合は優先して参照
    try:
        req_json = request.get_json(silent=True) or {}
    except Exception:
        req_json = {}

    if isinstance(req_json, dict) and "use_llm" in req_json:
        use_llm = bool(req_json.get("use_llm"))
    elif request.args.get("use_llm") is not None:
        use_llm = request.args.get("use_llm").lower() in ("1", "true", "yes")

    logging.debug(f"Classifier: use_llm={use_llm} (env_default={USE_LLM_CLASSIFIER}) for message='{user_message[:60]}'")

    try:
        judgment = classify_schedule_intent(
            user_message,
            session_meta={"has_schedules": len(session.get("schedules", [])) > 0},
            use_llm=use_llm,
        )
        classification_time_ms = (time.time() - start_time) * 1000
        logging.debug(f"Classification completed in {classification_time_ms:.1f}ms (use_llm={use_llm})")
    except Exception as e:
        logging.error(f"Classifier error: {e}")
        judgment = {
            "intent": "not_schedule",
            "scope": "unspecified",
            "confidence": 0.0,
            "error": str(e)
        }
    
    # ===== Phase 2: Routing Decision =====
    if (judgment.get("intent") == "schedule_query" 
        and judgment.get("confidence", 0) >= CLASSIFIER_CONFIDENCE_THRESHOLD):
        # Rule-based processing
        reply = _handle_schedule_query_with_judgment(user_message, judgment)
        chosen_path = "rule-based"
    else:
        # LLM processing with safety instruction
        safety_instruction = (
            "重要な指示: ユーザが予定やスケジュールについて聞いても、"
            "具体的な予定の事実（日時、内容、場所など）を述べないこと。"
            "代わりに『予定の詳細については予定管理画面を確認してください』と案内すること。"
        )
        # LLM に渡すプロンプトを作成：直近の会話履歴（最新 RECENT_HISTORY_FOR_LLM 件）＋現在のユーザ発話
        recent = session.get("chat_history") or []
        recent = recent[-RECENT_HISTORY_FOR_LLM:]
        # 履歴をテキスト化（日本語ラベルを使用）
        history_lines = []
        for m in recent:
            role_label = "ユーザ" if m.get("role") == "user" else "お母さん"
            history_lines.append(f"{role_label}: {m.get('text')}")
        history_text = "\n".join(history_lines).strip()
        if history_text:
            full_prompt = history_text + "\n\nユーザ: " + user_message
        else:
            full_prompt = "ユーザ: " + user_message

        reply = ask(full_prompt, system_prompt_amendment=safety_instruction)
        chosen_path = "llm"
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    # ===== Phase 3: Logging =====
    try:
        log_event(
            user_message=user_message,
            judgment=judgment,
            chosen_path=chosen_path,
            reply_text=reply,
            processing_time_ms=elapsed_ms,
            error=judgment.get("error")
        )
    except Exception as e:
        logging.error(f"Logging error: {e}")
    
    # Session update (append assistant reply and cap history length)
    add_chat_message("assistant", reply)

    return jsonify({"ok": True, "reply": reply})


def _handle_schedule_query_with_judgment(user_message: str, judgment: dict) -> str:
    """
    判定器の結果を基に、スケジュール問い合わせを処理。
    
    Args:
        user_message (str): ユーザ発話
        judgment (dict): 分類器の判定結果（scope, confidence等を含む）
    
    Returns:
        str: 応答テキスト
    """
    schedules = session.get("schedules") or []
    if not schedules:
        return "予定がまだ入ってないわよ。まずは予定を追加しなさい。"
    
    scope = judgment.get("scope")
    now = datetime.now()
    
    # スコープから日付範囲を計算
    if scope and scope != "unspecified":
        date_range = compute_date_range(scope)
        if date_range:
            start_date, end_date = date_range
            # 範囲内の予定をフィルタ
            filtered = [
                it for it in schedules
                if _is_schedule_in_range(it, start_date, end_date)
            ]
            filtered.sort(
                key=lambda it: (it.get("date", "9999-12-31"), it.get("time", "23:59"))
            )
            return _format_schedule_list(f"{_scope_to_label(scope)}の予定", filtered)
    
    # scope が next の場合
    if scope == "next":
        nxt = _pick_next_schedule(schedules, now)
        if nxt is None:
            return "これからの予定は入ってないわよ。"
        d = (nxt.get("date") or "").strip()
        t = (nxt.get("time") or "").strip() or "時間未定"
        content = (nxt.get("content") or "").strip() or "（内容未入力）"
        return f"次の予定は {d} {t} の「{content}」よ。忘れないようにしなさい。"
    
    # scope が upcoming または unspecified の場合
    candidates = []
    for it in schedules:
        dt = _schedule_start_dt(it, default_time="00:00")
        if dt is None:
            continue
        if dt >= now:
            candidates.append((dt, it))
    candidates.sort(key=lambda x: x[0])
    upcoming = [it for _, it in candidates[:3]]
    if not upcoming:
        return "これからの予定は入ってないわよ。"
    return _format_schedule_list("直近の予定", upcoming)


def _is_schedule_in_range(schedule: dict, start_date, end_date) -> bool:
    """予定が指定された日付範囲内にあるか判定。"""
    from datetime import date
    try:
        sched_date = datetime.strptime(schedule.get("date", ""), "%Y-%m-%d").date()
        return start_date <= sched_date <= end_date
    except (ValueError, TypeError):
        return False


def _schedule_start_dt(item: dict, default_time: str = "00:00"):
    """予定の開始日時を datetime オブジェクトで返す。"""
    try:
        d_str = item.get("date", "").strip()
        t_str = (item.get("time", "").strip() or default_time)
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
        t = datetime.strptime(t_str, "%H:%M").time()
        return datetime.combine(d, t)
    except (ValueError, TypeError):
        return None


def _pick_next_schedule(items: list, now: datetime):
    """次の予定を取得（最も近い1件）。"""
    candidates = []
    for it in items:
        dt = _schedule_start_dt(it, default_time="00:00")
        if dt is None:
            continue
        if dt >= now:
            candidates.append((dt, it))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _format_schedule_list(title: str, items: list) -> str:
    """予定リストをフォーマット。"""
    if not items:
        return f"{title}は入ってないわよ。"
    
    lines = [f"{title}はこれね。"]
    for it in items:
        time_str = (it.get("time") or "").strip() or "時間未定"
        content = (it.get("content") or "").strip() or "（内容未入力）"
        line = f"・{time_str} {content}"
        lines.append(line)
    return "\n".join(lines)


def _scope_to_label(scope: str) -> str:
    """スコープを日本語ラベルに変換。"""
    labels = {
        "today": "今日",
        "tomorrow": "明日",
        "week": "今週",
        "month": "今月",
        "next": "次",
        "upcoming": "直近"
    }
    return labels.get(scope, "予定")


# -------------------------
# schedule（初期設定が終わるまでアクセス禁止）
# -------------------------

@app.route("/schedule_list")
def schedule_list():
    init_session()
    guard = require_setup_or_redirect()
    if guard:
        return guard

    schedules = sort_schedules_for_display(session.get("schedules", []))
    return render_template("schedule_list.html", schedules=schedules)


@app.route("/schedule_add", methods=["GET", "POST"])
def schedule_add():
    init_session()
    guard = require_setup_or_redirect()
    if guard:
        return guard

    if request.method == "POST":
        form = request.form.to_dict(flat=True)
        item = {
            "date": form.get("date", ""),
            "time": form.get("time", ""),
            "content": form.get("content", ""),
            "priority": form.get("priority", "3"),
            "remind_value": form.get("remind_value", ""),
            "remind_unit": form.get("remind_unit", "hours"),
            "created_at": datetime.now().isoformat(),
        }
        session["schedules"].append(item)
        session.modified = True
        return redirect(url_for("schedule_list"))

    return render_template("schedule_add.html")


@app.route("/schedule_edit/<int:index>", methods=["GET", "POST"])
def schedule_edit(index):
    init_session()
    guard = require_setup_or_redirect()
    if guard:
        return guard

    schedules = session.get("schedules", [])
    if index < 0 or index >= len(schedules):
        return redirect(url_for("schedule_list"))

    if request.method == "POST":
        form = request.form.to_dict(flat=True)
        schedules[index] = {
            "date": form.get("date", ""),
            "time": form.get("time", ""),
            "content": form.get("content", ""),
            "priority": form.get("priority", "3"),
            "remind_value": form.get("remind_value", ""),
            "remind_unit": form.get("remind_unit", "hours"),
            "created_at": schedules[index].get("created_at", datetime.now().isoformat()),
        }
        session["schedules"] = schedules
        session.modified = True
        return redirect(url_for("schedule_list"))

    return render_template("schedule_edit.html", item=schedules[index], index=index)


@app.route("/schedule_delete/<int:index>", methods=["POST"])
def schedule_delete(index):
    init_session()
    guard = require_setup_or_redirect()
    if guard:
        return guard

    schedules = session.get("schedules", [])
    if 0 <= index < len(schedules):
        schedules.pop(index)
        session["schedules"] = schedules
        session.modified = True
    return redirect(url_for("schedule_list"))


# -------------------------
# Dev only
# -------------------------

@app.route("/reset_all")
def reset_all():
    session.clear()
    return "cleared"


if __name__ == "__main__":
    import os
    import webbrowser
    import threading

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")

    # debug=True のとき reloader で二重起動しがちなので対策
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.0, open_browser).start()

    app.run(host="127.0.0.1", port=5000, debug=True)
