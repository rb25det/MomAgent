# Mom-Elyza: 日本のお母さんAI（Windows 向けセットアップ / 完全ローカル）

このプロジェクトは **Windows 上で完全ローカルに動作する「日本のお母さんAI」** を構築する手順をまとめたものです。

- モデル：**Llama-3-ELYZA-JP-8B**（日本語特化）
- ランタイム：**Ollama（Windows 版）**
- 性格付け：**Modelfile の SYSTEM プロンプトで「日本の優しい関西のお母さん化」**
- 会話：Python CLI  
- ネット接続不要（モデル取得後）

---

# 🚀 1. 前提：Windows に Ollama をインストールする

### 1.1 Ollama の Windows 版をダウンロード
公式ページからインストーラを取得：

👉 https://ollama.com/download

### 1.2 インストール後、自動で Ollama サーバが起動する
タスクトレイに Ollama が起動していればOK。

### 1.3 動作確認
PowerShell で：

```powershell
ollama --version
```

---

# 📥 2. モデル（Llama-3-ELYZA-JP-8B）をダウンロード

PowerShell を開き、次を実行：

```powershell
ollama pull dsasai/llama3-elyza-jp-8b
```

動作確認：

```powershell
ollama run dsasai/llama3-elyza-jp-8b
```

---

# 🗂 3. 作業ディレクトリの作成

```powershell
mkdir $HOME\mom-elyza
cd $HOME\mom-elyza
```

---

# 🧩 4. Modelfile（お母さん性格定義）を作成

```
FROM dsasai/llama3-elyza-jp-8b

SYSTEM """
あなたは日本の優しいお母さんです。
関西寄りの話し方で、少し口うるさいけど愛情深く、
ユーザーに「予定の催促」「就活など耳の痛い話題の提示」を行います。

【口調の例】
- 「あんた今日の予定どうなってるん？」
- 「ちゃんと将来考えてるん？お母さん心配やわ」
- 「はよやりや～」
- 「うるさいな、は言わんの！」
など。

【会話方針】
1. ユーザーの予定を聞き出す
2. 進捗を促す
3. 就活・勉強など大事な話題も出す
4. やさしく見守りつつ、ちょっと小言を言う
"""

PARAMETER temperature 0.7
PARAMETER num_ctx 8192
```

---

# 🏗 5. お母さんモデルの作成（派生モデル）

```powershell
ollama create elyza-mom -f Modelfile
```

生成されたか確認：

```powershell
ollama list
```

---

# 💬 6. テスト実行（会話テスト）

```powershell
ollama run elyza-mom
```

---

# 🐍 7. Python チャット（/api/chat による会話＋ログ保存）

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
