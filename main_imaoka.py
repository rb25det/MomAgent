import sys
import json
from pathlib import Path

# chat_mom.py をインポート
try:
    import chat_mom
except ImportError:
    print("エラー: 'chat_mom.py' が見つかりません。同じフォルダに配置してください。")
    sys.exit(1)

from schedule_manager import ScheduleManager

# --- 予定をJSONファイルに蓄積する関数 ---
def save_schedule_to_file(schedule_data):
    """予定データを schedules.json に追記保存する"""
    base_dir = Path.home() / "mom-elyza"
    base_dir.mkdir(parents=True, exist_ok=True)
    file_path = base_dir / "schedules.json"
    
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                current_list = json.load(f)
            except json.JSONDecodeError:
                current_list = []
    else:
        current_list = []

    current_list.append(schedule_data)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(current_list, f, ensure_ascii=False, indent=4)
    print(f"\n★ 保存成功！ファイルの場所:\n{file_path.absolute()}\n")

# ---------------------------------------------------

def main():
    print("=== お母さんAI 起動 ===")
    print("お母さん> 今日の予定、なんかあるん？ (exit で終了)")

    scheduler = ScheduleManager()
    state = None
    history = []

    logs_dir = Path.home() / "mom-elyza" / "logs"
    log_file_path = chat_mom.create_log_file(logs_dir)
    print(f"(会話ログ保存先: {log_file_path})\n")

    with log_file_path.open("a", encoding="utf-8") as log_f:
        chat_mom.write_log(log_f, "お母さん", "今日の予定、なんかあるん？ (exit で終了)")

        while True:
            try:
                user_input = input("\nあなた> ").strip()
            except KeyboardInterrupt:
                break
                
            if user_input.lower() in ["exit", "quit"]:
                farewell = "ほな、またあとでね。"
                print(f"お母さん> {farewell}")
                chat_mom.write_log(log_f, "あなた", user_input)
                chat_mom.write_log(log_f, "お母さん", farewell)
                break

            chat_mom.write_log(log_f, "あなた", user_input)

            # --- 予定管理ロジック ---
            keywords = [
                "予定", "スケジュール", "約束", "登録", 
                "バイト", "仕事", "会議", "出張", "学校", "授業", "テスト",
                "デート", "遊び", "飲み", "ご飯", "病院", "美容院",
                "行く", "ある", "なし"
            ]
            is_schedule_intent = any(w in user_input for w in keywords)
            
            instruction = ""

            if state is not None or is_schedule_intent:
                state = scheduler.extract_and_update(user_input, state)
                
                # デバッグ表示（認識状態を確認）
                print(f"   (AI認識中: {json.dumps(state, ensure_ascii=False)})")

                status, sys_instruction = scheduler.get_next_action(state)
                
                if sys_instruction:
                    instruction = sys_instruction

                if status == "complete":
                    chat_mom.write_log(log_f, "system", f"【予定登録完了】{state}")
                    save_schedule_to_file(state)
                    state = None

            # --- AI対話処理 ---
            
            # 1. まずユーザーの入力を履歴に追加
            history.append({"role": "user", "content": user_input})
            
            # 2. 送信用のメッセージリストを作成（直近5ターン）
            # deepcopyしないとhistory自体が書き換わってしまうため注意（簡易的にスライスで対応）
            messages_to_send = [msg.copy() for msg in history[-5:]]

            # 3. ★修正点: 指示がある場合、直前のユーザーメッセージの中に埋め込む
            # （Systemメッセージとして分けると、Llama3が混乱して無言になるのを防ぐため）
            if instruction:
                last_msg = messages_to_send[-1]
                if last_msg['role'] == 'user':
                    # ユーザーの発言の後に、改行してシステム指示をくっつける
                    last_msg['content'] = f"{last_msg['content']}\n\n{instruction}"
                else:
                    # 万が一ユーザー発言じゃない場合は、従来通りappend
                    messages_to_send.append({"role": "system", "content": instruction})

            try:
                reply = chat_mom.chat_mom(messages_to_send)
                print(f"お母さん> {reply}")
                chat_mom.write_log(log_f, "お母さん", reply)
                history.append({"role": "assistant", "content": reply})

            except Exception as e:
                err_msg = f"（エラー）応答できませんでした... {e}"
                print(err_msg)
                chat_mom.write_log(log_f, "system", err_msg)

if __name__ == "__main__":
    main()
