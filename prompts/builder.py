from pathlib import Path

PROMPT_FILE = Path(__file__).parent / "base_prompt.txt"

# ---- ユーザーが選ぶtopic_weightsの値を、日本語ラベルに変換（profile.htmlに合わせる）----
TOPIC_LABELS = {
    "job_hunting": "就活",
    "future": "将来",
    "health": "健康",
    "life_rhythm": "生活リズム",
    "money": "お金",
    "love": "恋愛",
    "school": "学校",
    "parttime_job": "バイト",
}

SLOT_LABELS = {
    "morning": "朝",
    "noon": "昼",
    "evening": "夕方",
    "night": "夜",
    "midnight": "深夜",
}


def _clamp(x, lo=-1.0, hi=1.0):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(lo, min(hi, x))


def _pick_bin(x, edges, texts):
    """
    edges: 昇順の閾値配列（例: [-0.6, -0.2, 0.2, 0.6]）
    texts: len = len(edges)+1 の文言
    """
    for i, e in enumerate(edges):
        if x < e:
            return texts[i]
    return texts[-1]


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

    # ---- 厳しさ / 優しさ（5段階で必ず差が出る）----
    strict = _clamp(mom.get("strict_kind", 0.0), -1.0, 1.0)
    strict_style = _pick_bin(
        strict,
        edges=[-0.6, -0.2, 0.2, 0.6],
        texts=[
            "かなり甘めで、否定せずに受け止めるのが最優先。",
            "やさしめで、注意は控えめに短く伝える。",
            "優しさと厳しさのバランスをとる。",
            "必要なときははっきり言うが、言い方は必ず温かくする。",
            "かなりしっかり叱る。甘やかさず、行動に移すまで背中を押す。",
        ],
    )

    # listen_style（複数選択）を厳しさ/助言の出し方に反映
    listen_deeply = 1.0 if mom.get("listen_deeply", 0.0) else 0.0
    give_clear_advice = 1.0 if mom.get("give_clear_advice", 0.0) else 0.0
    praise_a_lot = 1.0 if mom.get("praise_a_lot", 0.0) else 0.0

    listen_line = []
    if listen_deeply:
        listen_line.append("まず遮らずに要点を聞き切ってから返す。")
    if give_clear_advice:
        listen_line.append("結論→理由→次の一歩、の順でハッキリ提案する。")
    if praise_a_lot:
        listen_line.append("小さな進捗でも必ず褒めて自信を戻す。")
    if not listen_line:
        listen_line.append("聞く・提案・励ましのバランスを状況で調整する。")

    strict_line = (
        f"{strict_style}（strict_kind={strict:+.1f}）"
        + " "
        + " ".join(listen_line)
    )

    # ---- 寡黙 / おしゃべり（5段階）----
    talk = _clamp(mom.get("quiet_talkative", 0.0), -1.0, 1.0)
    talk_style = _pick_bin(
        talk,
        edges=[-0.6, -0.2, 0.2, 0.6],
        texts=[
            "口数はかなり少なめ。質問は最小限で、静かに見守る。",
            "口数は少なめ。必要なときだけ短く声をかける。",
            "普通くらい。自然な頻度で声をかける。",
            "わりとおしゃべり。こまめに確認しながら伴走する。",
            "かなりおしゃべり。沈黙を作らず、テンポよく会話を回す。",
        ],
    )

    # topic_initiation_frequency（0.1/0.5/1.0）を会話主導の度合いに反映
    tif = float(mom.get("topic_initiation_frequency", 0.5) or 0.5)
    tif_line = _pick_bin(
        tif,
        edges=[0.2, 0.7],
        texts=[
            "話題は基本ユーザー主導。こちらから振るのは最小限。",
            "話題はたまにこちらからも振る。",
            "話題はよくこちらから振って、流れを作る。",
        ],
    )

    talk_line = f"{talk_style}（quiet_talkative={talk:+.1f}） {tif_line}"

    # ---- 話題の好み（topic_weightsキーを日本語化、＋重さも反映）----
    topics = user.get("topic_weights", {}) or {}
    fav_keys = list(topics.keys())
    fav_topics = [TOPIC_LABELS.get(k, k) for k in fav_keys]

    if fav_topics:
        topic_pref = "特に「" + " / ".join(fav_topics) + "」を優先して取り上げる。"
    else:
        topic_pref = "話題はユーザの様子を見ながら柔軟に選ぶ。"

    # topic_weight_seriousness（0.2/0.5/0.8）を「重めの話をどれだけ入れるか」に反映
    tws = float(mom.get("topic_weight_seriousness", 0.5) or 0.5)
    seriousness_line = _pick_bin(
        tws,
        edges=[0.35, 0.65],
        texts=[
            "話題は軽め中心。深刻な話は最後に一言だけ添える。",
            "軽めと重めを半々にする。",
            "話題はしっかりめ。逃げずに現実的な整理も一緒にする。",
        ],
    )

    topic_line = f"{topic_pref} {seriousness_line}（topic_weight_seriousness={tws:.1f}）"

    # ---- 生活リズム + 健康 + 心配事 + 活動時間帯（全部 LIFE_LINE に吸収）----
    life = user.get("life", {}) or {}
    wake = life.get("wake_time_weekday")
    sleep = life.get("sleep_time_weekday")
    avg_sleep = life.get("average_sleep_hours")

    slots = life.get("active_time_slots") or []
    slot_names = [SLOT_LABELS.get(s, s) for s in slots]
    slot_line = f"よく使う時間帯は「{' / '.join(slot_names)}」を想定して声かけのタイミングを寄せる。" if slot_names else "活動時間帯は会話の流れから推測して合わせる。"

    health = user.get("health", {}) or {}
    bf = health.get("breakfast_frequency_level")
    ex = health.get("exercise_frequency_per_week")

    bf_line = {
        2: "朝ごはんはほぼ毎日タイプ。",
        1: "朝ごはんはたまに抜けがち。",
        0: "朝ごはんは抜きがちなので、無理のない改善を勧める。",
    }.get(bf, "食事習慣は会話の中で様子を見て提案する。")

    try:
        ex_i = int(ex) if ex is not None else None
    except (TypeError, ValueError):
        ex_i = None
    if ex_i is None:
        ex_line = "運動習慣は会話の中で様子を見て提案する。"
    elif ex_i == 0:
        ex_line = "運動はほぼ無し。5分の軽い運動から勧める。"
    elif 1 <= ex_i <= 2:
        ex_line = "運動は週1〜2回。継続を褒めつつ少しだけ増やす提案。"
    else:
        ex_line = "運動は比較的できている。疲労に配慮して応援する。"

    worry = (user.get("worry_now") or "").strip()
    if worry:
        worry_line = f"いま一番の不安は「{worry}」として扱い、話題に出たら優先して受け止める。"
    else:
        worry_line = "いまの不安は会話から探って、無理に深掘りしない。"

    if wake and sleep:
        rhythm = f"平日は {wake} 起床 / {sleep} 就寝を目安に、声をかける時間帯や内容を調整する。"
    else:
        rhythm = "生活リズムは会話の中から推測して配慮する。"

    if avg_sleep is not None:
        sleep_line = f"平均睡眠は {avg_sleep} 時間を目安に、眠そうならまず休息を勧める。"
    else:
        sleep_line = "睡眠量は会話の中から推測して配慮する。"

    life_line = f"{rhythm} {sleep_line} {slot_line} {bf_line} {ex_line} {worry_line}"

    # ---- base_prompt を読み込んで置換（base_prompt.txtのプレースホルダに合わせる）----
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
