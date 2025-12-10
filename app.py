from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # 必要なら変えてね

# -------------------------
# helpers
# -------------------------
def init_session():
    if "profile" not in session:
        session["profile"] = {}
    if "mom_settings" not in session:
        session["mom_settings"] = {}
    if "schedules" not in session:
        session["schedules"] = []  # list of dicts
    if "chat_history" not in session:
        session["chat_history"] = []  # [{'role':'assistant'|'user','text':...}, ...]

def clear_chat_history():
    """チャット履歴だけを消す（予定は消さない）"""
    session["chat_history"] = []
    session.modified = True

def sort_schedules_for_display(schedules):
    # priority(1高,2中,3低) -> then date/time
    def keyfn(s):
        pr = int(s.get("priority","3"))
        date = s.get("date","9999-12-31")
        time = s.get("time","23:59")
        return (pr, date, time)
    return sorted(schedules, key=keyfn)

def generate_mom_reply(user_message):
    """簡易的なお母さん返信生成（デモ用）。本番はバック側でLLM呼ぶ想定"""
    profile = session.get("profile", {})
    name = profile.get("nickname") or profile.get("name") or "あんた"

    msg = user_message.strip().lower()

    if any(w in msg for w in ["登録", "予定登録", "予定を登録", "新しい予定"]):
        return "じゃあ、まずいつのどんな予定か教えて。例：2025-12-31 とか時間も。"
    if any(w in msg for w in ["確認", "予定確認", "見せて"]):
        schedules = session.get("schedules", [])
        if not schedules:
            return "いま登録されてる予定はないで。"
        sorted_s = sort_schedules_for_display(schedules)
        lines = []
        for i,s in enumerate(sorted_s, start=1):
            lines.append(f"{i}. {s['date']} {s['time']} — {s['content']}（優先度:{s['priority']}）")
        return "今の予定ね：\n" + "\n".join(lines[:10])
    if any(w in msg for w in ["削除", "消す", "予定削除"]):
        return "どの番号の予定を消す？番号で教えてね。"

    return f"{name}、そうなんやね。そしたらちょっとだけ手伝うわ。まずは一歩、5分でできることをやってみよか？"


# -------------------------
# routes
# -------------------------
@app.route("/")
def index():
    # ⭐ アプリを開いたら毎回チャット履歴だけ消す
    init_session()
    clear_chat_history()
    return redirect(url_for("profile"))

@app.route("/profile", methods=["GET", "POST"])
def profile():
    init_session()
    if request.method == "POST":
        profile_data = request.form.to_dict(flat=True)
        session["profile"] = profile_data
        session.modified = True
        return redirect(url_for("mom_settings_page"))
    return render_template("profile.html")

@app.route("/mom_settings", methods=["GET","POST"])
def mom_settings_page():
    init_session()
    if request.method == "POST":
        # ⭐ お母さん設定を保存した瞬間にチャット履歴を消す
        session["mom_settings"] = request.form.to_dict(flat=True)
        session.modified = True
        clear_chat_history()
        return redirect(url_for("chat_page"))
    return render_template("mom_settings.html")

@app.route("/chat", methods=["GET"])
def chat_page():
    init_session()
    # ⭐ 初回だけお母さんの第一声を入れる
    if not session.get("chat_history"):
        welcome = "今日はどうするん？まず予定教えて。"
        session["chat_history"].append({"role":"assistant","text":welcome})
        session.modified = True
    return render_template("chat.html", history=session.get("chat_history"))


# -------------------------
# schedule
# -------------------------
@app.route("/schedule_list")
def schedule_list():
    init_session()
    schedules = sort_schedules_for_display(session.get("schedules", []))
    return render_template("schedule_list.html", schedules=schedules)

@app.route("/schedule_add", methods=["GET","POST"])
def schedule_add():
    init_session()
    if request.method == "POST":
        form = request.form.to_dict(flat=True)
        item = {
            "date": form.get("date", ""),
            "time": form.get("time", ""),
            "content": form.get("content", ""),
            "priority": form.get("priority", "3"),
            "remind_value": form.get("remind_value",""),
            "remind_unit": form.get("remind_unit","hours"),
            "created_at": datetime.now().isoformat()
        }
        session["schedules"].append(item)
        session.modified = True
        return redirect(url_for("schedule_list"))
    return render_template("schedule_add.html")

@app.route("/schedule_edit/<int:index>", methods=["GET","POST"])
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
            "remind_value": form.get("remind_value",""),
            "remind_unit": form.get("remind_unit","hours"),
            "created_at": schedules[index].get("created_at", datetime.now().isoformat())
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
# Chat API
# -------------------------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    init_session()
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"ok": False, "error": "no message"}), 400

    session["chat_history"].append({"role":"user","text":user_message})
    reply = generate_mom_reply(user_message)
    session["chat_history"].append({"role":"assistant","text":reply})
    session.modified = True

    return jsonify({"ok": True, "reply": reply, "history": session["chat_history"]})


# -------------------------
# Dev only
# -------------------------
@app.route("/reset_all")
def reset_all():
    session.clear()
    return "cleared"


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
