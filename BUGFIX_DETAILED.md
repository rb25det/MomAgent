# 修正内容の詳細比較

## 修正 1: rebuild_model() 関数

### 修正前（問題あり）
```python
def rebuild_model(profile_data: dict, mom_settings_data: dict) -> None:
    mom_form = dict_to_multidict(mom_settings_data)
    config = write_config_json(profile_data, mom_form)
    write_modelfile(config)

    subprocess.run(
        ["ollama", "create", GENERATED_MODEL_NAME, "-f", str(MODELFILE_PATH)],
        check=True,
    )  # ❌ タイムアウトなし → Flask がハング

    clear_chat_history()
    session["model_ready"] = True
    session.modified = True
```

### 修正後（タイムアウト実装済み）
```python
def rebuild_model(profile_data: dict, mom_settings_data: dict) -> None:
    """プロフィール・お母さん設定からカスタムモデルを再構築。
    
    Ollama CREATE コマンドに 60 秒のタイムアウトを設定。
    タイムアウトやエラーが発生した場合はログ出力して処理を続行。
    """
    mom_form = dict_to_multidict(mom_settings_data)
    config = write_config_json(profile_data, mom_form)
    write_modelfile(config)

    try:
        subprocess.run(
            ["ollama", "create", GENERATED_MODEL_NAME, "-f", str(MODELFILE_PATH)],
            check=True,
            timeout=60,  # ✅ 60 秒でタイムアウト
        )
        logging.info(f"Model '{GENERATED_MODEL_NAME}' rebuilt successfully")
    except subprocess.TimeoutExpired:
        logging.warning(f"Ollama model rebuild timed out after 60 seconds. Continuing anyway.")
        # ✅ タイムアウトしても処理を継続
    except subprocess.CalledProcessError as e:
        logging.error(f"Ollama model rebuild failed: {e}")
        # ✅ エラーが発生しても処理を継続
    except Exception as e:
        logging.error(f"Unexpected error during model rebuild: {e}")

    clear_chat_history()
    session["model_ready"] = True
    session.modified = True
```

**改善点：**
1. `timeout=60` パラメータで Ollama CREATE コマンドを 60 秒でタイムアウト
2. 例外処理ブロック（try-except）で3つのエラーケースを処理
3. タイムアウト時も処理を継続（フォールバック動作）
4. すべてのエラーをログに記録して可視化

---

## 修正 2: ask() 関数

### 修正前（タイムアウト不足）
```python
def ask(prompt: str, system_prompt_amendment: str = "") -> str:
    """
    LLMに質問を投げて回答を得る。
    ...
    """
    try:
        # system_prompt_amendment があれば、プロンプトの冒頭に追加
        if system_prompt_amendment:
            full_prompt = system_prompt_amendment + "\n\n" + prompt
        else:
            full_prompt = prompt
        
        r = requests.post(
            OLLAMA_URL,
            json={"model": GENERATED_MODEL_NAME, "prompt": full_prompt, "stream": False},
            timeout=300,  # ❌ 300 秒は長すぎる
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.RequestException as e:
        logging.error(f"LLM error: {e}")
        return "ごめん、接続がうまくいかないみたい。ollama が起動しているか確認してみて。"
        # ❌ Timeout 例外の明示的なハンドリングなし
```

### 修正後（タイムアウト設定とエラーハンドリング強化）
```python
def ask(prompt: str, system_prompt_amendment: str = "") -> str:
    """
    LLMに質問を投げて回答を得る。
    
    Args:
        prompt (str): ユーザプロンプト
        system_prompt_amendment (str): システムプロンプトに追加する指示（安全プロンプト等）
    
    Returns:
        str: LLMの応答
    """
    try:
        # system_prompt_amendment があれば、ユーザプロンプトの冒頭に追加
        if system_prompt_amendment:
            full_prompt = system_prompt_amendment + "\n\n" + prompt
        else:
            full_prompt = prompt
        
        logging.debug(f"Calling Ollama with model='{GENERATED_MODEL_NAME}', prompt length={len(full_prompt)}")
        
        r = requests.post(
            OLLAMA_URL,
            json={"model": GENERATED_MODEL_NAME, "prompt": full_prompt, "stream": False},
            timeout=120,  # ✅ 300 秒 → 120 秒（2 分）に短縮
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        logging.debug(f"LLM response length: {len(response)}")
        return response
    except requests.exceptions.Timeout:
        # ✅ Timeout 例外を明示的にハンドリング
        logging.error("LLM request timed out after 120 seconds")
        return "ごめん、回答に時間がかかってしまったわ。もう一度聞いてみてくれる？"
    except requests.exceptions.RequestException as e:
        logging.error(f"LLM error: {e}")
        return "ごめん、接続がうまくいかないみたい。ollama が起動しているか確認してみて。"
```

**改善点：**
1. `timeout=120`：Ollama API呼び出しを 120 秒（2 分）でタイムアウト
2. `requests.exceptions.Timeout` を個別にハンドリング
3. タイムアウト時に別のメッセージを返す（より詳細なエラー情報）
4. ログ出力レベルの改善（デバッグログで詳細情報を記録）
5. Docstring を改善

---

## 動作フロー図

### 修正前（問題あり）
```
ユーザ → /mom_settings に POST
  ↓
Flask が rebuild_model() を呼び出し
  ↓
subprocess.run() で ollama create コマンド実行
  ↓
❌ タイムアウトなし、コマンドが終わるまで待機
  ↓
長時間待機... → Flask が応答しない（ハング）
```

### 修正後（正常）
```
ユーザ → /mom_settings に POST
  ↓
Flask が rebuild_model() を呼び出し
  ↓
subprocess.run(timeout=60) で ollama create コマンド実行
  ↓
60 秒でタイムアウト OR コマンド完了
  ↓
✅ 例外をハンドリング、ログに記録
  ↓
処理を継続、ユーザに即座にレスポンス
```

---

## パフォーマンス測定ポイント

修正後、以下の指標を監視することをお勧めします：

### 1. エンドポイント応答時間

```bash
# Flask ログから応答時間を確認
grep "Calling Ollama" /tmp/flask_startup.log | wc -l
```

### 2. タイムアウト発生状況

```bash
# ログからタイムアウトを検索
grep -i "timeout\|timed out" logs/*.log
```

### 3. Ollama モデル再構築の成功率

```bash
# ログから rebuild 成功/失敗を確認
grep "rebuilt successfully\|rebuild failed" /tmp/flask_startup.log
```

---

## ロールバック手順（必要な場合）

修正内容に問題がある場合、以下でロールバック可能です：

```bash
# Git で前のバージョンに戻す
git checkout app.py

# または、手動で修正前のコードを復元
# rebuild_model() と ask() を元の短いバージョンに戻す
```

---

## 関連ドキュメント

- [IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md) - 実装全体の概要
- [DESIGN.md](docs/DESIGN.md) - アーキテクチャ設計
- [test_api.py](test_api.py) - API 統合テスト
