# 要件定義書：お母さんAI 予定応答機能（判定器導入版）

## 1. 目的

ユーザが「予定」を尋ねた際に、LLMの誤答（捏造・無関係応答）を防ぎ、登録済みの予定を正確かつ文脈に沿って返答するために、**ルールベース＋判定器（LLM分類器）** を組み合わせて、意図・期間を高精度に判定し、安全にスケジュール情報を提供する。

---

## 2. 前提

- **現行環境**: セッション管理で予定を `session["schedules"]` に保持。予定の追加・編集・削除が可能（予定は辞書リスト）。
- **既存処理**: `api_chat` によりユーザ発話を受信。最終的に `ask()` で外部LLM（Ollama）に投げる。
- **既存モジュール**: ルールベース判定・レンダリング機能が `app_intentfix.py` に存在（`is_schedule_query`, `handle_schedule_query` 等）。
- **方針**: LLMに予定事実を「生成」させない。ただしルールベースの判定が完全ではないため、判定器による補強が必要。

---

## 3. 現状で実装できている点

| 項目 | 状態 | 詳細 |
|------|------|------|
| 予定管理 | ✅ | 追加・編集・削除、表示用ソート |
| ルールベース応答 | ✅ | 範囲判定（今日/明日/今週/来週/今月）、直近/次の予定抽出、表示整形 |
| 補完フロー | ✅ | 予定追加後の不足フィールド順次問い合わせ機能 |
| Model再構築・設定 | ✅ | `mom_settings` と `profile` から `Modelfile` 生成し `ollama create` 実行 |

---

## 4. 現状の課題（実装されていない点）

| 課題ID | 課題 | 影響 | 優先度 |
|--------|------|------|--------|
| ISSUE-1 | 単に「予定」という語が含まれるだけで反応する誤検知が発生 | 予定と無関係な文脈でも応答してしまう | **HIGH** |
| ISSUE-2 | ルールベースのみでは「問い合わせ意図」「範囲判定」の高信頼性が難しい | 境界例・曖昧例で誤応答が頻発 | **HIGH** |
| ISSUE-3 | 否定文・説明文（「予定が立て込んでる」等）の誤判定 | 会話の流れを損なう | **MEDIUM** |
| ISSUE-4 | LLMとルールの役割分離が曖昧 | LLMが予定事実を作り出す可能性 | **HIGH** |
| ISSUE-5 | テスト・評価体制が不足（精度の数値測定がない） | 改善効果の検証ができない | **MEDIUM** |
| ISSUE-6 | 「今週末」「来月の第2火曜」等の自然言語日時を正確に解釈できない | 複雑な時間表現への対応不可 | **LOW** |
| ISSUE-7 | ロギング・監査が不足 | いつルールが応答したか、信頼度などの記録がない | **MEDIUM** |

---

## 5. 機能要件（ビジネスレベル）

### 5.1 判定器の導入（必須）

#### 機能概要
- **入力**: ユーザ発話（日本語テキスト）
- **出力**: 
  - Intent: `schedule_query`, `not_schedule`
  - Scope: `today`, `tomorrow`, `week`, `month`, `next`, `upcoming`, `unspecified`, `not_applicable`
  - Date Range（オプション）: `start_date`, `end_date` (YYYY-MM-DD形式)
  - Confidence Score: 0.0 〜 1.0
- **応答閾値**: Confidence >= 0.80 で「予定問い合わせ」とみなす（初期値、運用で調整可能）
- **実装形態**: 同プロセス内の関数（LLMベース。将来的に別プロセス化可）

#### 判定アルゴリズム
1. ユーザ発話を受信
2. 判定器を呼び出し（LLMまたはハイブリッド）
3. 返却値から intent, scope, confidence を取得
4. 以下のロジックで処理を分岐：
   ```
   if intent == "schedule_query" AND confidence >= threshold:
       # ルールベース処理へ
       handle_schedule_query(user_message, scope, date_range)
   else:
       # LLMへ（安全プロンプト付き）
       ask(user_message, safety_instruction="...")
   ```

### 5.2 判定器優先フロー（既存フローの拡張）

- **フロー図**:
  ```
  受信 (user_message)
    ↓
  [判定器実行]
    ↓
  judgment = classifier(user_message)
    ├─ intent == "schedule_query" && confidence >= threshold
    │   ↓
    │  [ルールベース処理]
    │   ↓
    │  handle_schedule_query(user_message)
    │   ↓
    │  return schedule_reply
    │
    └─ その他
        ↓
       [LLM処理（安全プロンプト）]
        ↓
       reply = ask(user_message, safety_instruction)
        ↓
       return llm_reply
  ```

### 5.3 範囲解釈の正規化

- **判定器が返すスコープ** → **ローカル date 範囲への変換**:
  | Scope | 変換ロジック | 例（基準日 2026-01-02） |
  |-------|-----------|----------------------|
  | `today` | 当日のみ | 2026-01-02 〜 2026-01-02 |
  | `tomorrow` | 翌日のみ | 2026-01-03 〜 2026-01-03 |
  | `week` | 月曜〜日曜（日本仕様） | 2025-12-29 〜 2026-01-04 |
  | `month` | 当月1日〜末日 | 2026-01-01 〜 2026-01-31 |
  | `next` | 次の1件を返す | - |
  | `upcoming` | 次の複数件（最大3件） | - |
  | `unspecified` | 判定不可（判定器の低信頼） | - |

### 5.4 安全性（捏造防止）

- **ルールベース応答**: `session["schedules"]` の内容のみに基づく。事実以外の推測・生成は不可。
- **LLM応答**: プロンプトで以下を明示
  - 「ユーザの登録済みスケジュールについて聞かれても、具体的な予定事実は回答しないこと。代わりに『予定の詳細については予定管理画面を確認してください』と案内すること」
  - スケジュール関連の助言（時間管理のコツ等）は OK だが、事実の生成は禁止
- **検証**: ログを定期的にレビューし、LLMが予定事実を述べていないか確認

### 5.5 フォールバック・エラーハンドリング

- **判定器が利用不可の場合**: ルールベース処理に引き継ぐ（`is_schedule_query` で継続判定）、またはLLMへ（安全プロンプト付き）
- **判定器が例外を発生させる場合**: ログ記録し、LLMへルーティング（warning表示）
- **予定がない場合**: 「予定がまだ入ってないわよ」と返す
- **範囲内に予定がない場合**: 「その期間の予定は入ってないわ」と返す

### 5.6 不足フィールド補完（既存機能の活用）

- 予定追加時、`mom_settings` で設定されたフィールド（deadline, location等）の不足を検知
- チャット内で順次ユーザに問い合わせ（既存 `schedule_completion` フロー活用）
- 補完完了後に確認をして保存

### 5.7 可観測性・ロギング

- **記録すべき情報**:
  - Timestamp
  - User message (正規化済み)
  - Classifier intent / scope / confidence
  - Chosen path (rule-based / LLM)
  - Response text
  - Processing time
- **ログ形式**: JSON Lines（1行1イベント）
- **ログ保存先**: `logs/classifier_events.log`
- **レビュー頻度**: 週次（精度評価、閾値調整）

---

## 6. 非機能要件

| 要件ID | 要件 | 目標値 | 測定方法 |
|--------|------|--------|----------|
| NFR-1 | 判定器の精度（F1スコア） | >= 0.90 | テストセットで評価 |
| NFR-2 | False Positive Rate（誤検出率） | < 2% | テストセット、運用ログ集計 |
| NFR-3 | 判定→応答の追加遅延 | <= 200ms | ローカル環境でプロファイル |
| NFR-4 | 判定器障害時のフォールバック | 自動 | 障害注入テスト |
| NFR-5 | 言語対応 | 日本語（一次） | 日本語テストセット充実 |
| NFR-6 | 監査性 | ログで検索・集計可能 | JSONログで実装 |
| NFR-7 | セキュリティ | ローカル保存、外部送信禁止 | コード静的解析 |

---

## 7. 判定器（LLM分類器）仕様

### 7.1 役割
発話が「予定問い合わせ」か否か、および問い合わせの時間スコープ（範囲）を判定し、高信頼度で返す。

### 7.2 入出力インターフェース

#### 入力スキーマ
```json
{
  "text": "ユーザ発話テキスト（日本語）",
  "session_meta": {
    "has_schedules": true/false,
    "num_schedules": 整数
  }
}
```

#### 出力スキーマ
```json
{
  "intent": "schedule_query" | "not_schedule",
  "scope": "today" | "tomorrow" | "week" | "month" | "next" | "upcoming" | "unspecified" | "not_applicable",
  "start_date": "YYYY-MM-DD" | null,
  "end_date": "YYYY-MM-DD" | null,
  "confidence": 0.0 ~ 1.0,
  "reasoning": "判定根拠の簡潔説明（ログ用）"
}
```

### 7.3 判定基準

#### Positive Signals（予定問い合わせの兆候）
- 時間スコープキー: 「今日」「明日」「今週」「来週」「今月」「次」「直近」「これから」
- 問い合わせ動詞: 「教えて」「見せて」「確認」「知りたい」「一覧」「見たい」「ある」「入ってる」
- 疑問符: 「?」「？」

#### Negative Signals（予定問い合わせではない）
- 「予定が立て込んでる」「予定が詰まってる」（説明・感想、問い合わせではない）
- 「予定を立てたい」（追加意図。ただし別フロー）
- 文脈的に予定と無関係（例：「最近どう？」に「予定」が含まれていない）

#### Gray Zone（低信頼例）
- 「予定ってある？」（スコープ不明確）
- 「次何やるの？」（予定か単なる会話か曖昧）
- 「今日何があった？」（過去形。スコープは today だが、完了予定なのか）

### 7.4 信頼度スコアリング

```
confidence = base_score * (signal_weight) * (scope_clarity) * (context_match)

base_score:      明確な信号が多いほど高い（0.5 ~ 1.0）
signal_weight:   肯定シグナルの数・強度（0.8 ~ 1.0）
scope_clarity:   スコープが明確か（0.8 ~ 1.0、曖昧なら 0.5）
context_match:   会話文脈と整合性（0.7 ~ 1.0）
```

### 7.5 実装方針

**初期アプローチ（Phase 1）**: 
- LLMベース（Ollama, 別軽量モデルまたはメインモデルの分類タスク）
- 専用プロンプトで分類タスクに特化

**発展形（Phase 2）**:
- ローカルLLM + 正規表現ハイブリッド（速度最適化）
- キャッシング機構（よくある発話は事前学習結果を再利用）

---

## 8. API / 統合仕様

### 8.1 新 `api_chat` フロー（概略）

```python
@app.route("/api/chat", methods=["POST"])
def api_chat():
    init_session()
    if not is_setup_complete():
        return error response
    
    user_message = normalize(request.json["message"])
    
    # ===== Phase: Classify =====
    judgment = classify_schedule_intent(user_message)
    
    # ===== Phase: Route & Process =====
    if judgment["intent"] == "schedule_query" and judgment["confidence"] >= THRESHOLD:
        # ルールベース処理
        reply = handle_schedule_query(user_message, judgment)
        log_event(user_message, "rule", judgment, reply)
    else:
        # LLM処理（安全プロンプト付き）
        safety_instruction = "ユーザが予定について聞いても、予定の具体的事実は述べず..."
        reply = ask(user_message, system_prompt_amendment=safety_instruction)
        log_event(user_message, "llm", judgment, reply)
    
    # 会話履歴に追加
    session["chat_history"].append({"role": "user", "text": user_message})
    session["chat_history"].append({"role": "assistant", "text": reply})
    session.modified = True
    
    return jsonify({"ok": True, "reply": reply})
```

### 8.2 分類器関数インターフェース

```python
def classify_schedule_intent(text: str) -> dict:
    """
    ユーザ発話から予定問い合わせ意図を分類
    
    Args:
        text (str): ユーザ発話
    
    Returns:
        dict: {
            "intent": "schedule_query" | "not_schedule",
            "scope": "today" | ...,
            "start_date": str | None,
            "end_date": str | None,
            "confidence": float,
            "reasoning": str
        }
    """
    pass
```

### 8.3 エラーハンドリング

| シナリオ | 対応 | ログレベル |
|---------|------|-----------|
| 分類器が例外発生 | LLMへフォールバック、警告ログ | WARNING |
| 分類器タイムアウト（>3秒） | LLMへフォールバック、エラーログ | ERROR |
| 判定結果が不正（無効な日付等） | デフォルト値（intent=not_schedule） を使用、警告ログ | WARNING |
| ルールベース処理で予定がない | 「その期間の予定はないわよ」と返す | INFO |

---

## 9. ルールベース処理との役割分離

| 処理 | ルールベース | LLM | 判定器 |
|------|-----------|-----|--------|
| 予定の抽出 | ✅（session["schedules"]から） | ❌（禁止） | - |
| 予定の時間範囲判定 | ✅（scope から date range へ） | ❌（禁止） | ✅（scope 提供） |
| 予定の整形・表示 | ✅ | ❌ | - |
| 意図判定（予定問い合わせか否か） | 🟡（簡易版） | ❌ | ✅（メイン） |
| 会話の自然さ・共感 | ❌ | ✅ | - |
| スケジュール関連のアドバイス | ❌ | ✅（推奨のみ） | - |
| 補完フロー（不足フィールド問い合わせ） | ✅ | 🟡（補助） | - |

---

## 10. 検証・受け入れ基準

### 10.1 判定精度テスト

- **評価セット**: 最低 100発話（肯定例30、否定例30、境界例20、曖昧例20）
- **評価指標**:
  - Precision: >= 0.95 （false positive を重視）
  - Recall: >= 0.85
  - F1 Score: >= 0.90
  - False Positive Rate: < 2%

### 10.2 エンドツーエンドケース検証

| ID | 入力 | 期待応答 | 判定器出力（期待） | 合格基準 |
|----|------|---------|-------------------|----------|
| E2E-01 | 「今日の予定は？」 | 今日の予定一覧または「予定がない」 | {intent: schedule_query, scope: today, conf: 0.95} | ✅応答が正確 |
| E2E-02 | 「予定が立て込んでる」 | LLMが共感。予定一覧は返さない | {intent: not_schedule, conf: 0.90} | ✅LLM応答のみ |
| E2E-03 | 「次の予定は？」 | 次の1予定を返す | {intent: schedule_query, scope: next, conf: 0.92} | ✅正確な応答 |
| E2E-04 | 「来週の予定見せて」 | 来週分一覧 | {intent: schedule_query, scope: week, conf: 0.94} | ✅正確な応答 |
| E2E-05 | 「予定ってある？」 | LLMに委ねるか確認を促す | {intent: schedule_query, scope: unspecified, conf: 0.60} | 🟡低信頼は人間判断へ |
| E2E-06 | 「最近どう？」 | LLM応答（会話） | {intent: not_schedule, conf: 0.98} | ✅LLM応答のみ |

### 10.3 レイテンシテスト

- **判定器のみ**: <= 100ms
- **判定 + ルール処理**: <= 200ms
- **判定 + LLM処理**: 既存と同等（LLMが支配的）

### 10.4 ロギング・監査テスト

- `logs/classifier_events.log` が正しく生成されること
- JSON形式で必須フィールド（timestamp, intent, confidence等）が含まれること
- 1週間の運用で False Positive を集計し < 2% であること

---

## 11. 実装ロードマップ

### Phase 1: プロトタイプ・設計（1-2週）
- [ ] 判定器のプロンプト設計・チューニング
- [ ] 評価セット（100発話）の準備
- [ ] フロー図・シーケンス図の詳細化

### Phase 2: 実装・統合（2-3週）
- [ ] `classify_schedule_intent()` 関数実装（LLMベース）
- [ ] ロギング機構実装（`log_event()` 等）
- [ ] `api_chat` フローへの統合
- [ ] フォールバック・エラーハンドリング

### Phase 3: テスト・評価（1-2週）
- [ ] 評価セットでのテスト実行
- [ ] 精度測定・分析
- [ ] 信頼度閾値の最適化

### Phase 4: 運用準備（1週）
- [ ] UI/設定画面の更新（閾値変更可能に）
- [ ] ドキュメント作成
- [ ] 運用チェックリスト作成

### Phase 5: リリース・監視（継続）
- [ ] A/B テスト（ルールのみ vs ルール+判定器）
- [ ] ユーザ満足度測定
- [ ] 定期的な精度レビューと改善

---

## 12. 用語定義

| 用語 | 定義 |
|------|------|
| **判定器（Classifier）** | LLMをバックエンドとする、ユーザ発話の意図分類モジュール |
| **Intent（意図）** | 発話の種類（schedule_query / not_schedule） |
| **Scope（スコープ）** | 問い合わせの時間範囲（today / tomorrow / week 等） |
| **Confidence（信頼度）** | 判定結果の確信度（0.0 ~ 1.0） |
| **Threshold（閾値）** | Confidence がこれ以上なら schedule_query と判定（初期値 0.80） |
| **False Positive** | 実は予定問い合わせではないのに schedule_query と判定すること |
| **False Negative** | 実は予定問い合わせなのに not_schedule と判定すること |
| **Safety Instruction** | LLMに対する「予定事実を生成するな」という制約プロンプト |

---

## 13. 今後の拡張性

- 複数言語対応（英語、中国語等）
- 判定器の微調整・再学習（運用データを基に）
- キャッシング機構の導入（頻出発話の高速化）
- A/B テストフレームワークの拡充
- ユーザ満足度フィードバック機構

---

**承認者**: TBD  
**作成日**: 2026-01-02  
**版番**: 1.0
