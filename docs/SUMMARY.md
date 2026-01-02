# Project Summary

簡潔な要約のみを残します。詳細なバグフィックスや個別ドキュメントは削除しました。

- **主要ファイル**:
  - `app.py`: Flask API とセッション管理、LLM 呼び出しの中心。
  - `classifier.py`: スケジュール意図の判定ロジック。
  - `prompts/base_prompt.txt`: システムプロンプト（母親トーンのルール）。
  - `chat_mom.py`: CLI 用の簡易チャットフロー。

- **ログ**: `logs/` は `.gitignore` に追加済みで、ワークツリーに残す必要はありません。公開前に不要なログは削除してください。

- **テスト**: `test_api.py`, `test_classifier.py` が存在します。必要に応じて実行・調整してください。

- **ブランチ保存**: 作業中の状態は `save/current-state-2026-01-02` ブランチに保存済みです。

必要なら、この `SUMMARY.md` を起点に重要なドキュメント（README、運用手順）を再作成します。
