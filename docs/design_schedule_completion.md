# 予定補完機能 詳細設計

## 目的
- UIで追加/編集された予定の未入力項目を、会話で補完する。
- 補完対象項目は「お母さん設定」で切り替える。
- 補完結果は該当する予定に保存し、一覧/編集に整合的に反映する。

## 対象範囲
- サーバ: `app.py`
- テンプレート: `templates/mom_settings.html`, `templates/schedule_list.html`, `templates/schedule_edit.html`
- 補助: `prompts/builder.py`（補完方針の文言をプロンプトに反映する場合）

## データモデル
### 予定データ（`session["schedules"]`）
既存項目:
- `date` (string, required)
- `time` (string, required)
- `content` (string, required)
- `priority` (string, default "2")
- `remind_value` (string/number, optional)
- `remind_unit` (string, optional)
- `created_at` (string, ISO)

追加項目（補完対象）:
- `deadline` (string, optional) 例: "2025-01-31"
- `duration_minutes` (string/number, optional) 例: "60"
- `location` (string, optional) 例: "渋谷オフィス"
- `notes` (string, optional) 例: "資料印刷"

### 補完設定（`session["mom_settings"]`）
追加項目:
- `schedule_completion_fields` (list of string)
  - 例: ["remind_value", "deadline", "duration_minutes", "location", "notes"]

### 補完状態（`session["schedule_completion"]`）
- `index` (int) 予定のインデックス
- `pending_fields` (list of string) 未入力項目のキュー
- `current_field` (string) 現在質問中の項目
- `last_prompt` (string) 直近の補完質問（任意）

## 画面設計（mom_settings）
### 追加UI
- お母さん設定に「予定の補完対象」を追加。
- チェックボックスで選択:
  - `remind_value` / `remind_unit`
  - `deadline`
  - `duration_minutes`
  - `location`
  - `notes`
- 送信時は `mom_settings` の `schedule_completion_fields` として保存。

## 予定編集画面
- 追加項目の表示/編集を可能にする。
- 既存項目と同列で入力欄を追加。
- 表示のみで十分な場合は、編集は後回しでも可。

## API設計
### 既存: `POST /api/chat`
- 予定補完モードを優先。
- `schedule_completion` が存在する場合、通常のLLM応答ではなく補完質問/保存処理を行う。

### 追加: 補完フロー
1) `schedule_completion` が存在しない場合:
   - 最新の予定（または未補完の予定）を探索。
   - 未入力項目があり、`mom_settings.schedule_completion_fields` に含まれる場合は補完モード開始。
2) 補完モード開始:
   - `pending_fields` を生成。
   - `current_field` をセットし、質問文を返す。
3) 補完モード継続:
   - ユーザー回答を `current_field` に保存。
   - 次の `pending_fields` を取り出し、次の質問を返す。
4) 補完完了:
   - すべて埋まったら予定内容を要約して確認。
   - 同意が得られたら `schedule_completion` をクリア。

## 予定補完対象の抽出ロジック
- `schedules` を新しい順に走査。
- 以下の条件で未入力判定:
  - `remind_value`: 空 or None
  - `remind_unit`: 空 or None（`remind_value` がある場合にのみ必須）
  - `deadline`: 空 or None
  - `duration_minutes`: 空 or None
  - `location`: 空 or None
  - `notes`: 空 or None
- `mom_settings.schedule_completion_fields` に含まれない項目は無視。

## 会話ロジック
### 質問テンプレート
- `deadline`: "それ、いつまでに終わらせたい？"
- `duration_minutes`: "どれくらい時間かかりそう？"
- `location`: "場所はどこやっけ？"
- `notes`: "準備するものある？"
- `remind_value`: "何時間前（何日前）に声かけしたらええ？"
- `remind_unit`: `remind_value` 回答に応じて補足

### まとめ確認テンプレート
- "じゃあ、{date} {time} に {content}、場所は {location}、所要時間は {duration_minutes} 分、締切は {deadline}、リマインドは {remind_value}{remind_unit} 前で合ってる？"

## LLM連携方針
- 補完モード中は LLM への問い合わせを行わず、ルールベースで質問。
- 補完完了後に通常のLLMチャットへ復帰。
- 予定を毎ターン必ず認知させる場合は、`ask()` のプロンプトに予定一覧を挿入（別設計）。

## 例外/エラー処理
- 補完中にユーザーが "やめる" "キャンセル" などを発言した場合:
  - `schedule_completion` を破棄し、通常チャットへ復帰。
- 未入力項目が不明確な回答の場合:
  - 同じ質問を言い換えて再質問。
- 予定が空のとき:
  - 補完モードは起動しない。

## 画面反映・整合性
- 補完結果は `session["schedules"][index]` を直接更新。
- `schedule_list` と `schedule_edit` で値が確認できる。
- 既存の編集保存フローは維持。

## 移行・互換
- 既存予定に新規項目が存在しない場合は補完対象として扱う。
- 新項目は未設定扱いで問題なし。

## テスト観点（手動）
- 予定追加後、補完対象項目が空の場合に会話で質問が出る。
- 回答後、一覧/編集に反映される。
- 補完対象に設定していない項目は質問されない。
- 補完をキャンセルすると通常会話に戻る。
