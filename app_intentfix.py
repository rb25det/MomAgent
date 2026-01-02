import json
import subprocess
from pathlib import Path
from datetime import datetime, date, timedelta

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

# =========================
# 基本設定
# =========================

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
GENERATED_MODEL_NAME = "elyza-mom"

CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "mom_config.json"

MODELFILE_PATH = Path("Modelfile")

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
    "schedule_completion_fields",
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
    if "model_ready" not in session:
        session["model_ready"] = False
    if "schedule_completion" not in session:
        session["schedule_completion"] = None
    if "schedule_completion_pending" not in session:
        session["schedule_completion_pending"] = False


def is_setup_complete() -> bool:
    return bool(session.get("model_ready"))


def clear_chat_history():
    session["chat_history"] = []
    session.modified = True


def sort_schedules_for_display(schedules):
    def keyfn(s):
        pr = int(s.get("priority", "3"))
        date = s.get("date", "9999-12-31")
        time = s.get("time", "23:59")
        return (pr, date, time)
    return sorted(schedules, key=keyfn)

# -------------------------
# schedule query（チャットで予定を聞かれたときの応答）
# - 予定の「事実」はコード側で生成し、LLMには任せない（捏造回避）
# - 誤反応を避けるため、"予定" という単語が出た"だけ"では反応しない
# -------------------------

SCHEDULE_SCOPE_WORDS = ("今日", "明日", "今週", "来週", "今月", "次", "直近", "これから")
SCHEDULE_NOUN_WORDS = ("予定", "スケジュール", "schedule")
SCHEDULE_REQUEST_WORDS = ("教えて", "見せて", "確認", "知りたい", "一覧", "見たい", "教え", "把握")


def _parse_date_str(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_time_str(s: str) -> str | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        datetime.strptime(s, "%H:%M")  # validate only
        return s
    except Exception:
        return None


def _schedule_start_dt(item: dict, *, default_time: str = "00:00") -> datetime | None:
    d = _parse_date_str(item.get("date", ""))
    if d is None:
        return None
    t = _parse_time_str(item.get("time", "")) or default_time
    try:
        tm = datetime.strptime(t, "%H:%M").time()
        return datetime.combine(d, tm)
    except Exception:
        return None


def _start_of_week(d: date) -> date:
    # 日本の一般的な週始まり（Mon）
    return d - timedelta(days=d.weekday())


def _looks_like_schedule_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False

    t_lower = t.lower()
    has_noun = any(w in t for w in SCHEDULE_NOUN_WORDS) or ("schedule" in t_lower)
    has_scope = any(w in t for w in SCHEDULE_SCOPE_WORDS)
    if not (has_noun or has_scope):
        return False

    has_qmark = ("?" in t) or ("？" in t)
    if has_qmark:
        return True

    # 「今日の予定」みたいに疑問符なしで送る人もいるので、定型の先頭一致は許す
    if t.startswith(("今日の予定", "明日の予定", "今週の予定", "来週の予定", "今月の予定", "次の予定", "直近の予定")):
        return True

    # 依頼語が入っていれば予定問い合わせとみなす
    if any(w in t for w in SCHEDULE_REQUEST_WORDS):
        return True

    # 「今日なにある」系（疑問符なしでも成立するケース）を限定的に拾う
    if has_scope and any(w in t for w in ("何", "なに", "ある", "入ってる", "やること")):
        # ただし「予定が立て込んでる」などの"説明"には反応しない（依頼語なし・疑問符なし）
        if "予定が" in t and any(x in t for x in ("立て込", "詰ま", "いっぱい", "忙し")):
            return False
        return True

    return False


def is_schedule_query(text: str) -> bool:
    return _looks_like_schedule_question(text)


def _format_schedule_item(item: dict) -> str:
    time_str = (item.get("time") or "").strip() or "時間未定"
    content = (item.get("content") or "").strip() or "（内容未入力）"

    extras = []
    location = (item.get("location") or "").strip()
    if location:
        extras.append(f"場所:{location}")

    duration = (item.get("duration_minutes") or "").strip()
    if duration:
        extras.append(f"所要:{duration}分")

    deadline = (item.get("deadline") or "").strip()
    if deadline:
        extras.append(f"締切:{deadline}")

    line = f"・{time_str} {content}"
    if extras:
        line += f"（{' / '.join(extras)}）"
    return line


def _render_schedule_list(title: str, items: list[dict]) -> str:
    if not items:
        return f"{title}は入ってないわよ。"

    lines = [f"{title}はこれね。"]
    for it in items:
        lines.append(_format_schedule_item(it))
    return "\n".join(lines)


def _pick_next_schedule(items: list[dict], now: datetime) -> dict | None:
    candidates = []
    for it in items:
        dt = _schedule_start_dt(it, default_time="00:00")
        if dt is None:
            continue
        if dt >= now:
            candidates.append((dt, it))
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1] if candidates else None


def handle_schedule_query(user_message: str) -> str | None:
    if not is_schedule_query(user_message):
        return None

    schedules = session.get("schedules") or []
    if not schedules:
        return "予定がまだ入ってないわよ。まずは予定を追加しなさい。"

    now = datetime.now()
    today = now.date()
    msg = user_message.strip()

    # scope判定
    mode = None
    start = end = None

    if "今日" in msg:
        mode = "range"
        start = today
        end = today + timedelta(days=1)
        title = "今日の予定"
    elif "明日" in msg:
        mode = "range"
        start = today + timedelta(days=1)
        end = start + timedelta(days=1)
        title = "明日の予定"
    elif "今週" in msg:
        mode = "range"
        start = _start_of_week(today)
        end = start + timedelta(days=7)
        title = "今週の予定"
    elif "来週" in msg:
        mode = "range"
        start = _start_of_week(today) + timedelta(days=7)
        end = start + timedelta(days=7)
        title = "来週の予定"
    elif "今月" in msg:
        mode = "range"
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1)
        else:
            end = start.replace(month=start.month + 1, day=1)
        title = "今月の予定"
    elif any(w in msg for w in ("次", "直近", "これから")):
        mode = "next"
    else:
        mode = "upcoming"

    # range
    if mode == "range":
        in_range = []
        for it in schedules:
            d = _parse_date_str(it.get("date", ""))
            if d is None:
                continue
            if start <= d < end:
                in_range.append(it)

        in_range.sort(key=lambda it: (_schedule_start_dt(it, default_time="00:00") or datetime.max))
        return _render_schedule_list(title, in_range)

    # next
    if mode == "next":
        nxt = _pick_next_schedule(schedules, now)
        if nxt is None:
            return "これからの予定は入ってないわよ。"
        d = (nxt.get("date") or "").strip()
        t = (nxt.get("time") or "").strip() or "時間未定"
        content = (nxt.get("content") or "").strip() or "（内容未入力）"
        return f"次の予定は {d} {t} の「{content}」よ。忘れないようにしなさい。"

    # upcoming（次の予定を最大3件）
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
    return _render_schedule_list("直近の予定", upcoming)


def require_setup_or_redirect():
    if not is_setup_complete():
        return redirect(url_for("profile"))
    return None


# =========================
# schedule completion helpers
# =========================

SCHEDULE_FIELD_QUESTIONS = {
    "remind_value": "リマインドは何時間前（何日前）がいい？",
    "remind_unit": "時間前と日前、どっちにする？",
    "deadline": "それ、いつまでに終わらせたい？",
    "duration_minutes": "どれくらい時間かかりそう？",
    "location": "場所はどこやっけ？",
    "notes": "準備するものある？",
}


def get_schedule_completion_fields() -> list:
    mom_settings = session.get("mom_settings") or {}
    fields = mom_settings.get("schedule_completion_fields") or []
    return list(fields)


def is_missing_field(schedule: dict, field: str) -> bool:
    value = schedule.get(field)
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def pending_completion_fields(schedule: dict, fields: list) -> list:
    pending = []
    for field in fields:
        if field == "remind_unit" and not schedule.get("remind_value"):
            continue
        if is_missing_field(schedule, field):
            pending.append(field)
    return pending


def find_schedule_to_complete(fields: list) -> tuple[int | None, list]:
    schedules = session.get("schedules") or []
    for idx in range(len(schedules) - 1, -1, -1):
        pending = pending_completion_fields(schedules[idx], fields)
        if pending:
            return idx, pending
    return None, []


def parse_first_number(text: str):
    digits = "".join(ch if ch.isdigit() else " " for ch in text)
    parts = [p for p in digits.split() if p]
    if not parts:
        return None
    return int(parts[0])


def parse_remind_value_unit(text: str):
    value = parse_first_number(text)
    unit = None
    lowered = text.strip().lower()
    if "日" in lowered or "days" in lowered:
        unit = "days"
    elif "時間" in lowered or "hours" in lowered or "時" in lowered:
        unit = "hours"
    return value, unit


def apply_completion_answer(schedule: dict, field: str, answer: str) -> None:
    cleaned = answer.strip()
    if field == "remind_value":
        value, unit = parse_remind_value_unit(cleaned)
        schedule["remind_value"] = str(value) if value is not None else cleaned
        if unit:
            schedule["remind_unit"] = unit
        return
    if field == "remind_unit":
        unit = "days" if ("日" in cleaned or "days" in cleaned) else "hours"
        schedule["remind_unit"] = unit
        return
    if field == "duration_minutes":
        value = parse_first_number(cleaned)
        schedule["duration_minutes"] = str(value) if value is not None else cleaned
        return
    schedule[field] = cleaned


def format_schedule_summary(schedule: dict) -> str:
    parts = [f"{schedule.get('date', '')} {schedule.get('time', '')}", schedule.get("content", "")]
    if schedule.get("location"):
        parts.append(f"場所は{schedule['location']}")
    if schedule.get("duration_minutes"):
        parts.append(f"所要時間は{schedule['duration_minutes']}分")
    if schedule.get("deadline"):
        parts.append(f"締切は{schedule['deadline']}")
    if schedule.get("remind_value"):
        unit = "時間前" if schedule.get("remind_unit", "hours") == "hours" else "日前"
        parts.append(f"リマインドは{schedule['remind_value']}{unit}")
    if schedule.get("notes"):
        parts.append(f"備考は{schedule['notes']}")
    return "、".join([p for p in parts if p])


def is_affirmative(text: str) -> bool:
    positive = {"はい", "うん", "いいよ", "ok", "okay", "了解", "合ってる", "それで"}
    t = text.strip().lower()
    return any(p in t for p in positive)


def is_negative(text: str) -> bool:
    negative = {
        "いいえ",
        "違う",
        "ちがう",
        "やめる",
        "キャンセル",
        "中止",
        "今は別の話",
        "別の話",
        "やめとく",
        "no",
        "nope",
    }
    t = text.strip().lower()
    return any(n in t for n in negative)


def start_schedule_completion_if_needed() -> str | None:
    if not session.get("schedule_completion_pending"):
        return None
    fields = get_schedule_completion_fields()
    if not fields:
        session["schedule_completion_pending"] = False
        session.modified = True
        return None
    index, pending = find_schedule_to_complete(fields)
    if index is None:
        session["schedule_completion_pending"] = False
        session.modified = True
        return None
    session["schedule_completion"] = {
        "index": index,
        "pending_fields": pending,
        "current_field": pending[0],
        "awaiting_confirmation": False,
    }
    session.modified = True
    return SCHEDULE_FIELD_QUESTIONS.get(pending[0], "もう少しだけ教えて？")


def handle_schedule_completion(user_message: str) -> str | None:
    completion = session.get("schedule_completion")
    if not completion:
        return None
    schedules = session.get("schedules") or []
    index = completion.get("index")
    if index is None or index >= len(schedules):
        session["schedule_completion"] = None
        session.modified = True
        return None
    schedule = schedules[index]

    if is_negative(user_message):
        session["schedule_completion"] = None
        session["schedule_completion_pending"] = False
        session.modified = True
        return "分かった。今は別の話にしよか。"

    if completion.get("awaiting_confirmation"):
        if is_affirmative(user_message):
            session["schedule_completion"] = None
            # Avoid repeated prompts after completion.
            session["schedule_completion_pending"] = False
            session.modified = True
            return "よし、これで保存しとくね。"
        if is_negative(user_message):
            session["schedule_completion"] = None
            session["schedule_completion_pending"] = False
            session.modified = True
            return "分かった。予定編集画面で直してくれる？"
        return "合ってるかどうか教えてくれる？"

    current_field = completion.get("current_field")
    if current_field:
        apply_completion_answer(schedule, current_field, user_message)
        schedules[index] = schedule
        session["schedules"] = schedules
        session.modified = True

    pending = completion.get("pending_fields") or []
    if pending:
        pending.pop(0)
    if pending:
        completion["pending_fields"] = pending
        completion["current_field"] = pending[0]
        session["schedule_completion"] = completion
        session.modified = True
        return SCHEDULE_FIELD_QUESTIONS.get(pending[0], "もう少しだけ教えて？")

    completion["awaiting_confirmation"] = True
    completion["current_field"] = None
    completion["pending_fields"] = []
    session["schedule_completion"] = completion
    session.modified = True
    summary = format_schedule_summary(schedule)
    return f"じゃあ、{summary}で合ってる？"


# =========================
# Ollama API 呼び出し（チャット用）
# =========================

def ask(prompt: str) -> str:
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": GENERATED_MODEL_NAME, "prompt": prompt, "stream": False},
            timeout=300,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.RequestException as e:
        print("LLM error:", e)
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
    schedule_completion_fields = mom_form.getlist("schedule_completion_fields")

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
            "schedule_completion_fields": list(schedule_completion_fields),
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
    mom_form = dict_to_multidict(mom_settings_data)

    config = write_config_json(profile_data, mom_form)
    write_modelfile(config)

    subprocess.run(
        ["ollama", "create", GENERATED_MODEL_NAME, "-f", str(MODELFILE_PATH)],
        check=True,
    )

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
        session["chat_history"].append({"role": "assistant", "text": "今日はどうするの？まずは予定を教えて。"})
        session.modified = True

    return render_template("chat.html", history=session.get("chat_history"))


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
    # 予定参照（チャットで聞かれた場合）
    schedule_reply = handle_schedule_query(user_message)
    if schedule_reply is not None:
        session["chat_history"].append({"role": "assistant", "text": schedule_reply})
        session.modified = True
        return jsonify({"ok": True, "reply": schedule_reply})

    # 補完モードが優先
    completion_reply = handle_schedule_completion(user_message)
    if completion_reply is None:
        completion_reply = start_schedule_completion_if_needed()
    if completion_reply is not None:
        session["chat_history"].append({"role": "assistant", "text": completion_reply})
        session.modified = True
        return jsonify({"ok": True, "reply": completion_reply})

    reply = ask(user_message)
    session["chat_history"].append({"role": "assistant", "text": reply})
    session.modified = True

    return jsonify({"ok": True, "reply": reply})


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
            "deadline": form.get("deadline", ""),
            "duration_minutes": form.get("duration_minutes", ""),
            "location": form.get("location", ""),
            "notes": form.get("notes", ""),
            "created_at": datetime.now().isoformat(),
        }
        session["schedules"].append(item)
        session["schedule_completion"] = None
        session["schedule_completion_pending"] = True
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
            "deadline": form.get("deadline", ""),
            "duration_minutes": form.get("duration_minutes", ""),
            "location": form.get("location", ""),
            "notes": form.get("notes", ""),
            "created_at": schedules[index].get("created_at", datetime.now().isoformat()),
        }
        session["schedules"] = schedules
        session["schedule_completion"] = None
        session["schedule_completion_pending"] = True
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
