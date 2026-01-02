# 実装サマリー：お母さんAI 予定応答機能（判定器導入版）

**実装完了日**: 2026-01-02  
**ステータス**: ✅ 完了  
**テスト合格率**: 24/24 (100%)

---

## 概要

要件定義・詳細設計に基づき、**ユーザ発話の意図判定器**と**ルールベース＋LLMハイブリッド処理**を実装しました。

予定問い合わせを**正規表現（軽量）+ LLM分類器（高精度）**で判定し、以下の処理を実現：
- 予定問い合わせ → ルール処理（登録済み予定のみから応答）
- その他 → LLM処理（安全プロンプト付き）

---

## 実装ファイル一覧

| ファイル | 行数 | 役割 |
|---------|------|------|
| [classifier.py](classifier.py) | 550+ | 判定器・補助機能のメインモジュール |
| [app.py](app.py) | 600+ | Flask アプリケーション（API統合） |
| [test_classifier.py](test_classifier.py) | 350+ | ユニットテスト（判定器機能） |
| [test_api.py](test_api.py) | 300+ | 統合テスト（API フロー） |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | 900+ | 要件定義書 |
| [docs/DESIGN.md](docs/DESIGN.md) | 1000+ | 詳細設計書 |
| [docs/TEST_CASES.md](docs/TEST_CASES.md) | 700+ | テストケース・受け入れ基準 |

---

## 実装内容詳細

### 1. 判定器モジュール (`classifier.py`)

#### 機能

**ハイブリッド判定アプローチ**:
```
入力: ユーザ発話
   ↓
[Step 1] ルールベース判定（_quick_filter）
   - 正規表現で明確な肯定/否定を即座に判定
   - 処理時間: 1ms以下
   - 信頼度: 0.9以上なら確定
   ↓
[Step 2] 必要に応じてLLM判定（_classify_with_llm）
   - グレーゾーン（信頼度 0.5～0.9）の場合のみLLMを呼び出し
   - タイムアウト: 3秒
   ↓
[Step 3] 信頼度統合（_adjust_confidence）
   - 正規表現とLLMの結果を加重平均
   ↓
出力: intent, scope, confidence, date_range等
```

**実装関数**:

| 関数名 | 入力 | 出力 | 特徴 |
|--------|------|------|------|
| `classify_schedule_intent()` | テキスト | 分類結果辞書 | メイン関数。日付範囲も計算 |
| `_quick_filter()` | テキスト | (bool, float) | 軽量ルールベース判定 |
| `_classify_with_llm()` | テキスト | 判定辞書 | LLMベース分類（グレーゾーン用） |
| `_infer_scope_from_text()` | テキスト | scope文字列 | スコープを発話から推定 |
| `_adjust_confidence()` | 2つの信頼度 | 統合信頼度 | 信頼度の加重平均 |
| `compute_date_range()` | scope文字列 | (date, date) | スコープを日付範囲に変換 |
| `log_event()` | 各種パラメータ | None | JSON Lines形式でログ記録 |
| `analyze_classifier_log()` | ログファイルパス | 統計辞書 | ログを集計・分析 |

**判定精度**:
- 肯定例（「今日の予定は？」等）: confidence >= 0.85
- 否定例（「予定が立て込んでる」等）: confidence >= 0.85
- グレーゾーン（「予定ってある？」等）: 0.5 < confidence < 0.8 → LLMへ

**スコープ判定**:
```
"今日" → "today"
"明日" → "tomorrow"
"今週/来週" → "week"
"今月/来月" → "month"
"次/直近" → "next" or "upcoming"
（その他） → "unspecified"
```

**日付範囲計算** (日本仕様：週は月曜始まり):
```
"today" → (本日, 本日)
"tomorrow" → (翌日, 翌日)
"week" → (月曜, 日曜)
"month" → (1日, 末日)
"next/upcoming" → None
```

#### ログ機構

**ログスキーマ** (JSON Lines形式):
```json
{
  "timestamp": "2026-01-02T12:00:00Z",
  "event_type": "schedule_classification",
  "user_message": "ユーザの発話",
  "classifier_intent": "schedule_query",
  "classifier_scope": "today",
  "classifier_confidence": 0.95,
  "classifier_reasoning": "判定の根拠",
  "chosen_path": "rule-based",
  "reply_text": "システムの返信",
  "processing_time_ms": 45.3,
  "error": null
}
```

**ログ保存先**: `logs/classifier_events.log`

### 2. Flask アプリケーション統合 (`app.py`)

#### 修正内容

**既存関数の改良**:

```python
def ask(prompt: str, system_prompt_amendment: str = "") -> str:
    """
    改良内容:
    - system_prompt_amendment パラメータを追加
    - 安全プロンプト（予定事実生成禁止）をLLMに付与可能
    """
```

**新規API フロー** (`/api/chat`):

```
POST /api/chat
  ↓
[Phase 1] Classification
  - classify_schedule_intent() を呼び出し
  - intent, scope, confidence を取得
  ↓
[Phase 2] Routing Decision
  - if intent == "schedule_query" && confidence >= 0.80:
      → rule-based処理へ
    else:
      → LLM処理（安全プロンプト付き）
  ↓
[Phase 3] Processing
  - rule: _handle_schedule_query_with_judgment()
         → 登録済み予定から応答
  - LLM: ask(..., system_prompt_amendment=SAFETY)
         → 安全プロンプト付きで応答
  ↓
[Phase 4] Logging
  - log_event() でイベント記録
  ↓
Response: {"ok": true, "reply": "応答テキスト"}
```

**新規補助関数**:

| 関数名 | 目的 |
|--------|------|
| `_handle_schedule_query_with_judgment()` | 判定器結果を基に予定問い合わせを処理 |
| `_is_schedule_in_range()` | 予定が日付範囲内か判定 |
| `_schedule_start_dt()` | 予定の開始日時を datetime で返す |
| `_pick_next_schedule()` | 次の1件の予定を取得 |
| `_format_schedule_list()` | 予定リストを見やすく整形 |
| `_scope_to_label()` | スコープを日本語ラベルに変換 |

**安全プロンプト例**:
```
重要な指示: ユーザが予定やスケジュールについて聞いても、
具体的な予定の事実（日時、内容、場所など）を述べないこと。
代わりに『予定の詳細については予定管理画面を確認してください』と案内すること。
```

#### エラーハンドリング

| 場面 | 対応 |
|------|------|
| 分類器タイムアウト（>3秒） | LLMへ自動フォールバック、warning ログ |
| 分類器一般エラー | LLMへフォールバック、error ログ |
| ログ書き込みエラー | エラーログのみ出力、処理は継続 |
| 予定がない | 「予定がまだ入ってない」と応答 |
| 範囲内に予定がない | 「その期間の予定は入ってない」と応答 |

### 3. テストスイート

#### ユニットテスト (`test_classifier.py`)

**24テスト、全合格**:

| テストクラス | テスト数 | カバー範囲 |
|-------------|---------|-----------|
| `TestQuickFilter` | 7 | ルールベース判定（肯定/否定/グレーゾーン） |
| `TestComputeDateRange` | 8 | 日付範囲計算（全スコープ） |
| `TestClassifyScheduleIntent` | 4 | メイン分類関数 |
| `TestLogging` | 2 | ロギング機構 |
| `TestAnalyzeClassifierLog` | 1 | ログ分析 |
| `TestIntegration` | 2 | 統合テスト |

**テスト結果**:
```
Ran 24 tests in 0.019s
OK
```

#### 統合テスト (`test_api.py`)

**11テスト** (モック使用):
- セットアップ未完了時の処理
- 空メッセージ処理
- 正常なリクエスト処理
- スケジュール問い合わせの判定→ルート処理
- 非スケジュール問い合わせ→LLM処理
- エラーハンドリング（タイムアウト等）
- 安全プロンプトの付与確認
- ロギング確認

---

## 実装の特徴

### 1. 高精度・高速判定
- **正規表現**: 1ms以下で明確な場合を即座に判定
- **LLM**: グレーゾーンのみ呼び出し（呼び出し削減）
- **ハイブリッド**: 速度と精度のバランス

### 2. 捏造防止
- **ルール処理**: `session["schedules"]` のみからのデータ取得
- **LLM処理**: 安全プロンプトで予定事実生成を禁止
- **検証**: ログで実際の応答を監視可能

### 3. 可観測性
- **JSON Lines ログ**: 1行1イベントで検索・集計容易
- **詳細情報**: 入力、判定結果、処理経路、応答、処理時間を記録
- **分析関数**: `analyze_classifier_log()` でワンコマンド集計

### 4. 拡張性
- **設定可能な閾値**: `CLASSIFIER_CONFIDENCE_THRESHOLD`
- **フィーチャーフラグ**: `use_llm` パラメータで判定器の有効/無効を切り替え可
- **モジュール分離**: `classifier.py` として独立、将来別プロセス化可能

### 5. 業務レベルのコード品質
- **Docstring完備**: 全関数に入出力・役割を明記
- **型ヒント**: Python 3.9+ の型注釈を使用
- **ログ記録**: `logging` モジュールで構造化ログ
- **エラーハンドリング**: 例外処理とフォールバック完備

---

## 使用方法

### 分類器の単独使用

```python
from classifier import classify_schedule_intent

# ルールベースのみで判定
result = classify_schedule_intent("今日の予定は？", use_llm=False)
print(result)
# {
#   "intent": "schedule_query",
#   "scope": "today",
#   "confidence": 0.95,
#   "start_date": "2026-01-02",
#   "end_date": "2026-01-02",
#   ...
# }

# LLM分類器を含める（グレーゾーン時）
result = classify_schedule_intent("予定ってある？", use_llm=True)
```

### Flask API の使用

```bash
# チャット API
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "今日の予定は？"}'

# レスポンス例
{
  "ok": true,
  "reply": "今日の予定はこれね。\n・10:00 朝の会議\n・14:00 午後のミーティング"
}
```

### ロギング分析

```python
from classifier import analyze_classifier_log

result = analyze_classifier_log()
print(f"総イベント数: {result['total_events']}")
print(f"予定問い合わせ: {result['schedule_query_count']}")
print(f"ルールベース: {result['rule_based_count']}")
print(f"LLM: {result['llm_count']}")
print(f"エラー: {result['error_count']}")
```

---

## 今後のステップ

### Phase 1: 本番環境での試験運用（推奨）
1. ローカル環境での詳細なテスト実施
2. 実際のユーザ発話データを用いた精度検証
3. 信頼度閾値（初期値 0.80）の最適化
4. A/B テスト（従来ルールのみ vs 判定器導入版）

### Phase 2: プロンプト最適化
- LLM分類器用プロンプトのチューニング
- 自然言語日時表現（「来月の第2火曜」等）への対応
- エッジケースの処理改善

### Phase 3: パフォーマンス最適化
- 専用軽量分類モデルの導入（速度向上）
- キャッシング機構（頻出発話の高速化）
- バッチ処理対応

### Phase 4: 運用自動化
- 定期的な精度レポート生成
- 閾値の自動調整
- アラート機構の実装

---

## 技術スタック

| 項目 | 詳細 |
|------|------|
| **言語** | Python 3.9+ |
| **Web フレームワーク** | Flask 3.0+ |
| **LLM バックエンド** | Ollama (ローカル) |
| **ロギング** | Python `logging` + JSON Lines |
| **テスト** | unittest (24テスト、全合格) |
| **ドキュメント** | Markdown (1900+ 行) |

---

## 参考資料

- [要件定義書](docs/REQUIREMENTS.md) - ビジネス要件・検証基準
- [詳細設計書](docs/DESIGN.md) - アーキテクチャ・実装仕様
- [テストケース](docs/TEST_CASES.md) - 実装テスト・受け入れ基準

---

**実装者**: GitHub Copilot  
**実装日**: 2026-01-02  
**バージョン**: 1.0
