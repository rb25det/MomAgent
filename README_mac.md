# Mom-Elyza: 日本のお母さんAI（ローカルLLM / Ollama × Llama-3-ELYZA-JP-8B）

このプロジェクトは、Mac 上で **完全ローカル**に動作する  
「日本のお母さんエージェント」を構築するためのセットアップ手順と実行方法をまとめたものです。

以下を明確に分けて説明しています：

1. **初回セットアップ手順（モデル導入〜mom-elyza 作成）**  
2. **2回目以降の運用（実行方法）**  
3. **システムプロンプト（お母さん性格）の書き換え方法**

---

# 📌 0. 前提

- Mac（M1/M2/M3）  
- Homebrew 導入済み  
- Python3 利用可  

---

# 🚀 1. 初回セットアップ（初めて mom-elyza を作る人）

このステップは **最初の一度だけ**行えばOK。

---

## 1-1. Ollama のインストール

```bash
brew install ollama
```

---

## 1-2. Ollama サーバ起動（別タブで常駐）

```bash
ollama serve
```

> このターミナルは起動しっぱなしで OK。  
> 推論はすべて **http://127.0.0.1:11434** に送られます。

---

## 1-3. 日本語モデル（ELYZA JP-8B）のダウンロード

別タブを開いて：

```bash
ollama pull dsasai/llama3-elyza-jp-8b
```

---

## 1-4. 作業ディレクトリ作成

```bash
mkdir -p ~/mom-elyza
cd ~/mom-elyza
```

---

## 1-5. Modelfile の作成（お母さんの性格設定）

`~/mom-elyza/Modelfile` を作成：

```
FROM dsasai/llama3-elyza-jp-8b

SYSTEM """
あなたは日本のお母さんです。

【性格 / 話し方】
- 優しく、ときどき厳しく、愛情が先に来る。
- 関西寄りの自然な口調も可。
- 長文にせず短く・要点を温かく。

【役割A：予定の聞き出し】
- 会話の最初は必ず「今日の予定」「締切」「所要時間」を聞く。
- 5〜15分でできる一歩を提示して背中を押す。

【役割B：耳の痛い話題】
- 就活 / 将来 / 生活リズム / 健康 / お金 から1つだけ触れる。

【反発への対応】
- まず短く共感 → やさしい提案 or 軽い叱咤 → 最後フォロー。

【禁止】
- 侮辱・人格否定
- 専門的な断定
- 長文の説教
"""

PARAMETER temperature 0.7
PARAMETER num_ctx 8192
```

---

## 1-6. お母さんモデルの作成（初回だけ）

```bash
ollama create elyza-mom -f Modelfile
```

成功すると：

```
success
```

---

## 1-7. Python チャットの準備

### 依存パッケージのインストール

```bash
python3 -m pip install --user requests
```

### chat_mom.py を作成（~/mom-elyza/chat_mom.py）

```python
import requests

URL = "http://127.0.0.1:11434/api/generate"
MODEL = "elyza-mom"

def ask(prompt: str) -> str:
    r = requests.post(URL, json={"model": MODEL, "prompt": prompt, "stream": False}, timeout=300)
    r.raise_for_status()
    return r.json().get("response", "").strip()

if __name__ == "__main__":
    print("お母さん> 今日はどうするん？ まず予定教えて。（exit で終了）")
    while True:
        q = input("あなた> ").strip()
        if q.lower() in {"exit", "quit"}:
            print("お母さん> ほなまたね。体こわさんようにね。")
            break
        print("お母さん>", ask(q))
```

---

# ▶️ 2. 2回目以降の運用（毎回やる操作）

---

## 2-1. Ollama サーバを起動（常駐）

```bash
ollama serve
```

---

## 2-2. Python チャットアプリを実行

```bash
python3 ~/mom-elyza/chat_mom.py
```

---

# ✏️ 3. システムプロンプト（お母さん性格）の書き換え方法

---

## 3-1. Modelfile を編集

```bash
cd ~/mom-elyza
nano Modelfile
```

---

## 3-2. 変更を反映する（再生成）

```bash
ollama create elyza-mom -f Modelfile
```

---

# 🎉 完了！

これで Elyza JP-8B をベースにした  
「ローカルお母さんAI」がいつでも再現できます。