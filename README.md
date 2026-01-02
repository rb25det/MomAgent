
# MomAgent — 日本のお母さんAI（簡潔版）

このリポジトリは、ローカルで動作する母親風チャットエージェントのプロトタイプです。

- モデルランタイム: Ollama（ローカル実行を想定）
- システムプロンプト: `prompts/base_prompt.txt`

重要: このブランチ `save/current-state-2026-01-02` に作業中の状態を保存しています。

簡単な使い方:

1. Ollama をローカルで起動し、`Modelfile` に記載のモデルをロードする。
2. 依存関係を用意（Python 仮想環境を推奨）。
3. 開発用サーバを起動して API を使うか、`chat_mom.py` で CLI 対話を行う。

例: サーバ起動（開発）

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # 無ければ必要なパッケージを手動で
python app.py
```

ログとプライバシー:

- `logs/` は `.gitignore` に追加済みです。公開する前にログを確認・匿名化してください。

整理方針:

- 冗長なドキュメントは削除し、`docs/SUMMARY.md` に簡潔な概要をまとめました。

問題や要望があれば `docs/SUMMARY.md` を起点に再作成します。
