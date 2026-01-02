# Mom-Elyza: 日本のお母さんAI（Windows 向けセットアップ / 完全ローカル）

このプロジェクトは **Windows 上で完全ローカルに動作する「日本のお母さんAI」** を構築する手順をまとめたものです。

- モデル：**Llama-3-ELYZA-JP-8B**（日本語特化）
- ランタイム：**Ollama（Windows 版）**
- 性格付け：**Modelfile の SYSTEM プロンプトで「日本の優しい関西のお母さん化」**
- 会話：Python CLI  
- ネット接続不要（モデル取得後）

---

## 7. Python チャット（依存と実行）

### 7.1 依存のインストール（推奨: 仮想環境）

PowerShell 例:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 7.2 実行方法

簡易 CLI と Flask サーバの両方を用意しています。用途に合わせて選んでください。

- 簡易 CLI:

```powershell
python chat_mom.py
```

- サーバ起動（開発・API 経由／ブラウザ利用）:

```powershell
python app.py
```

### 7.3 ログの確認

PowerShell でログを確認できます（`logs/` は `.gitignore` に追加済み）：

```powershell
Get-ChildItem $HOME\mom-elyza\logs
```

この手順では Ollama が事前に起動しており、モデルが利用可能であることを前提としています。Windows 版 Ollama がサービスとして常駐している場合はそのまま利用できますし、CLI で起動するなら `ollama serve` を実行してください。

### 7.1 依存のインストール

```powershell
pip install requests
```

### 7.2 `chat_mom.py` を作成

```python
import requests
from datetime import datetime
from pathlib import Path

API_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "elyza-mom"

def chat_mom(messages):
    res = requests.post(
        API_URL,
        json={"model": MODEL, "messages": messages, "stream": False},
        timeout=300
    )
    res.raise_for_status()
    return res.json()["message"]["content"].strip()

def create_log_file(base_dir: Path) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return base_dir / f"chat_{now}.txt"

def write_log(f, speaker: str, text: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    f.write(f"[{timestamp}] {speaker}> {text}\n")
    f.flush()

if __name__ == "__main__":
    print("お母さん> 今日はどうするん？ まず予定教えて。（exit で終了）")

    history = []
    logs_dir = Path.home() / "mom-elyza" / "logs"
    log_file_path = create_log_file(logs_dir)
    print(f"(ログ保存先: {log_file_path})")

    with log_file_path.open("a", encoding="utf-8") as log_f:
        write_log(log_f, "お母さん", "今日はどうするん？ まず予定教えて。（exit で終了）")

        while True:
            q = input("あなた> ").strip()
            if q.lower() in {"exit", "quit"}:
                farewell = "ほなまたね。体こわさんようにね。"
                print("お母さん>", farewell)
                write_log(log_f, "あなた", q)
                write_log(log_f, "お母さん", farewell)
                break

            history.append({"role": "user", "content": q})
            write_log(log_f, "あなた", q)

            try:
                reply = chat_mom(history)
            except Exception as e:
                err_msg = f"（エラー）Ollama が起動しているか確認してね：{e}"
                print(err_msg)
                write_log(log_f, "お母さん", err_msg)
                continue

            history.append({"role": "assistant", "content": reply})
            print("お母さん>", reply)
            write_log(log_f, "お母さん", reply)
```

---

# ▶️ 8. 実行方法

### 8.1 Ollama が起動している状態を確認
タスクトレイの Ollama アイコンが出ていればOK。

### 8.2 Python チャットを実行

```powershell
python $HOME\mom-elyza\chat_mom.py
```

---

# 📁 9. ログの確認

```powershell
Get-ChildItem $HOME\mom-elyza\logs
```

---

# 🎉 完了！

これで Windows 上でも **「日本のお母さんAI」** をローカルで動かすことができます。

- Modelfile を編集 → 性格調整  
- Python コードを拡張 → タスク管理や記憶  
- 今後、Notion やカレンダー連携も可能  
