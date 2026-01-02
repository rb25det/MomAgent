# MomAgent — Ubuntu 設定メモ

このファイルは Ubuntu / Debian 系でローカル実行する際の簡潔な手順です。

前提:
- Ubuntu 20.04 以降
- Ollama は公式手順に従ってインストールしてください（公式ダウンロードページ参照）。

1) システムの準備

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl
```

2) Ollama をインストール

- Ollama の Linux インストール手順に従ってください（公式ガイド参照）。
- インストール後、`ollama serve` で起動するか、システムサービスとして常駐させます。

3) プロジェクトの準備

```bash
git clone <repo-url>
cd MomAgent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4) モデルを取得（初回）

```bash
ollama pull dsasai/llama3-elyza-jp-8b
ollama create elyza-mom -f Modelfile
```

5) 実行例

- CLI:

```bash
python3 chat_mom.py
```

- サーバ起動:

```bash
python3 app.py
```

注意:
- `logs/` は `.gitignore` に含まれています。公開前に不要ログの削除や匿名化を行ってください。
