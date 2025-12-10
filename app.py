# app.py

import json
import subprocess
from pathlib import Path

import requests
from flask import Flask, request, render_template, jsonify

# ← 追加：builder.py を読み込む
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

app = Flask(__name__, template_folder="templates")


# =========================
# Ollama API 呼び出し
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
# =========================

def write_config_json(form) -> dict:
    """フォーム内容を JSON に変換し、config/mom_config.json として保存"""

    active_slots = form.getlist("active_time_slots")
    topics = form.getlist("topic_weights")
    listen_styles = form.getlist("listen_style")

    config = {
        "user": {
            "nickname": form.get("nickname"),
            "gender": form.get("gender"),
            "age": int(form["age"]) if form.get("age") else None,
            "grade": form.get("grade") or None,
            "role_status": form.get("role_status") or None,

            "life": {
                "wake_time_weekday": form.get("wake_time_weekday"),
                "sleep_time_weekday": form.get("sleep_time_weekday"),
                "wake_time_holiday": form.get("wake_time_holiday"),
                "sleep_time_holiday": form.get("sleep_time_holiday"),
                "average_sleep_hours": float(form["average_sleep_hours"])
                if form.get("average_sleep_hours") else None,
                "active_time_slots": active_slots,
            },

            "health": {
                "breakfast_frequency_level": int(form["breakfast_frequency"])
                if form.get("breakfast_frequency") else None,
                "exercise_frequency_per_week": int(form["exercise_frequency_per_week"])
                if form.get("exercise_frequency_per_week") else None,
            },

            "topic_weights": {t: 1.0 for t in topics},
        },

        "mother_model": {
            "strict_kind": float(form["strict_kind"]) if form.get("strict_kind") else 0.0,
            "quiet_talkative": float(form["quiet_talkative"]) if form.get("quiet_talkative") else 0.0,
            "dialect_type": form.get("dialect_type") or "normal",
            "listen_deeply": 1.0 if "listen_deeply" in listen_styles else 0.0,
            "give_clear_advice": 1.0 if "give_clear_advice" in listen_styles else 0.0,
            "praise_a_lot": 1.0 if "praise_a_lot" in listen_styles else 0.0,
            "topic_initiation_frequency": float(form.get("topic_initiation_frequency") or 0.5),
            "topic_weight_seriousness": float(form.get("topic_weight_seriousness") or 0.5),
        },

        "generated_model_name": GENERATED_MODEL_NAME,
    }

    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return config


# =========================
# ルーティング
# =========================

@app.route("/", methods=["GET"])
def index():
    return render_template("form.html")


@app.route("/setup", methods=["POST"])
def setup():
    # 1. JSON 作成
    config = write_config_json(request.form)

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
        return "<p>モデル生成に失敗しました。ollama create のログを確認してください。</p>"

    return """
    <p>お母さんモデルの準備ができました！</p>
    <p><a href="/chat">チャットを始める</a></p>
    """


@app.route("/chat", methods=["GET"])
def chat_page():
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    message = data.get("message", "")
    resp = ask(message)
    return jsonify({"response": resp})


# =========================
# 自動でブラウザを開く設定（任意）
# =========================

if __name__ == "__main__":
    import os
    import webbrowser
    import threading

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000/")

    # ★ ここがポイント：リローダー本体プロセスのときだけ開く
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.0, open_browser).start()

    app.run(host="127.0.0.1", port=5000, debug=True)
