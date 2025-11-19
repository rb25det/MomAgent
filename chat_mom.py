import requests
from datetime import datetime
from pathlib import Path

API_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "elyza-mom"

def chat_mom(messages):
    """
    messages: [{"role": "user" or "assistant", "content": "..."}, ...]
    をまとめて /api/chat に投げる
    """
    res = requests.post(
        API_URL,
        json={
            "model": MODEL,
            "messages": messages,
            "stream": False,
        },
        timeout=300,
    )
    res.raise_for_status()
    data = res.json()
    # Ollama chat API のレスポンス形式:
    # { "message": { "role": "...", "content": "..." }, ... }
    return data["message"]["content"].strip()

def create_log_file(base_dir: Path) -> Path:
    """
    ログファイルを作成し、その Path を返す。
    ファイル名: chat_YYYY-MM-DD_HHMMSS.txt
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_path = base_dir / f"chat_{now}.txt"
    return log_path

def write_log(f, speaker: str, text: str):
    """
    ログファイルに1行書き込む。
    speaker: "あなた" or "お母さん"
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"[{timestamp}] {speaker}> {text}\n")
    f.flush()  # 念のため逐次書き出す

if __name__ == "__main__":
    print("お母さん> 今日はどうするん？ まず予定教えて。（exit で終了）")

    # 会話履歴（LLM用）
    history = []

    # ログファイル準備
    logs_dir = Path.home() / "mom-elyza" / "logs"
    log_file_path = create_log_file(logs_dir)
    print(f"(ログ保存先: {log_file_path})")

    with log_file_path.open("a", encoding="utf-8") as log_f:
        # 最初の一言もログに残しておく
        write_log(log_f, "お母さん", "今日はどうするん？ まず予定教えて。（exit で終了）")

        while True:
            q = input("あなた> ").strip()
            if q.lower() in {"exit", "quit"}:
                farewell = "ほなまたね。体こわさんようにね。"
                print("お母さん>", farewell)
                write_log(log_f, "あなた", q)
                write_log(log_f, "お母さん", farewell)
                break

            # ユーザ発言を履歴＆ログに追加
            history.append({"role": "user", "content": q})
            write_log(log_f, "あなた", q)

            try:
                reply = chat_mom(history)
            except Exception as e:
                err_msg = f"（エラー）Ollama が起動しているか確認してね：{e}"
                print(err_msg)
                write_log(log_f, "お母さん", err_msg)
                # エラー時に履歴を戻したい場合は history.pop() してもよい
                continue

            # モデル返答を履歴＆ログに追加
            history.append({"role": "assistant", "content": reply})
            print("お母さん>", reply)
            write_log(log_f, "お母さん", reply)
