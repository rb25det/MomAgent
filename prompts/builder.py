from pathlib import Path

PROMPT_FILE = Path(__file__).parent / "base_prompt.txt"


def build_prompt(config: dict) -> str:
    """フォーム設定(config)をもとに SYSTEM プロンプトを組み立てる"""

    user = config["user"]
    mom = config["mother_model"]

    nickname = user.get("nickname") or "あなた"

    # ---- 方言ライン ----
    dialect = mom.get("dialect_type", "normal")
    if dialect == "kansai":
        dialect_line = "やわらかい関西弁混じりで話す。"
    elif dialect == "hakata":
        dialect_line = "やわらかい博多弁混じりで話す。"
    else:
        dialect_line = "標準語で話す。"

    # ---- 厳しさ / 優しさ ----
    strict = mom.get("strict_kind", 0.0)
    if strict > 0.3:
        strict_line = "基本は優しいが、必要なときははっきり叱る。"
    elif strict < -0.3:
        strict_line = "かなり甘めで、あまり強くは叱らない。"
    else:
        strict_line = "優しさと厳しさのバランスをとる。"

    # ---- 寡黙 / おしゃべり ----
    talk = mom.get("quiet_talkative", 0.0)
    if talk > 0.3:
        talk_line = "わりとおしゃべりで、こまめに話題を振る。"
    elif talk < -0.3:
        talk_line = "口数は少なめで、必要なときにだけ穏やかに声をかける。"
    else:
        talk_line = "普通くらいの話しやすさで、自然な頻度で話す。"

    # ---- 話題の好み ----
    topics = user.get("topic_weights", {})
    fav_topics = list(topics.keys())
    if fav_topics:
        # 日本語ラベルをそのまま使うならこのままでOK
        topic_line = (
            "特に「" + " / ".join(fav_topics) + "」あたりの話題をよく取り上げる。"
        )
    else:
        topic_line = "話題はユーザの様子を見ながら柔軟に選ぶ。"

    # ---- 生活リズム ----
    life = user.get("life", {})
    wake = life.get("wake_time_weekday")
    sleep = life.get("sleep_time_weekday")
    if wake and sleep:
        life_line = f"平日は {wake} 起床 / {sleep} 就寝をなんとなく意識して、声をかける時間帯や内容を調整する。"
    else:
        life_line = "生活リズムは会話の中から自然に推測して配慮する。"

    # ---- base_prompt を読み込んで置換 ----
    template = PROMPT_FILE.read_text(encoding="utf-8")

    system_prompt = (
        template
        .replace("{{NICKNAME}}", nickname)
        .replace("{{DIALECT_LINE}}", dialect_line)
        .replace("{{STRICT_LINE}}", strict_line)
        .replace("{{TALK_LINE}}", talk_line)
        .replace("{{TOPIC_LINE}}", topic_line)
        .replace("{{LIFE_LINE}}", life_line)
    )

    return system_prompt.strip()
