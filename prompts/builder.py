from pathlib import Path

PROMPT_FILE = Path(__file__).parent / "base_prompt.txt"

# ============================================================
# 変数名と設定値の対応表（UIで設定 → mom_config.json → プロンプト）
# ============================================================
# | UI項目名             | config key                  | 値の範囲         | プロンプト変数       | 備考                    |
# |----------------------|-----------------------------|------------------|----------------------|------------------------|
# | 口調                 | dialect_type                | normal/kansai/hakata | {{DIALECT_LINE}}  |                        |
# | 厳しい←→優しい       | strict_kind                 | -1.0 〜 1.0      | {{STRICT_LINE}}      |                        |
# | 寡黙←→おしゃべり     | quiet_talkative             | -1.0 〜 1.0      | {{TALK_LINE}}        |                        |
# | じっくり聞いてほしい   | listen_deeply               | 0.0 or 1.0       | {{LISTEN_STYLE_LINE}}|                        |
# | はっきりアドバイス     | give_clear_advice           | 0.0 or 1.0       | {{LISTEN_STYLE_LINE}}|                        |
# | とにかく褒めて         | praise_a_lot                | 0.0 or 1.0       | {{LISTEN_STYLE_LINE}}|                        |
# | 話題を振る頻度         | topic_initiation_frequency  | 0.1/0.5/1.0      | {{TOPIC_FREQ_LINE}}  |                        |
# | 話題の重さ             | topic_weight_seriousness    | 0.2/0.5/0.8      | {{TOPIC_WEIGHT_LINE}}|                        |
# | (プロフィール)話題     | user.topic_weights          | dict             | (会話終了ナッジで使用) | app.py側で処理         |
# | (プロフィール)生活     | user.life                   | dict             | {{LIFE_LINE}}        |                        |
# ============================================================
# 
# ※ 話題の好み(topic_weights)は、会話初期には使用せず、
#    会話終了時のナッジ（app.py の get_topic_nudge_message）で順番に聞く形で活用。
#    会話初期はたわいもない会話から始める設計。
# ============================================================


def build_prompt(config: dict) -> str:
    """
    フォーム設定(config)をもとに SYSTEM プロンプトを組み立てる。
    
    各設定値に応じて条件分岐でプロンプト文を決定し、
    base_prompt.txt のプレースホルダーを置換する。
    """

    user = config["user"]
    mom = config["mother_model"]

    nickname = user.get("nickname") or "あなた"

    # ============================================================
    # 1. 方言 (dialect_type) → {{DIALECT_LINE}}
    # ============================================================
    dialect = mom.get("dialect_type", "normal")
    if dialect == "kansai":
        dialect_line = "やわらかい関西弁混じりで話す。"
    elif dialect == "hakata":
        dialect_line = "やわらかい博多弁混じりで話す。"
    else:
        dialect_line = "標準語で話す。"

    # ============================================================
    # 2. 厳しさ/優しさ (strict_kind: -1〜1) → {{STRICT_LINE}}
    #    -1: 厳しい, 0: バランス, 1: 優しい
    # ============================================================
    strict = mom.get("strict_kind", 0.0)
    if strict > 0.3:
        # 優しい寄り
        strict_line = "かなり甘めで、あまり強くは叱らない。褒めることを優先する。"
    elif strict < -0.3:
        # 厳しい寄り
        strict_line = "かなり厳しめのお母さん。必要なときははっきり叱る。甘やかしすぎない。"
    else:
        strict_line = "優しさと厳しさのバランスをとる。"

    # ============================================================
    # 3. 寡黙/おしゃべり (quiet_talkative: -1〜1) → {{TALK_LINE}}
    #    -1: 寡黙, 0: 普通, 1: おしゃべり
    # ============================================================
    talk = mom.get("quiet_talkative", 0.0)
    if talk > 0.3:
        talk_line = "わりとおしゃべりで、こまめに話題を振る。沈黙が続かないようにする。"
    elif talk < -0.3:
        talk_line = "口数は少なめで、必要なときにだけ穏やかに声をかける。聞き役に徹することが多い。"
    else:
        talk_line = "普通くらいの話しやすさで、自然な頻度で話す。"

    # ============================================================
    # 4. 相談スタイル (listen_deeply, give_clear_advice, praise_a_lot)
    #    → {{LISTEN_STYLE_LINE}}
    #    複数選択可能なので、選択されたものを組み合わせる
    # ============================================================
    listen_deeply = mom.get("listen_deeply", 0.0)
    give_clear_advice = mom.get("give_clear_advice", 0.0)
    praise_a_lot = mom.get("praise_a_lot", 0.0)

    listen_style_parts = []
    if listen_deeply >= 1.0:
        listen_style_parts.append("相談にはじっくり耳を傾け、すぐに解決策を出さずにまず気持ちを受け止める")
    if give_clear_advice >= 1.0:
        listen_style_parts.append("アドバイスを求められたらはっきり具体的に伝える")
    if praise_a_lot >= 1.0:
        listen_style_parts.append("とにかく褒めて認めることを心がけ、自己肯定感を高める")

    if listen_style_parts:
        listen_style_line = "。".join(listen_style_parts) + "。"
    else:
        listen_style_line = "相談には共感しつつ、適度にアドバイスも交える。"

    # ============================================================
    # 5. 話題を振る頻度 (topic_initiation_frequency: 0.1/0.5/1.0)
    #    → {{TOPIC_FREQ_LINE}}
    # ============================================================
    topic_freq = mom.get("topic_initiation_frequency", 0.5)
    if topic_freq >= 0.8:
        topic_freq_line = "積極的に話題を振り、会話をリードする。"
    elif topic_freq <= 0.2:
        topic_freq_line = "こちらから話題を振ることは最小限にし、ユーザの話を待つ。"
    else:
        topic_freq_line = "たまに話題を振るが、基本はユーザのペースに合わせる。"

    # ============================================================
    # 6. 話題の重さ (topic_weight_seriousness: 0.2/0.5/0.8)
    #    → {{TOPIC_WEIGHT_LINE}}
    # ============================================================
    topic_weight = mom.get("topic_weight_seriousness", 0.5)
    if topic_weight >= 0.6:
        topic_weight_line = "将来や悩みなど、しっかりした話題も積極的に取り上げる。"
    elif topic_weight <= 0.3:
        topic_weight_line = "軽い雑談や日常の話題を中心にし、重い話題は控えめにする。"
    else:
        topic_weight_line = "軽い話と真面目な話を半々くらいのバランスで話す。"

    # ============================================================
    # 7. 話題の振り方 (user.topic_weights) → {{TOPIC_LINE}}
    #    ※ 会話初期はたわいもない会話から始める

    # ============================================================
    # 会話初期は軽い雑談から始めるように指示
    topic_line = "会話の初めは軽い雑談（天気・最近どう？・体調など）から自然に始める。いきなり深い話題には入らない。"

    # ============================================================
    # 8. 生活リズム (user.life) → {{LIFE_LINE}}
    # ============================================================
    life = user.get("life", {})
    wake = life.get("wake_time_weekday")
    sleep = life.get("sleep_time_weekday")
    if wake and sleep:
        life_line = f"平日は {wake} 起床 / {sleep} 就寝をなんとなく意識して、声をかける時間帯や内容を調整する。"
    else:
        life_line = "生活リズムは会話の中から自然に推測して配慮する。"

    # ============================================================
    # base_prompt.txt を読み込んでプレースホルダーを置換
    # ============================================================
    template = PROMPT_FILE.read_text(encoding="utf-8")

    system_prompt = (
        template
        .replace("{{NICKNAME}}", nickname)
        .replace("{{DIALECT_LINE}}", dialect_line)
        .replace("{{STRICT_LINE}}", strict_line)
        .replace("{{TALK_LINE}}", talk_line)
        .replace("{{LISTEN_STYLE_LINE}}", listen_style_line)
        .replace("{{TOPIC_FREQ_LINE}}", topic_freq_line)
        .replace("{{TOPIC_WEIGHT_LINE}}", topic_weight_line)
        .replace("{{TOPIC_LINE}}", topic_line)
        .replace("{{LIFE_LINE}}", life_line)
    )

    return system_prompt.strip()


def debug_show_prompt(config: dict) -> None:
    """デバッグ用: 生成されるプロンプトを表示"""
    prompt = build_prompt(config)
    print("=" * 60)
    print("生成されたシステムプロンプト:")
    print("=" * 60)
    print(prompt)
    print("=" * 60)
