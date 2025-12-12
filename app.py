import json
import subprocess
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


def require_setup_or_redirect():
    if not is_setup_complete():
        return redirect(url_for("profile"))
    return None


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
        return "ごめん、今ちょっとつながらへんみたい。ollama が起動してるか確認してみて。"


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
        return redirect(url_for("start_page"))
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
        session["chat_history"].append({"role": "assistant", "text": "今日はどうするん？まず予定教えて。"})
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
