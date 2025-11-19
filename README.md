# Mom-Elyza: 日本のお母さんAI

このリポジトリは、ローカルで動作する「日本のお母さん風エージェント」を構築するためのコードと手順をまとめたものです。

- モデル: Llama-3-ELYZA-JP-8B
- ランタイム: Ollama
- ローカルのみで動作（APIキー不要）

---

## セットアップ

ご利用のOSごとに README を参照してください。

- macOS: [README_mac.md](./README_mac.md)
- Windows: [README_windows.md](./README_windows.md)

---

## ファイル構成（例）

- `Modelfile`  
  お母さんの性格や会話方針を定義した Ollama 用設定。

- `chat_mom.py`  
  ローカルの Mom-Elyza と対話するためのシンプルな CLI。

- `logs/`  
  会話ログ（`.gitignore` 推奨）。

---

## ライセンス / 注意事項

- モデル利用規約やライセンスは、Llama3 / ELYZA の規約に従ってください。
- ログには個人情報を書きすぎないよう注意してください。
