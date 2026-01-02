# Bug Fix Summary - App.py 応答なしの問題修正

## 問題の概要

ユーザが `python app.py` を実行してメッセージを送信後、返答がない（ハング状態）という問題が発生していました。

## 原因分析

### 1. **rebuild_model() のタイムアウトなし問題（主原因）**
   - `subprocess.run()` で Ollama の `ollama create` コマンドを実行する際に、**タイムアウトが設定されていなかった**
   - Ollama でモデル再構築に時間がかかる場合（特に大きなモデル）、Flask プロセスが永遠に待機状態になった
   - これによって `/mom_settings` エンドポイントがハングしていた

### 2. **ask() 関数のタイムアウト不足**
   - Ollama API 呼び出しのタイムアウトが 300 秒（5 分）だった
   - ネットワーク遅延やサーバー負荷時にハングの原因になる可能性

## 実装した修正

### 修正 1: `rebuild_model()` 関数（app.py 行 247-275）

```python
def rebuild_model(profile_data: dict, mom_settings_data: dict) -> None:
    """プロフィール・お母さん設定からカスタムモデルを再構築。
    
    Ollama CREATE コマンドに 60 秒のタイムアウトを設定。
    タイムアウトやエラーが発生した場合はログ出力して処理を続行。
    """
    # ... 設定処理 ...
    
    try:
        subprocess.run(
            ["ollama", "create", GENERATED_MODEL_NAME, "-f", str(MODELFILE_PATH)],
            check=True,
            timeout=60,  # ✅ 60 秒でタイムアウト設定
        )
        logging.info(f"Model '{GENERATED_MODEL_NAME}' rebuilt successfully")
    except subprocess.TimeoutExpired:
        logging.warning(f"Ollama model rebuild timed out after 60 seconds. Continuing anyway.")
        # タイムアウトしても処理は継続（既存モデルを使用）
    except subprocess.CalledProcessError as e:
        logging.error(f"Ollama model rebuild failed: {e}")
        # エラーが発生しても処理は継続
    except Exception as e:
        logging.error(f"Unexpected error during model rebuild: {e}")
```

**変更点：**
- `timeout=60` を追加：Ollama CREATE コマンドを 60 秒でタイムアウト
- タイムアウト時のエラーハンドリング：例外をキャッチして処理を継続
- ログ記録：成功時と失敗時の両方をログに記録

### 修正 2: `ask()` 関数（app.py 行 105-137）

```python
def ask(prompt: str, system_prompt_amendment: str = "") -> str:
    """
    LLMに質問を投げて回答を得る。
    ...
    """
    try:
        if system_prompt_amendment:
            full_prompt = system_prompt_amendment + "\n\n" + prompt
        else:
            full_prompt = prompt
        
        logging.debug(f"Calling Ollama with model='{GENERATED_MODEL_NAME}', prompt length={len(full_prompt)}")
        
        r = requests.post(
            OLLAMA_URL,
            json={"model": GENERATED_MODEL_NAME, "prompt": full_prompt, "stream": False},
            timeout=120,  # ✅ 300 秒 → 120 秒に短縮
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        logging.debug(f"LLM response length: {len(response)}")
        return response
    except requests.exceptions.Timeout:
        # ✅ Timeout 例外の明示的なハンドリング
        logging.error("LLM request timed out after 120 seconds")
        return "ごめん、回答に時間がかかってしまったわ。もう一度聞いてみてくれる？"
    except requests.exceptions.RequestException as e:
        logging.error(f"LLM error: {e}")
        return "ごめん、接続がうまくいかないみたい。ollama が起動しているか確認してみて。"
```

**変更点：**
- `timeout=120`：Ollama API 呼び出しを 120 秒（2 分）でタイムアウト
- `requests.exceptions.Timeout` の明示的なハンドリング
- ログ出力レベルの改善：デバッグログで詳細情報を記録

## 効果

| 項目 | 修正前 | 修正後 |
|------|--------|--------|
| rebuild_model タイムアウト | なし（無限待機） | 60 秒 |
| ask() タイムアウト | 300 秒 | 120 秒 |
| ハング状態時の対応 | 応答なし | ユーザにフレンドリーなエラーメッセージ |
| ログ記録 | 最小限 | タイムアウト時も記録 |
| エラー耐性 | 低い | 高い（タイムアウト時も処理継続） |

## テストの進め方

修正後、以下の手順でテストしてください：

```bash
# 1. Flask サーバー起動
python app.py

# 2. ブラウザで http://127.0.0.1:5000 にアクセス

# 3. 以下の順序で操作
#    - プロフィール設定 → お母さん設定 → チャット

# 4. 以下のメッセージでテスト
#    - 「今週何か予定ある？」（予定問い合わせ）
#    - 「最近どう？」（一般会話）
#    - 「明日は？」（予定問い合わせ）

# 5. ログを確認
tail -f logs/classifier_events.log
```

## 注意事項

- **Ollama が起動していること** が前提条件です：
  ```bash
  ollama serve  # 別ターミナルで実行
  ```

- **モデル `elyza-mom` が作成されていること** を確認：
  ```bash
  ollama list  # elyza-mom が表示されることを確認
  ```

- タイムアウト値（60秒、120秒）は環境に応じて調整可能です

## 関連ファイル

- [app.py](app.py) - Flask アプリケーション（修正済み）
- [classifier.py](classifier.py) - スケジュール判定器
- [IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md) - 実装の詳細
