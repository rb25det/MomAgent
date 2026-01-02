# テストケース・受け入れ基準

## 1. テストデータセット（代表的なユーザ発話）

### 1.1 肯定例（予定問い合わせ）

| ID | 発話 | 期待 Intent | 期待 Scope | 期待 Conf | 根拠 |
|----|------|-----------|-----------|----------|------|
| POS-01 | 今日の予定は？ | schedule_query | today | >= 0.90 | 時間キー + 疑問符 |
| POS-02 | 今日の予定を教えて | schedule_query | today | >= 0.90 | 時間キー + 動詞 |
| POS-03 | 今日何かある？ | schedule_query | today | >= 0.85 | 時間キー + 疑問 |
| POS-04 | 明日の予定見せて | schedule_query | tomorrow | >= 0.90 | 明確なキー + 動詞 |
| POS-05 | 今週の予定 | schedule_query | week | >= 0.85 | 時間キー（疑問符なし） |
| POS-06 | 来週の予定教えて | schedule_query | week | >= 0.90 | キー + 動詞 |
| POS-07 | 今月の予定を確認したい | schedule_query | month | >= 0.90 | 月キー + 動詞 |
| POS-08 | 次の予定は？ | schedule_query | next | >= 0.90 | 「次」+ 疑問符 |
| POS-09 | これからの予定は？ | schedule_query | upcoming | >= 0.85 | 「これから」+ 疑問符 |
| POS-10 | 直近の予定を見たい | schedule_query | upcoming | >= 0.90 | キー + 動詞 |
| POS-11 | 予定の確認をしたい | schedule_query | unspecified | >= 0.75 | 「予定」+ 動詞（スコープ不明） |
| POS-12 | schedule確認 | schedule_query | unspecified | >= 0.85 | 英語キー + 動詞 |

### 1.2 否定例（非予定問い合わせ）

| ID | 発話 | 期待 Intent | 期待 Scope | 期待 Conf | 根拠 |
|----|------|-----------|-----------|----------|------|
| NEG-01 | 予定が立て込んでる | not_schedule | not_applicable | >= 0.90 | 説明・感想（問い合わせではない） |
| NEG-02 | 予定が詰まってる | not_schedule | not_applicable | >= 0.90 | 状況説明 |
| NEG-03 | 予定が忙しい | not_schedule | not_applicable | >= 0.85 | 状況説明 |
| NEG-04 | 予定を立てたい | not_schedule | not_applicable | >= 0.90 | 追加・作成要望（確認ではない） |
| NEG-05 | 予定を変更してほしい | not_schedule | not_applicable | >= 0.90 | 編集要望 |
| NEG-06 | 予定を削除したい | not_schedule | not_applicable | >= 0.90 | 削除要望 |
| NEG-07 | 最近どう？ | not_schedule | not_applicable | >= 0.95 | 予定無関連の雑談 |
| NEG-08 | 宿題ってある？ | not_schedule | not_applicable | >= 0.90 | 「予定」キーなし |
| NEG-09 | 元気ですか | not_schedule | not_applicable | >= 0.98 | 明らかに無関連 |
| NEG-10 | 今日は誰と会った？ | not_schedule | not_applicable | >= 0.85 | 過去形（確認ではない） |

### 1.3 グレーゾーン例（判定が難しい）

| ID | 発話 | 期待 Intent | 期待 Scope | 期待 Conf | 対応戦略 |
|----|------|-----------|-----------|----------|----------|
| GRAY-01 | 予定ってある？ | schedule_query | unspecified | 0.6～0.8 | LLM判定。スコープ不明確 |
| GRAY-02 | 今日何やる？ | schedule_query | today | 0.7～0.85 | 「今日」キーあるが、敬語なし |
| GRAY-03 | 明日何するの？ | schedule_query | tomorrow | 0.7～0.85 | カジュアル表現 |
| GRAY-04 | 次何か予定ある？ | schedule_query | next | 0.75～0.85 | 「次」+ 疑問 + 「予定」なし |
| GRAY-05 | スケジュール見たい | schedule_query | unspecified | 0.80～0.90 | 英語キーのみ |
| GRAY-06 | 予定が入ってるんですか？ | schedule_query | unspecified | 0.75～0.85 | 質問形式だが確認的 |
| GRAY-07 | 予定を教えてもらえる？ | schedule_query | unspecified | 0.80～0.90 | 敬語・依頼形 |
| GRAY-08 | 今日は何か予定ある？ | schedule_query | today | 0.80～0.90 | 自然な会話体 |

---

## 2. エンドツーエンドテストケース

### 2.1 シナリオテスト

| ID | シナリオ | 前提 | ユーザ発話 | 期待フロー | 期待応答例 | 合格基準 |
|----|---------|------|-----------|-----------|-----------|---------|
| E2E-01 | 今日の予定を確認 | 登録済み予定あり（本日） | 「今日の予定は？」 | classify → rule処理 | 「・10:00 会議\n・15:00 打ち合わせ」 | ✅ルール応答のみ |
| E2E-02 | 予定がない日 | 本日予定なし | 「今日の予定は？」 | classify → rule処理 | 「今日は予定が入ってないわよ」 | ✅ ルール応答 |
| E2E-03 | 感想への対応 | 任意 | 「予定が立て込んでる」 | classify (low) → LLM処理 | 「大変ですね。頑張ってね」 | ✅ LLM応答のみ |
| E2E-04 | 来週の予定 | 登録済み予定あり（来週） | 「来週の予定見せて」 | classify → rule処理 | 「来週の予定:\n・月曜...」 | ✅ ルール応答 |
| E2E-05 | グレーゾーン | 任意 | 「予定ってある？」 | classify (GRAY) → LLM処理 | 「予定管理画面で確認してね」 | 🟡 低信頼時の対応 |
| E2E-06 | 分類器タイムアウト | 外部遅延あり | 任意 | timeout → LLM fallback | LLM応答 | ✅ fallback成功 |
| E2E-07 | 日本語複雑表現 | 任意 | 「来月の第2火曜の予定を知りたい」 | classify (low?) → LLM | 「複雑な日付は確認画面で」 | 🟡 複雑日付への対応 |
| E2E-08 | チャット連続 | 履歴あり | 「今週の予定」→「来週は？」 | 各々classify → rule | 「今週：...\n来週：...」 | ✅ 文脈を保持 |

### 2.2 エラーハンドリングテスト

| ID | エラー条件 | 期待動作 | 合格基準 |
|----|-----------|---------|---------|
| ERR-01 | 分類器LLMが利用不可 | fallback to LLM（安全プロンプト） | ✅ 処理継続 |
| ERR-02 | 分類器タイムアウト（>3秒） | LLMへルーティング + warning log | ✅ graceful fallback |
| ERR-03 | JSON解析失敗 | デフォルト判定（not_schedule） | ✅ エラー耐性 |
| ERR-04 | ログファイル書き込み失敗 | warning出力、処理は継続 | ✅ 可用性維持 |
| ERR-05 | 空白文字列入力 | エラー応答 | ✅ バリデーション |

---

## 3. 機能テスト

### 3.1 分類器機能テスト

```python
# test_classifier.py
import unittest
from app import classify_schedule_intent

class TestClassifyScheduleIntent(unittest.TestCase):
    
    def test_positive_clear(self):
        """明確な肯定例"""
        result = classify_schedule_intent("今日の予定は？")
        self.assertEqual(result["intent"], "schedule_query")
        self.assertEqual(result["scope"], "today")
        self.assertGreaterEqual(result["confidence"], 0.85)
    
    def test_negative_clear(self):
        """明確な否定例"""
        result = classify_schedule_intent("予定が立て込んでる")
        self.assertEqual(result["intent"], "not_schedule")
        self.assertGreaterEqual(result["confidence"], 0.85)
    
    def test_gray_zone(self):
        """グレーゾーン例"""
        result = classify_schedule_intent("予定ってある？")
        self.assertIn(result["intent"], ["schedule_query", "not_schedule"])
        # confidence が中程度
        self.assertTrue(0.4 < result["confidence"] < 0.9)
    
    def test_empty_input(self):
        """空入力"""
        result = classify_schedule_intent("")
        self.assertEqual(result["intent"], "not_schedule")
        self.assertEqual(result["confidence"], 0.0)
```

### 3.2 日付範囲計算テスト

```python
# test_date_range.py
import unittest
from datetime import date
from app import compute_date_range

class TestComputeDateRange(unittest.TestCase):
    
    def setUp(self):
        # 2026-01-02 を基準日として設定
        self.reference = date(2026, 1, 2)  # 金曜
    
    def test_today(self):
        """当日範囲"""
        start, end = compute_date_range("today", self.reference)
        self.assertEqual((start, end), (self.reference, self.reference))
    
    def test_tomorrow(self):
        """翌日範囲"""
        start, end = compute_date_range("tomorrow", self.reference)
        expected_tomorrow = date(2026, 1, 3)
        self.assertEqual((start, end), (expected_tomorrow, expected_tomorrow))
    
    def test_week(self):
        """週範囲（月曜始まり）"""
        start, end = compute_date_range("week", self.reference)
        expected_start = date(2025, 12, 29)  # その週の月曜
        expected_end = date(2026, 1, 4)      # その週の日曜
        self.assertEqual((start, end), (expected_start, expected_end))
    
    def test_month(self):
        """月範囲"""
        start, end = compute_date_range("month", self.reference)
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 1, 31))
    
    def test_next_scope(self):
        """next スコープ（範囲なし）"""
        result = compute_date_range("next", self.reference)
        self.assertIsNone(result)
```

### 3.3 ロギングテスト

```python
# test_logging.py
import unittest
import json
from pathlib import Path
from app import log_event, CLASSIFIER_LOG_PATH

class TestLogging(unittest.TestCase):
    
    def setUp(self):
        # テスト用ログファイルをクリア
        if CLASSIFIER_LOG_PATH.exists():
            CLASSIFIER_LOG_PATH.unlink()
    
    def test_log_event_creates_file(self):
        """ロギングがファイルを生成"""
        judgment = {
            "intent": "schedule_query",
            "scope": "today",
            "confidence": 0.95,
            "reasoning": "test"
        }
        log_event("テスト", judgment, "rule-based", "応答", 50.0)
        
        self.assertTrue(CLASSIFIER_LOG_PATH.exists())
    
    def test_log_event_format(self):
        """ログのJSON形式が正しい"""
        judgment = {
            "intent": "schedule_query",
            "scope": "today",
            "confidence": 0.95,
            "reasoning": "test"
        }
        log_event("テスト", judgment, "rule-based", "応答", 50.0)
        
        with open(CLASSIFIER_LOG_PATH, "r") as f:
            line = f.readline()
            event = json.loads(line)
            
            self.assertIn("timestamp", event)
            self.assertEqual(event["event_type"], "schedule_classification")
            self.assertEqual(event["chosen_path"], "rule-based")
```

---

## 4. 精度評価テスト

### 4.1 テストセット作成

```python
# test_dataset.py
TEST_CASES = [
    # (発話, 期待intent, 期待scope, min_confidence)
    ("今日の予定は？", "schedule_query", "today", 0.85),
    ("予定が立て込んでる", "not_schedule", "not_applicable", 0.85),
    # ... 100件以上
]

def evaluate_classifier():
    """テストセットで分類器を評価"""
    tp = tn = fp = fn = 0
    
    for text, expected_intent, expected_scope, min_conf in TEST_CASES:
        result = classify_schedule_intent(text)
        
        predicted = result["intent"]
        conf = result["confidence"]
        
        if predicted == expected_intent and conf >= min_conf:
            if expected_intent == "schedule_query":
                tp += 1
            else:
                tn += 1
        else:
            if expected_intent == "schedule_query":
                fn += 1  # False Negative
            else:
                fp += 1  # False Positive
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    print(f"Precision: {precision:.2%}")
    print(f"Recall: {recall:.2%}")
    print(f"F1 Score: {f1:.2%}")
    print(f"False Positive Rate: {fp / (fp + tn):.2%}")
    
    return {
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "false_positive_rate": fp / (fp + tn) if (fp + tn) > 0 else 0,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn
    }
```

### 4.2 精度目標

| 指標 | 初期目標 | 本番目標 | 測定方法 |
|------|---------|---------|---------|
| Precision | >= 0.93 | >= 0.95 | テストセット100発話 |
| Recall | >= 0.85 | >= 0.88 | テストセット100発話 |
| F1 Score | >= 0.89 | >= 0.91 | Precision & Recall から計算 |
| False Positive Rate | < 5% | < 2% | テストセット |
| False Negative Rate | < 15% | < 10% | テストセット |

---

## 5. パフォーマンステスト

### 5.1 レイテンシ測定

```python
# test_performance.py
import time
from app import classify_schedule_intent, api_chat

def measure_classifier_latency():
    """分類器のみのレイテンシ測定"""
    times = []
    for _ in range(100):
        start = time.time()
        classify_schedule_intent("今日の予定は？")
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    max_time = max(times)
    p95 = sorted(times)[95]
    
    print(f"Classifier latency:")
    print(f"  Avg: {avg:.1f}ms")
    print(f"  P95: {p95:.1f}ms")
    print(f"  Max: {max_time:.1f}ms")
    
    assert avg <= 100, f"Average latency {avg}ms exceeds 100ms"
    assert p95 <= 150, f"P95 latency {p95}ms exceeds 150ms"
```

### 5.2 パフォーマンス目標

| メトリクス | 目標値 | 測定条件 |
|-----------|--------|---------|
| 分類器平均遅延 | <= 100ms | ローカル、100発話平均 |
| 分類器P95遅延 | <= 150ms | ローカル、100発話 |
| 分類 + ルール処理合計 | <= 200ms | 実装後に測定 |
| メモリ使用量 | <= 50MB 増分 | 実装後に測定 |

---

## 6. セキュリティ・監査テスト

### 6.1 プライバシーテスト

```python
def test_no_schedule_data_sent_to_llm():
    """
    LLM処理時に実際の予定情報が送信されていないことを確認
    """
    # ログを監視して、予定内容が含まれていないことを確認
    with open(CLASSIFIER_LOG_PATH) as f:
        for line in f:
            event = json.loads(line)
            if event["chosen_path"] == "llm":
                # LLM応答には予定の具体内容が含まれていないはず
                reply = event["reply_text"]
                # 予定の ID や時刻などが含まれていないか確認
                assert "10:00" not in reply or "会議" not in reply  # 例
```

### 6.2 ロギング監査テスト

```python
def test_logging_compliance():
    """
    ログが適切に記録・管理されているか確認
    """
    # ログファイルの存在確認
    assert CLASSIFIER_LOG_PATH.exists()
    
    # JSON形式確認
    with open(CLASSIFIER_LOG_PATH) as f:
        for line in f:
            event = json.loads(line)  # 必要なフィールドが全て含まれている
            required_fields = [
                "timestamp", "event_type", "user_message",
                "classifier_intent", "classifier_confidence",
                "chosen_path"
            ]
            for field in required_fields:
                assert field in event, f"Missing field: {field}"
```

---

## 7. 受け入れ基準サマリ

### 7.1 機能受け入れ基準

| # | 基準 | 判定方法 | 合格基準 |
|----|------|--------|--------|
| F1 | 分類器が実装されている | コード確認 | 関数が存在・動作 |
| F2 | ルールベース処理と分類器の統合 | E2E テスト | E2E-01 ～ 08 すべて合格 |
| F3 | 信頼度閾値による分岐 | コード確認 + テスト | threshold >= 0.80 で分岐 |
| F4 | エラーハンドリング | エラーテスト | ERR-01 ～ 05 すべて合格 |
| F5 | ロギング機構 | ログ確認 | JSON 形式で記録される |
| F6 | LLM 安全プロンプト | コード確認 | ask() に safety_instruction パラメータ |

### 7.2 非機能受け入れ基準

| # | 基準 | 目標値 | 判定方法 |
|----|------|--------|--------|
| NF1 | 分類精度（F1 Score） | >= 0.90 | テストセット 100 発話 |
| NF2 | False Positive Rate | < 2% | テストセット集計 |
| NF3 | 平均レイテンシ | <= 100ms | 分類器のみ |
| NF4 | 合計レイテンシ | <= 200ms | 分類 + ルール処理 |
| NF5 | エラー復旧 | 自動 fallback | エラーテスト実施 |
| NF6 | ログ可用性 | 100% | 運用 1 週間の集計 |

### 7.3 サインオフ

- **開発者確認**: [ ] 実装完了、ユニットテスト合格
- **テスター確認**: [ ] 統合テスト・精度テスト合格
- **PO確認**: [ ] ビジネス要件を満たす、ユーザ体験に問題なし
- **リリース確認**: [ ] 本番環境でのロールアウト承認

---

## 8. トラブルシューティングガイド

### 8.1 よくある問題と対応

| 問題 | 症状 | 原因 | 対応 |
|------|------|------|------|
| 分類精度が低い | F1 < 0.85 | プロンプトが不適切 | プロンプト調整、LLM再学習 |
| False Positive が多い | 予定と無関係な発話が引っかかる | 閾値が低すぎる | 閾値を 0.90 に引き上げ |
| タイムアウト頻発 | 分類器が 3 秒以上かかる | LLM 負荷が高い | 軽量モデルに切り替え |
| ログファイルが肥大化 | ディスク圧迫 | ログローテーション未設定 | ローテーション機構を追加 |

### 8.2 デバッグ用ログレベル

```python
# DEBUG: すべての判定詳細を記録
# INFO: 重要なイベント（ルーティング決定等）
# WARNING: 低信頼判定、タイムアウト等
# ERROR: 分類器エラー、LLM エラー等
```

---

**バージョン**: 1.0  
**作成日**: 2026-01-02  
**ステータス**: ドラフト
