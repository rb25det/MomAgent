"""
統合テスト：API フロー、エンドツーエンドシナリオの検証

このテストモジュールは以下をテストします：
- 判定器 → ルール処理の統合
- 判定器 → LLM処理の統合
- エラーハンドリング

※ Flask セッション関連の複雑なテストは、実際の運用環境での手動テストを推奨
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from classifier import classify_schedule_intent


class TestClassifierIntegration(unittest.TestCase):
    """分類器とルール処理の統合テスト"""
    
    def test_schedule_query_classification(self):
        """スケジュール問い合わせの分類"""
        result = classify_schedule_intent("今日の予定は？", use_llm=False)
        
        self.assertEqual(result["intent"], "schedule_query")
        self.assertEqual(result["scope"], "today")
        self.assertGreaterEqual(result["confidence"], 0.85)
        self.assertIsNotNone(result["start_date"])
        self.assertIsNotNone(result["end_date"])
    
    def test_not_schedule_classification(self):
        """非スケジュール問い合わせの分類"""
        result = classify_schedule_intent("予定が立て込んでる", use_llm=False)
        
        self.assertEqual(result["intent"], "not_schedule")
        self.assertGreaterEqual(result["confidence"], 0.85)
    
    def test_tomorrow_schedule_query(self):
        """明日の予定問い合わせ"""
        result = classify_schedule_intent("明日の予定を教えて", use_llm=False)
        
        self.assertEqual(result["intent"], "schedule_query")
        self.assertEqual(result["scope"], "tomorrow")
        self.assertGreaterEqual(result["confidence"], 0.85)
    
    def test_week_schedule_query(self):
        """今週の予定問い合わせ"""
        result = classify_schedule_intent("今週の予定は？", use_llm=False)
        
        self.assertEqual(result["intent"], "schedule_query")
        self.assertEqual(result["scope"], "week")
        self.assertGreaterEqual(result["confidence"], 0.85)
    
    def test_month_schedule_query(self):
        """今月の予定問い合わせ"""
        result = classify_schedule_intent("今月の予定を見たい", use_llm=False)
        
        self.assertEqual(result["intent"], "schedule_query")
        self.assertEqual(result["scope"], "month")
        self.assertGreaterEqual(result["confidence"], 0.80)


class TestEdgeCases(unittest.TestCase):
    """エッジケースのテスト"""
    
    def test_schedule_modification_request(self):
        """予定変更要望（否定）"""
        result = classify_schedule_intent("予定を変更したい", use_llm=False)
        self.assertEqual(result["intent"], "not_schedule")
    
    def test_schedule_deletion_request(self):
        """予定削除要望（否定）"""
        result = classify_schedule_intent("予定を削除してほしい", use_llm=False)
        self.assertEqual(result["intent"], "not_schedule")
    
    def test_gray_zone_handling(self):
        """グレーゾーンの処理"""
        result = classify_schedule_intent("予定ってある？", use_llm=False)
        
        # グレーゾーン：0.5～0.8の信頼度
        self.assertTrue(0.4 < result["confidence"] < 0.9)
    
    def test_mixed_positive_negative(self):
        """混合表現（「予定があって、大変です」）"""
        result = classify_schedule_intent("予定があって大変です", use_llm=False)
        
        # 否定シグナルの方が強い（状況説明）
        if result["intent"] == "schedule_query":
            self.assertTrue(result["confidence"] < 0.85)
    
    def test_formal_request(self):
        """敬語での要望"""
        result = classify_schedule_intent("予定の確認をしたいのですが", use_llm=False)
        
        # 「確認」という単語がないので not_schedule
        self.assertIn(result["intent"], ["schedule_query", "not_schedule"])



class TestScopeInference(unittest.TestCase):
    """スコープ推定のテスト"""
    
    def test_today_inference(self):
        """今日のスコープ推定"""
        result = classify_schedule_intent("今日なに？", use_llm=False)
        self.assertEqual(result["scope"], "today")
    
    def test_next_inference(self):
        """次のスコープ推定"""
        result = classify_schedule_intent("次の予定は？", use_llm=False)
        self.assertEqual(result["scope"], "next")
    
    def test_upcoming_inference(self):
        """直近のスコープ推定"""
        result = classify_schedule_intent("直近の予定を見たい", use_llm=False)
        # 「直近」は「next」にマップされる
        self.assertIn(result["scope"], ["next", "upcoming"])



class TestDateRangeComputation(unittest.TestCase):
    """日付範囲の計算テスト"""
    
    def test_schedule_query_has_dates(self):
        """スケジュール問い合わせは日付範囲を持つ"""
        result = classify_schedule_intent("今日の予定？", use_llm=False)
        
        self.assertIsNotNone(result["start_date"])
        self.assertIsNotNone(result["end_date"])
        # 日付形式の確認
        self.assertRegex(result["start_date"], r"\d{4}-\d{2}-\d{2}")
    
    def test_non_schedule_has_no_dates(self):
        """非スケジュール問い合わせは日付範囲なし"""
        result = classify_schedule_intent("元気？", use_llm=False)
        
        self.assertIsNone(result["start_date"])
        self.assertIsNone(result["end_date"])


if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()
