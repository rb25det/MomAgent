# Python App.py 応答なし問題の修正ガイド

## 🔴 問題の説明

ユーザが `python app.py` を実行してメッセージを送信した後、応答がない（ハング状態）という問題が発生していました。

## 🟢 原因と解決方法

### 問題の根本原因

1. **`rebuild_model()` 関数にタイムアウトがない**
   - Ollama の `ollama create` コマンド実行時に無期限に待機
   - `/mom_settings` エンドポイント設定時にハング

2. **`ask()` 関数のタイムアウトが長すぎる**
   - 300 秒（5分）は実用的ではない
   - ネットワーク遅延時にも影響

### 実装した修正

#### ✅ 修正 1: `rebuild_model()` 関数
- **追加**: `timeout=60` パラメータ
- **追加**: エラーハンドリング（try-except）
- **効果**: タイムアウト時も処理を続行

#### ✅ 修正 2: `ask()` 関数
- **変更**: `timeout=300` → `timeout=120`
- **追加**: `requests.exceptions.Timeout` の明示的なハンドリング
- **効果**: Timeout 時も親切なメッセージを返す

## 📝 修正内容の確認

### 変更ファイル: `app.py`

#### Line 105-137: `ask()` 関数
```python
# ✅ timeout=120 に変更
r = requests.post(
    OLLAMA_URL,
    json={"model": GENERATED_MODEL_NAME, "prompt": full_prompt, "stream": False},
    timeout=120,  # 修正: 300秒 → 120秒
)

# ✅ Timeout 例外を明示的にハンドリング
except requests.exceptions.Timeout:
    logging.error("LLM request timed out after 120 seconds")
    return "ごめん、回答に時間がかかってしまったわ。もう一度聞いてみてくれる？"
```

#### Line 247-275: `rebuild_model()` 関数
```python
# ✅ try-except ブロックを追加
try:
    subprocess.run(
        ["ollama", "create", GENERATED_MODEL_NAME, "-f", str(MODELFILE_PATH)],
        check=True,
        timeout=60,  # 修正: タイムアウト追加
    )
    logging.info(f"Model '{GENERATED_MODEL_NAME}' rebuilt successfully")
except subprocess.TimeoutExpired:
    logging.warning(f"Ollama model rebuild timed out after 60 seconds. Continuing anyway.")
except subprocess.CalledProcessError as e:
    logging.error(f"Ollama model rebuild failed: {e}")
except Exception as e:
    logging.error(f"Unexpected error during model rebuild: {e}")
```

## 🧪 テスト手順

### 前提条件

1. **Ollama が起動している**
   ```bash
   ollama serve
   ```

2. **Flask サーバーを起動**
   ```bash
   python app.py
   ```

### テストシナリオ

#### Step 1: プロフィール設定
```
1. ブラウザで http://127.0.0.1:5000 にアクセス
2. プロフィール情報を入力
3. 「次へ」をクリック
```

**期待される動作**: 即座に次のページ（お母さん設定）に移動

#### Step 2: お母さん設定
```
1. お母さんの性格設定を入力
2. 「完了」をクリック
```

**期待される動作**: 3-30秒以内に応答（rebuild_model の実行時間）

#### Step 3: チャット
```
1. チャットページに遷移
2. 以下の3つのメッセージをテスト
   - 「今週何か予定ある？」（予定問い合わせ）
   - 「最近どう？」（一般会話）
   - 「明日は？」（予定問い合わせ）
```

**期待される動作**: 各メッセージに 30 秒以内に応答

## 📊 パフォーマンス指標

修正後の応答時間の目安：

| エンドポイント | 処理 | 期待時間 |
|---|---|---|
| `/profile` (POST) | プロフィール保存 | < 1 秒 |
| `/mom_settings` (POST) | モデル再構築 | 3-30 秒（Ollama CREATE） |
| `/api/chat` | 予定問い合わせ | < 2 秒（ルール処理） |
| `/api/chat` | 一般会話 | < 30 秒（LLM処理） |

## 🐛 トラブルシューティング

### 問題: `/mom_settings` で 60 秒以上ハングする

**原因**: Ollama CREATE コマンドが 60 秒でタイムアウト

**対応**:
```bash
# Flask ログを確認
tail -50 /tmp/flask_startup.log

# Ollama の状態を確認
ollama list

# Ollama プロセスを再起動
pkill ollama
ollama serve
```

### 問題: `/api/chat` で「回答に時間がかかってしまった」メッセージが返される

**原因**: LLM 呼び出しが 120 秒以上かかった

**対応**:
```bash
# Ollama のログを確認
journalctl -u ollama -f  # systemd の場合

# GPU メモリ状態を確認（GPU使用時）
nvidia-smi

# タイムアウト値を増やす（必要に応じて）
# app.py の ask() 関数の timeout を調整
```

### 問題: 修正が適用されているか確認したい

**確認方法**:
```bash
# timeout パラメータが存在するか確認
grep "timeout=" app.py | head -5

# 出力例：
# Line 129:            timeout=120,  # 120秒でタイムアウト
# Line 269:            timeout=60,  # 60秒でタイムアウト
```

## 📚 関連ドキュメント

| ファイル | 内容 |
|---|---|
| [BUGFIX_SUMMARY.md](BUGFIX_SUMMARY.md) | 修正内容の要約 |
| [BUGFIX_DETAILED.md](BUGFIX_DETAILED.md) | 修正前後の詳細比較 |
| [IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md) | 全体実装サマリー |
| [DESIGN.md](docs/DESIGN.md) | アーキテクチャ設計 |

## ✅ チェックリスト

修正完了後、以下を確認してください：

- [ ] `app.py` の Line 129 に `timeout=120` がある
- [ ] `app.py` の Line 269 に `timeout=60` がある
- [ ] `ask()` 関数に `requests.exceptions.Timeout` のハンドリングがある
- [ ] `rebuild_model()` 関数が try-except で包まれている
- [ ] Ollama サーバーが起動している
- [ ] Flask サーバーが起動している
- [ ] `/mom_settings` で 60 秒以内に応答が返される
- [ ] `/api/chat` で 120 秒以内に応答が返される

---

**修正日**: 2026-01-02  
**修正バージョン**: app.py v2.1  
**テスト状況**: ✅ コード修正完了、動作テスト準備完了
