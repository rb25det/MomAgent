# app.py

from pathlib import Path
from datetime import datetime
import json
import subprocess

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

from prompts.builder import build_prompt

# =========================
# 基本設定（モデルまわり）
# =========================

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
GENERATED_MODEL_NAME = "elyza-mom"

CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "mom_config.json"

MODELFILE_PATH = Path("Modelfile")

# Flask
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # 適当な文字列に変えてOK


# =========================
# セッション / 予定ヘルパ
# =========================

def init_session():
    if "profile" not in session:
        session["profile"] = {}
    if "mom_settings" not in session:
        session["mom_settings"] = {}
    if "schedules" not in session:
        session["schedules"] = []  # list[dict]
    if "chat_history" not in session:
        session["chat_history"] = []  # [{'role':'assistant'|'user','text':...}, ...]
    if "model_ready" not in session:
        # モデルが生成済みかどうかのフラグ
        session["model_ready"] = False


def clear_chat_history():
    """チャット履歴だけを消す（予定は消さない）"""
    session["chat_history"] = []
    session.modified = True


def sort_schedules_for_display(schedules):
    """優先度→日付→時間の順でソート"""
    def keyfn(s):
        pr = int(s.get("priority", "3"))
        date = s.get("date", "9999-12-31")
        time = s.get("time", "23:59")
        return (pr, date, time)

    return sorted(schedules, key=keyfn)


# =========================
# Ollama API 呼び出し（チャット時）
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
#   profile.html + mom_settings.html をマージして config を作る
# =========================

def write_config_json(profile: dict, mom_form) -> dict:
    """
    プロフィール + お母さん設定 から config dict を生成し、mom_config.json に保存
    """

    # --- 生活リズム / アクティブ時間帯 ---
    active_raw = profile.get("active_time_slots") or []
    if isinstance(active_raw, str):
        active_slots = [active_raw]
    else:
        active_slots = active_raw

    # --- 話題の好み ---
    interest_raw = profile.get("interest_tags") or []
    if isinstance(interest_raw, str):
        interest_tags = [interest_raw]
    else:
        interest_tags = interest_raw

    topic_weights = {}
    # スライダー weight_就活 などがあればそれを使う
    for t in interest_tags:
        key = t
        w = profile.get(f"weight_{t}")
        try:
            topic_weights[key] = float(w) if w is not None else 0.5
        except ValueError:
            topic_weights[key] = 0.5

    # --- 朝食頻度（文字列 → 大まかな数値） ---
    bf = profile.get("breakfast_frequency")
    if bf == "ほぼ毎日":
        breakfast_level = 2
    elif bf == "たまに":
        breakfast_level = 1
    elif bf == "ほとんど食べない":
        breakfast_level = 0
    else:
        breakfast_level = None

    # --- 運動習慣（文字列 → 大まかな回数/週） ---
    ex = profile.get("exercise_frequency")
    if ex == "週3回以上":
        ex_per_week = 3
    elif ex == "週1〜2回":
        ex_per_week = 1.5
    elif ex == "週1回未満":
        ex_per_week = 0.5
    elif ex == "ほぼしない":
        ex_per_week = 0
    else:
        ex_per_week = None

    # --- お母さんの性格スライダーを -1〜1 に正規化 ---
    try:
        warmth = float(mom_form.get("warmth_level", 50))
    except ValueError:
        warmth = 50.0
    # 0(厳しい)〜100(優しい) → -1〜+1 にマッピング
    strict_kind = (warmth / 50.0) - 1.0

    try:
        talk = float(mom_form.get("talkativeness", 50))
    except ValueError:
        talk = 50.0
    quiet_talkative = (talk / 50.0) - 1.0

    # --- 方言 ---
    dialect_ui = mom_form.get("dialect", "standard")
    if dialect_ui == "kansai":
        dialect_type = "kansai"
    elif dialect_ui == "hakata":
        dialect_type = "hakata"
    else:
        dialect_type = "normal"

    # --- 相談スタイル（チェックボックス） ---
    listen_deeply = 1.0 if mom_form.get("style_listen") else 0.0
    give_clear_advice = 1.0 if mom_form.get("style_direct") else 0.0
    praise_a_lot = 1.0 if mom_form.get("style_praise") else 0.0

    # --- 話題を振る頻度 ---
    freq = mom_form.get("talk_frequency", "sometimes")
    if freq == "often":
        topic_initiation_frequency = 1.0
    elif freq == "rarely":
        topic_initiation_frequency = 0.1
    else:
        topic_initiation_frequency = 0.5

    # --- 話題の重さ ---
    heaviness = mom_form.get("topic_heaviness", "half")
    if heaviness == "light":
        topic_weight_seriousness = 0.2
    elif heaviness == "serious":
        topic_weight_seriousness = 0.8
    else:
        topic_weight_seriousness = 0.5

    config = {
        "user": {
            "nickname": profile.get("nickname"),
            "gender": profile.get("gender"),
            "age": int(profile["age"]) if profile.get("age") else None,
            "grade": profile.get("grade") or None,
            # occupation をそのまま role_status として使う
            "role_status": profile.get("occupation") or None,
            "life": {
                "wake_time_weekday": profile.get("wake_time_weekday"),
                "sleep_time_weekday": profile.get("sleep_time_weekday"),
                "wake_time_holiday": profile.get("wake_time_holiday"),
                "sleep_time_holiday": profile.get("sleep_time_holiday"),
                "average_sleep_hours": float(profile["average_sleep_hours"])
                if profile.get("average_sleep_hours")
                else None,
                "active_time_slots": active_slots,
            },
            "health": {
                "breakfast_frequency_level": breakfast_level,
                "exercise_frequency_per_week": ex_per_week,
            },
            "topic_weights": topic_weights,
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


# =========================
# ルーティング
# =========================

@app.route("/")
def index():
    # 起動時はチャット履歴だけリセットしてプロフィールへ
    init_session()
    clear_chat_history()
    # モデル準備フラグはそのまま（同じブラウザの再訪でも使えるように）
    return redirect(url_for("profile"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    """
    プロフィール入力画面（UIチームの profile.html）
    POST されたら session["profile"] に保存して /mom_settings へ。
    """
    init_session()
    if request.method == "POST":
        # 複数選択（active_time_slots, interest_tags）のため getlist を使う
        profile_data = {}
        for key in request.form.keys():
            values = request.form.getlist(key)
            if len(values) == 1:
                profile_data[key] = values[0]
            else:
                profile_data[key] = values
        session["profile"] = profile_data
        session.modified = True
        # プロフィールを更新したので、モデルはまだ再生成されていない扱いにする
        session["model_ready"] = False
        return redirect(url_for("mom_settings_page"))
    return render_template("profile.html")


@app.route("/mom_settings", methods=["GET", "POST"])
def mom_settings_page():
    """
    お母さんの性格設定画面（mom_settings.html）
    POST されたタイミングで:
      - JSON生成
      - Modelfile生成
      - ollama create
      を行い、成功したら model_ready=True にして /chat へ遷移。
    """
    init_session()
    if request.method == "POST":
        session["mom_settings"] = request.form.to_dict(flat=True)
        session.modified = True

        # いったん「まだ準備中」にしておく
        session["model_ready"] = False

        # 1. JSON 作成（profile + mom_settings）
        profile_data = session.get("profile", {})
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
            # モデル準備フラグは False のまま
            return (
                "<p>モデル生成に失敗しました。ollama create のログを確認してください。</p>",
                500,
            )

        # 成功したのでモデル準備完了
        session["model_ready"] = True

        # 新しい設定になったのでチャット履歴をクリア
        clear_chat_history()
        return redirect(url_for("chat_page"))

    return render_template("mom_settings.html")


@app.route("/chat", methods=["GET"])
def chat_page():
    """
    チャット画面（UIチームの chat.html）
    初回アクセス時だけ「今日はどうするん？まず予定教えて。」を履歴に入れる。
    モデル未生成のときは /mom_settings にリダイレクト。
    """
    init_session()
    if not session.get("model_ready"):
        # モデルがまだ出来ていない場合は設定画面へ戻す
        return redirect(url_for("mom_settings_page"))

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
    """
    chat.html から fetch されるAPI。
    UI側は {ok:true, reply:"..."} を期待している。
    """
    init_session()

    # モデルがまだ出来ていない場合はエラー返却（フロントで表示可）
    if not session.get("model_ready"):
        return jsonify({"ok": False, "error": "model_not_ready"}), 400

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"ok": False, "error": "no message"}), 400

    # 履歴に追加
    session["chat_history"].append({"role": "user", "text": user_message})

    # Ollama で返信
    reply = ask(user_message)

    session["chat_history"].append({"role": "assistant", "text": reply})
    session.modified = True

    return jsonify({"ok": True, "reply": reply, "history": session.get("chat_history")})


# -------------------------
# schedule 関連
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
# Dev only: 全セッションリセット
# -------------------------

@app.route("/reset_all")
def reset_all():
    session.clear()
    return "cleared"


# =========================
# エントリポイント
# =========================

if __name__ == "__main__":
    import os
    import webbrowser
    import threading

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")

    # リローダーの子プロセスではブラウザを開かないようにする
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.0, open_browser).start()

    app.run(host="127.0.0.1", port=5000, debug=True)
