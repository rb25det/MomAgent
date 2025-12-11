# app.py

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

# builder.py を prompts パッケージから読む想定
# プロジェクト構成:
#   MomAgent/
#     app.py
#     prompts/
#       __init__.py
#       builder.py
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
app.secret_key = "your_secret_key_here"  # 適当な値に変えてOK


# =========================
# helpers（セッション・予定）
# =========================

def init_session():
    if "profile" not in session:
        session["profile"] = {}
    if "mom_settings" not in session:
        session["mom_settings"] = {}
    if "schedules" not in session:
        session["schedules"] = []  # list of dicts
    if "chat_history" not in session:
        session["chat_history"] = []  # [{'role':'assistant'|'user','text':...}, ...]
    if "model_ready" not in session:
        session["model_ready"] = False  # モデル生成済みかどうか


def clear_chat_history():
    """チャット履歴だけを消す（予定は消さない）"""
    session["chat_history"] = []
    session.modified = True


def sort_schedules_for_display(schedules):
    # priority(1高,2中,3低) -> then date/time
    def keyfn(s):
        pr = int(s.get("priority", "3"))
        date = s.get("date", "9999-12-31")
        time = s.get("time", "23:59")
        return (pr, date, time)
    return sorted(schedules, key=keyfn)


# =========================
# Ollama API 呼び出し（チャット用）
# =========================

def ask(prompt: str) -> str:
    """生成したお母さんモデルに問い合わせる"""
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": GENERATED_MODEL_NAME, "prompt": prompt, "stream": False},
            timeout=300,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()

    except requests.exceptions.HTTPError as e:
        print("LLM HTTPError:", e)
        return "ごめんね、今お母さん側のエラーみたいやわ。API やモデル名を確認してみて。"

    except requests.exceptions.RequestException as e:
        print("LLM RequestException:", e)
        return "ちょっとサーバにつながらへんみたいやわ。ollama が起動してるか確認してみて。"


# =========================
# Modelfile の生成
# =========================

def write_modelfile(config: dict):
    """builder.py によって組み立てた SYSTEM プロンプトを使って Modelfile を作成"""

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
#   profile.html + mom_settings.html を合体して config を作る
#   name / value は form.html に合わせてある
# =========================

def write_config_json(profile: dict, mom_form) -> dict:
    """
    プロフィール（session に入っている dict）と
    mom_settings.html から POST された form を合成して config dict を作る
    """

    # -------- ユーザ側 --------

    # active_time_slots, topic_weights は複数選択
    active_raw = profile.get("active_time_slots") or []
    if isinstance(active_raw, str):
        active_slots = [active_raw]
    else:
        active_slots = list(active_raw)

    topic_raw = profile.get("topic_weights") or []
    if isinstance(topic_raw, str):
        topics = [topic_raw]
    else:
        topics = list(topic_raw)

    # numeric 系
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

    # 朝ごはん頻度（0 / 1 / 2）
    breakfast_level = to_int_or_none(profile.get("breakfast_frequency"))

    # 運動習慣（週あたり回数）
    exercise_per_week = to_int_or_none(profile.get("exercise_frequency_per_week"))

    # -------- お母さんモデル側 --------

    # slider: strict_kind, quiet_talkative（すでに -1〜1 の値で飛んでくる想定）
    strict_kind = to_float_or_none(mom_form.get("strict_kind")) or 0.0
    quiet_talkative = to_float_or_none(mom_form.get("quiet_talkative")) or 0.0

    dialect_type = mom_form.get("dialect_type") or "normal"

    listen_styles = mom_form.getlist("listen_style")
    listen_deeply = 1.0 if "listen_deeply" in listen_styles else 0.0
    give_clear_advice = 1.0 if "give_clear_advice" in listen_styles else 0.0
    praise_a_lot = 1.0 if "praise_a_lot" in listen_styles else 0.0

    topic_initiation_frequency = to_float_or_none(
        mom_form.get("topic_initiation_frequency")
    ) or 0.5
    topic_weight_seriousness = to_float_or_none(
        mom_form.get("topic_weight_seriousness")
    ) or 0.5

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
                "active_time_slots": active_slots,
            },

            "health": {
                "breakfast_frequency_level": breakfast_level,
                "exercise_frequency_per_week": exercise_per_week,
            },

            # checkbox 群をそのまま weight=1.0 で辞書化
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

    # JSON として保存
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return config


# =========================
# routes
# =========================

@app.route("/")
def index():
    # ⭐ 起動時：セッションを初期化してチャット履歴だけリセット → プロフィールへ
    init_session()
    clear_chat_history()
    return redirect(url_for("profile"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    init_session()
    if request.method == "POST":
        # checkbox など複数値に対応するため getlist ベースで保存
        profile_data = {}
        for key in request.form.keys():
            vals = request.form.getlist(key)
            if len(vals) == 1:
                profile_data[key] = vals[0]
            else:
                profile_data[key] = vals
        session["profile"] = profile_data
        session["model_ready"] = False  # プロフィール変えたら再生成が必要
        session.modified = True
        return redirect(url_for("mom_settings_page"))
    return render_template("profile.html")


@app.route("/mom_settings", methods=["GET", "POST"])
def mom_settings_page():
    init_session()
    if request.method == "POST":
        # mom_settings も一応保存（ナビなどで使う場合用）
        mom_settings_data = {}
        for key in request.form.keys():
            vals = request.form.getlist(key)
            if len(vals) == 1:
                mom_settings_data[key] = vals[0]
            else:
                mom_settings_data[key] = vals
        session["mom_settings"] = mom_settings_data
        session["model_ready"] = False
        session.modified = True

        # プロフィールがない場合は戻す
        profile_data = session.get("profile") or {}
        if not profile_data:
            return redirect(url_for("profile"))

        # 1. JSON 作成
        config = write_config_json(profile_data, request.form)

        # 2. Modelfile 生成
        write_modelfile(config)

        # 3. Ollama モデル生成
        try:
            subprocess.run(
                ["ollama", "create", GENERATED_MODEL_NAME, "-f", str(MODELFILE_PATH)],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print("ollama create error:", e)
            session["model_ready"] = False
            session.modified = True
            return (
                "<p>モデル生成に失敗しました。`ollama create` のログを確認してください。</p>",
                500,
            )

        # 成功したらチャット履歴をリセットしてフラグ ON
        clear_chat_history()
        session["model_ready"] = True
        session.modified = True
        return redirect(url_for("chat_page"))

    return render_template("mom_settings.html")


@app.route("/chat", methods=["GET"])
def chat_page():
    init_session()
    # モデルがまだできていなければ mom_settings に飛ばす
    if not session.get("model_ready"):
        return redirect(url_for("mom_settings_page"))

    # 初回だけお母さんの第一声を入れる
    if not session.get("chat_history"):
        welcome = "今日はどうするん？まず予定教えて。"
        session["chat_history"].append({"role": "assistant", "text": welcome})
        session.modified = True

    return render_template("chat.html", history=session.get("chat_history"))


# -------------------------
# Chat API
# -------------------------

@app.route("/api/chat", methods=["POST"])
def api_chat():
    init_session()

    # モデルがまだならエラー返し（フロントでメッセージ表示用）
    if not session.get("model_ready"):
        return jsonify({"ok": False, "error": "model_not_ready"}), 400

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"ok": False, "error": "no_message"}), 400

    session["chat_history"].append({"role": "user", "text": user_message})

    reply = ask(user_message)

    session["chat_history"].append({"role": "assistant", "text": reply})
    session.modified = True

    return jsonify({"ok": True, "reply": reply, "history": session["chat_history"]})


# -------------------------
# schedule
# -------------------------

@app.route("/schedule_list")
def schedule_list():
    init_session()
    schedules = sort_schedules_for_display(session.get("schedules", []))
    return render_template("schedule_list.html", schedules=schedules)


@app.route("/schedule_add", methods=["GET", "POST"])
def schedule_add():
    init_session()
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
            "created_at": schedules[index].get(
                "created_at", datetime.now().isoformat()
            ),
        }
        session["schedules"] = schedules
        session.modified = True
        return redirect(url_for("schedule_list"))
    item = schedules[index]
    return render_template("schedule_edit.html", item=item, index=index)


@app.route("/schedule_delete/<int:index>", methods=["POST"])
def schedule_delete(index):
    init_session()
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

    # Flask のリローダー稼働時のみブラウザを開く
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.0, open_browser).start()

    # use_reloader=True（デフォルト）に戻すこと
    app.run(host="127.0.0.1", port=5000, debug=True)
