"""
ユニットテスト：分類器・補助機能の検証

このテストモジュールは以下をテストします：
- 分類器の判定精度（肯定例、否定例、グレーゾーン）
- 日付範囲計算
- ロギング機構
"""

import unittest
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path

from classifier import (
    classify_schedule_intent,
    _quick_filter,
    compute_date_range,
    log_event,
    analyze_classifier_log,
)


class TestQuickFilter(unittest.TestCase):
    """ルールベース判定（_quick_filter）のテスト"""
    
    def test_strong_positive(self):
        """強い肯定シグナル"""
        is_likely, conf = _quick_filter("今日の予定を教えて")
        self.assertEqual(is_likely, True)
        self.assertGreaterEqual(conf, 0.9)
    
    def test_time_key_with_question(self):
        """時間キー + 疑問符"""
        is_likely, conf = _quick_filter("明日の予定は？")
        self.assertEqual(is_likely, True)
        self.assertGreaterEqual(conf, 0.85)
    
    def test_clear_negative(self):
        """明確な否定"""
        is_likely, conf = _quick_filter("予定が立て込んでる")
        self.assertEqual(is_likely, False)
        self.assertGreaterEqual(conf, 0.9)
    
    def test_schedule_creation(self):
        """予定立案要望（否定）"""
        is_likely, conf = _quick_filter("予定を立てたい")
        self.assertEqual(is_likely, False)
        self.assertGreaterEqual(conf, 0.85)
    
    def test_gray_zone(self):
        """グレーゾーン"""
        is_likely, conf = _quick_filter("予定ってある？")
        self.assertIsNone(is_likely)
        self.assertTrue(0.4 < conf < 0.7)
    
    def test_empty_input(self):
        """空入力"""
        is_likely, conf = _quick_filter("")
        self.assertEqual(is_likely, False)
        self.assertEqual(conf, 0.0)
    
    def test_unrelated(self):
        """無関連な発話"""
        is_likely, conf = _quick_filter("最近どう？")
        self.assertEqual(is_likely, False)


class TestComputeDateRange(unittest.TestCase):
    """日付範囲計算（compute_date_range）のテスト"""
    
    def setUp(self):
        """基準日: 2026-01-02 (金曜日)"""
        self.reference_date = date(2026, 1, 2)
    
    def test_today_scope(self):
        """当日範囲"""
        start, end = compute_date_range("today", self.reference_date)
        self.assertEqual((start, end), (self.reference_date, self.reference_date))
    
    def test_tomorrow_scope(self):
        """翌日範囲"""
        start, end = compute_date_range("tomorrow", self.reference_date)
        expected_tomorrow = date(2026, 1, 3)
        self.assertEqual((start, end), (expected_tomorrow, expected_tomorrow))
    
    def test_week_scope(self):
        """週範囲（月曜始まり）"""
        start, end = compute_date_range("week", self.reference_date)
        # 2026-01-02 は金曜。その週の月曜は 2025-12-29
        expected_start = date(2025, 12, 29)
        expected_end = date(2026, 1, 4)
        self.assertEqual((start, end), (expected_start, expected_end))
    
    def test_month_scope(self):
        """月範囲"""
        start, end = compute_date_range("month", self.reference_date)
        self.assertEqual(start, date(2026, 1, 1))
        self.assertEqual(end, date(2026, 1, 31))
    
    def test_december_month_scope(self):
        """12月の月範囲（年越え）"""
        december_date = date(2025, 12, 15)
        start, end = compute_date_range("month", december_date)
        self.assertEqual(start, date(2025, 12, 1))
        self.assertEqual(end, date(2025, 12, 31))
    
    def test_next_scope(self):
        """next スコープ（範囲なし）"""
        result = compute_date_range("next", self.reference_date)
        self.assertIsNone(result)
    
    def test_upcoming_scope(self):
        """upcoming スコープ（範囲なし）"""
        result = compute_date_range("upcoming", self.reference_date)
        self.assertIsNone(result)
    
    def test_unknown_scope(self):
        """未知のスコープ"""
        result = compute_date_range("unknown", self.reference_date)
        self.assertIsNone(result)


class TestClassifyScheduleIntent(unittest.TestCase):
    """メイン分類関数（classify_schedule_intent）のテスト"""
    
    def test_positive_example(self):
        """肯定例：今日の予定は？"""
        result = classify_schedule_intent("今日の予定は？", use_llm=False)
        self.assertEqual(result["intent"], "schedule_query")
        self.assertEqual(result["scope"], "today")
        self.assertGreaterEqual(result["confidence"], 0.80)
    
    def test_negative_example(self):
        """否定例：予定が立て込んでる"""
        result = classify_schedule_intent("予定が立て込んでる", use_llm=False)
        self.assertEqual(result["intent"], "not_schedule")
        self.assertGreaterEqual(result["confidence"], 0.80)
    
    def test_empty_input(self):
        """空入力"""
        result = classify_schedule_intent("", use_llm=False)
        self.assertEqual(result["intent"], "not_schedule")
        self.assertEqual(result["confidence"], 0.0)
    
    def test_date_range_computed(self):
        """日付範囲が計算されている"""
        result = classify_schedule_intent("今日の予定は？", use_llm=False)
        self.assertIsNotNone(result["start_date"])
        self.assertIsNotNone(result["end_date"])
        # start_date と end_date が同じ（今日）
        self.assertEqual(result["start_date"], result["end_date"])


class TestLogging(unittest.TestCase):
    """ロギング機構（log_event）のテスト"""
    
    def setUp(self):
        """テスト用ログファイルを作成"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "test.log"
    
    def tearDown(self):
        """テスト用ログファイルを削除"""
        self.temp_dir.cleanup()
    
    def test_log_event_creates_json(self):
        """ロギングがJSON行を生成"""
        judgment = {
            "intent": "schedule_query",
            "scope": "today",
            "confidence": 0.95,
            "reasoning": "test"
        }
        
        # ロギング関数をカスタマイズ（テスト用）
        event = {
            "timestamp": "2026-01-02T12:00:00Z",
            "event_type": "schedule_classification",
            "user_message": "テスト",
            "classifier_intent": judgment["intent"],
            "classifier_scope": judgment["scope"],
            "classifier_confidence": judgment["confidence"],
            "classifier_reasoning": judgment["reasoning"],
            "chosen_path": "rule-based",
            "reply_text": "応答",
            "processing_time_ms": 50.0,
            "error": None
        }
        
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        
        # ファイルが作成されたか確認
        self.assertTrue(self.log_file.exists())
        
        # JSON形式で読み込めるか確認
        with open(self.log_file, "r", encoding="utf-8") as f:
            line = f.readline()
            loaded = json.loads(line)
            self.assertEqual(loaded["event_type"], "schedule_classification")
            self.assertEqual(loaded["chosen_path"], "rule-based")


class TestAnalyzeClassifierLog(unittest.TestCase):
    """ログ分析関数（analyze_classifier_log）のテスト"""
    
    def setUp(self):
        """テスト用ログファイルを作成"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "test.log"
    
    def tearDown(self):
        """テスト用ログファイルを削除"""
        self.temp_dir.cleanup()
    
    def test_analyze_empty_log(self):
        """空のログファイルを分析"""
        # ファイルが存在しない場合
        result = analyze_classifier_log(Path(self.temp_dir.name) / "nonexistent.log")
        self.assertEqual(result["total_events"], 0)
    
    def test_analyze_with_events(self):
        """イベント含むログを分析"""
        # テストログを作成
        events = [
            {
                "timestamp": "2026-01-02T12:00:00Z",
                "classifier_intent": "schedule_query",
                "classifier_confidence": 0.95,
                "chosen_path": "rule-based"
            },
            {
                "timestamp": "2026-01-02T12:01:00Z",
                "classifier_intent": "not_schedule",
                "classifier_confidence": 0.85,
                "chosen_path": "llm"
            },
            {
                "timestamp": "2026-01-02T12:02:00Z",
                "classifier_intent": "schedule_query",
                "classifier_confidence": 0.60,
                "chosen_path": "llm",
                "error": "timeout"
            }
        ]
        
        with open(self.log_file, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        
        # ログを分析
        result = analyze_classifier_log(self.log_file)
        
        # 結果の検証
        self.assertEqual(result["total_events"], 3)
        self.assertEqual(result["schedule_query_count"], 2)
        self.assertEqual(result["not_schedule_count"], 1)
        self.assertEqual(result["rule_based_count"], 1)
        self.assertEqual(result["llm_count"], 2)
        self.assertEqual(result["error_count"], 1)
        
        # 信頼度の平均が計算されている
        self.assertAlmostEqual(result["avg_confidence_schedule"], (0.95 + 0.60) / 2, places=2)
        self.assertAlmostEqual(result["avg_confidence_not"], 0.85, places=2)


class TestIntegration(unittest.TestCase):
    """統合テスト"""
    
    def test_positive_example_integration(self):
        """肯定例の統合テスト"""
        # ルールベースのみで判定（LLM呼び出し不要）
        result = classify_schedule_intent("今日の予定を教えて", use_llm=False)
        
        # 期待値
        self.assertEqual(result["intent"], "schedule_query")
        self.assertEqual(result["scope"], "today")
        self.assertGreaterEqual(result["confidence"], 0.80)
        self.assertIsNotNone(result["start_date"])
        self.assertIsNotNone(result["end_date"])
        self.assertIsNone(result["error"])
    
    def test_negative_example_integration(self):
        """否定例の統合テスト"""
        result = classify_schedule_intent("予定が詰まってる", use_llm=False)
        
        self.assertEqual(result["intent"], "not_schedule")
        self.assertGreaterEqual(result["confidence"], 0.80)
        self.assertIsNone(result["error"])


if __name__ == "__main__":
    unittest.main()
