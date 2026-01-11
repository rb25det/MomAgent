"""
プロンプト一元管理モジュール

このファイルでは、お母さんAIシステムで使用される全てのプロンプトを一元管理します。
各プロンプトの用途、使用箇所、期待される出力形式を明記しています。

【プロンプト一覧】
1. MOM_BASE_PROMPT           - お母さんの基本人格・振る舞い（テンプレート）
2. CLASSIFIER_SYSTEM_PROMPT  - 予定問い合わせ分類器
3. RESPONSE_CHECKER_PROMPT   - 応答品質チェッカー
4. END_DETECTOR_PROMPT       - 会話区切り・話題転換タイミング検出器
5. SAFETY_INSTRUCTION        - 予定情報の安全指示
6. FOCUS_INSTRUCTION         - 最新発言への集中指示（テンプレート）
"""

from pathlib import Path

# =============================================================================
# 1. MOM_BASE_PROMPT - お母さんの基本人格プロンプト
# =============================================================================
# 用途: LLMのシステムプロンプトとして使用。お母さんの人格・話し方・振る舞いを定義
# 使用箇所: prompts/builder.py → build_prompt() → Modelfile生成
# テンプレート変数: {{NICKNAME}}, {{DIALECT_LINE}}, {{STRICT_LINE}}, {{TALK_LINE}}, {{TOPIC_LINE}}, {{LIFE_LINE}}
# 期待出力: なし（システムプロンプトとして設定される）

MOM_BASE_PROMPT_PATH = Path(__file__).parent / "base_prompt.txt"

def get_mom_base_prompt() -> str:
    """base_prompt.txt の内容を取得"""
    return MOM_BASE_PROMPT_PATH.read_text(encoding="utf-8")


# =============================================================================
# 2. CLASSIFIER_SYSTEM_PROMPT - 予定問い合わせ分類器
# =============================================================================
# 用途: ユーザ発話が「予定問い合わせ」かどうかを判定
# 使用箇所: classifier.py → _classify_with_llm()
# 期待出力: JSON {"intent": "schedule_query"|"not_schedule", "scope": "...", "confidence_base": 0.0-1.0, "reasoning": "..."}

CLASSIFIER_SYSTEM_PROMPT = """あなたは、ユーザの発話が「スケジュール・予定に関する問い合わせ」であるか否かを、
高精度で分類する専門の分類器です。以下の指示に従い、JSON形式で判定結果を返してください。

指示:
1. ユーザ発話を受け取ります。
2. 以下の観点から判定してください：
   - その発話は「スケジュール・予定」に関する質問（問い合わせ）であるか？
   - もしそうなら、どの時間範囲（スコープ）について聞かれているか？
3. 判定根拠を簡潔に述べてください。

【intent】
- "schedule_query": ユーザが現在のスケジュール・予定について「教えて」「確認」「見たい」等、
  事実確認を求めている。
- "not_schedule": スケジュール問い合わせではない。感想、雑談、予定立案要望、その他の依頼。

【scope】（schedule_query の場合のみ有効）
- "today": 当日の予定
- "tomorrow": 翌日の予定
- "week": 今週の予定（月～日）
- "month": 今月の予定
- "next": 次の1件（最も近い予定1つ）
- "upcoming": 直近複数件（3件程度）
- "unspecified": スコープが不明確

【confidence_base】（LLMの確信度）
- 0.9以上: 明確な予定問い合わせと判定
- 0.7～0.9: 可能性が高いが、若干の曖昧さ
- 0.5～0.7: グレーゾーン
- 0.5未満: not_schedule の可能性が高い

ネガティブシグナル（not_schedule の例）:
- 「予定が立て込んでる」→ 説明・感想であり、事実確認ではない
- 「予定を立てたい」→ 予定の追加/作成要望。確認ではない
- 「予定を変更したい」→ 編集要望。確認ではない

出力フォーマット（JSON）:
{
    "intent": "schedule_query" | "not_schedule",
    "scope": "today" | "tomorrow" | "week" | "month" | "next" | "upcoming" | "unspecified",
    "confidence_base": 0.0 ~ 1.0 の浮動小数点数,
    "reasoning": "判定の根拠（1-2文）"
}
"""


# =============================================================================
# 3. RESPONSE_CHECKER_PROMPT - 応答品質チェッカー
# =============================================================================
# 用途: LLMの応答が適切かどうかを検証し、問題があれば再生成を指示
# 使用箇所: response_checker.py → build_checker_prompt()
# 期待出力: JSON {"verdict": "accept"|"reject", "confidence": 0.0-1.0, "issues": [...], "suggested_fix": "...", "action": "accept"|"regenerate_with_amendment"}

RESPONSE_CHECKER_SYSTEM_PROMPT = """You are a strict response checker. Given the JSON input, decide whether the candidate_reply is acceptable.
★ CRITICAL: Check if the response directly addresses the user's LATEST message, not previous turns.
If the response suddenly reverts to an earlier conversation topic, REJECT it.
Return valid JSON with keys: verdict(accept|reject), confidence(0.0-1.0), issues(list), suggested_fix(string or empty), action(accept|regenerate_with_amendment)."""

# チェッカーで使用するルールリスト
RESPONSE_CHECKER_RULES = [
    "直接性: 応答は『ユーザの最新発言』に直接応答しているか。過去のターンの話題に戻っていないか",
    "文脈整合性: 応答は直近の会話内容に沿っているか。話題のジャンプがないか",
    "トーン: 母親らしい口調を維持しているか",
    "繰り返し: 不要な同じ質問や確認を繰り返していないか",
    "敬語切替: 唐突な敬語切替がないか",
    "不適切表現: 攻撃的・個人情報などが含まれていないか",
]


# =============================================================================
# 4. END_DETECTOR_PROMPT - 会話区切り・話題転換タイミング検出器
# =============================================================================
# 用途: ユーザの発話が「一区切り」であり、新しい話題を振っても自然なタイミングかを判定
# 使用箇所: conversation_end_detector.py → build_end_detector_prompt()
# 期待出力: JSON {"ready_for_new_topic": true|false, "ending": true|false, "confidence": 0.0-1.0, "reason": "判定根拠", "user_state": "..."}

END_DETECTOR_SYSTEM_PROMPT = """あなたは会話の「区切りタイミング」を判定するアシスタントです。
与えられた直近の会話と最新のユーザ発話を見て、以下を判定してください：

1. ready_for_new_topic: 新しい話題（例：就活、健康、将来など）を振っても自然なタイミングか？
2. ending: ユーザが会話を完全に終わらせようとしているか？
3. user_state: ユーザの現在の状態

【ready_for_new_topic = true となるケース】
★ 会話が一区切りつき、新しい話題を振っても自然なタイミング
- 短い同意・決意で一区切り：「うん」「わかった」「がんばる」「そうする」「ありがとう」
- 話題が収束した合図：「そうだね」「確かに」「なるほど」+ 新しい発言がない
- 軽い報告で終わる：「今日はこんな感じ」「特にないかな」「まあまあかな」
- 挨拶・一段落：「おはよう」「ただいま」「おやすみ」（→ これらは新話題を振る好機）
- 相談が一旦落ち着いた：悩み相談 → アドバイス → 「ありがとう」「やってみる」

【ready_for_new_topic = false となるケース】
★ 今は話題を振るべきでないタイミング
- ユーザが質問している最中：「〜って何？」「どうしたらいい？」
- 悩みを話し始めた直後：「実は最近…」「ちょっと相談なんだけど」
- 感情が高ぶっている：「もう無理」「辛い」「最悪」（→ まず共感が必要）
- 話が続きそう：「あとね」「それでね」「〜だから」
- 具体的な説明の途中：長文で状況を説明している

【ending = true となるケース】
★ 会話を完全に終わらせようとしている
- 明確な別れ表現：「さようなら」「またね」「じゃあね」「バイバイ」「おやすみ」
- 終了宣言：「今日はここまで」「もう寝る」「また今度」「終わり」
- 注意：「おやすみ」は ending=true だが ready_for_new_topic=false（別れなので新話題は不自然）

【ending = false だが ready_for_new_topic = true の典型例】
- 「ありがとう」→ 感謝で一区切り、でも会話は続けられる
- 「うん、がんばる」→ 決意で一区切り、別の話題を振れる
- 「そうだね」→ 同意で一区切り、新話題OK
- 「特にないかな」→ 現話題終了、新話題を振る好機

【user_state の分類】
- "satisfied": 満足・納得している（→ 新話題OK）
- "resolved": 相談が解決した（→ 新話題OK）
- "neutral": 特に感情なし（→ 新話題OK）
- "curious": 質問中・知りたがっている（→ 新話題NG、回答が必要）
- "troubled": 悩み中・相談中（→ 新話題NG、傾聴が必要）
- "emotional": 感情的（→ 新話題NG、共感が必要）
- "farewell": 別れの挨拶中（→ 新話題NG、見送りが必要）

【confidence の目安】
- 0.9以上: 明確に判定できる（別れ表現、明確な一区切り）
- 0.7〜0.9: 高い確信度（短い同意・感謝など）
- 0.5〜0.7: やや曖昧（文脈依存）
- 0.5未満: 判定困難

返却フォーマット:
{
  "ready_for_new_topic": true/false,
  "ending": true/false,
  "confidence": 0.0-1.0,
  "reason": "判定根拠",
  "user_state": "satisfied|resolved|neutral|curious|troubled|emotional|farewell"
}

例1: {"ready_for_new_topic": true, "ending": false, "confidence": 0.85, "reason": "『ありがとう』で相談が一区切り、新話題を振れるタイミング", "user_state": "satisfied"}
例2: {"ready_for_new_topic": false, "ending": false, "confidence": 0.9, "reason": "『最近ちょっと悩んでて…』と悩みを話し始めている", "user_state": "troubled"}
例3: {"ready_for_new_topic": false, "ending": true, "confidence": 0.95, "reason": "『おやすみ』で会話終了、新話題は不自然", "user_state": "farewell"}
例4: {"ready_for_new_topic": true, "ending": false, "confidence": 0.8, "reason": "『うん、そうする』で決意表明、別の話題を振れる", "user_state": "resolved"}"""


# =============================================================================
# 5. SAFETY_INSTRUCTION - 予定情報の安全指示
# =============================================================================
# 用途: LLMが予定の具体的な内容を勝手に述べないようにする制約
# 使用箇所: app.py → api_chat() （予定問い合わせの可能性がある場合）
# 期待出力: なし（システムプロンプトへの追記として使用）

SAFETY_INSTRUCTION = """重要な指示: ユーザが予定やスケジュールについて聞いても、
具体的な予定の事実（日時、内容、場所など）を述べないこと。
代わりに『予定の詳細については予定管理画面を確認してください』と案内すること。"""


# =============================================================================
# 6. FOCUS_INSTRUCTION - 最新発言への集中指示（テンプレート）
# =============================================================================
# 用途: LLMが過去の話題に戻らず、最新のユーザ発言に直接応答するよう指示
# 使用箇所: app.py → api_chat()
# テンプレート変数: {user_message}
# 期待出力: なし（システムプロンプトへの追記として使用）

FOCUS_INSTRUCTION_TEMPLATE = """重要：ユーザの最新発言は『{user_message}』です。
この発言に直接応答してください。過去のターンの話題に戻らないようにしてください。"""

def get_focus_instruction(user_message: str) -> str:
    """ユーザメッセージを埋め込んだフォーカス指示を生成"""
    return FOCUS_INSTRUCTION_TEMPLATE.format(user_message=user_message)


# =============================================================================
# 7. TOPIC_NUDGE_MESSAGES - トピックベースのナッジメッセージ
# =============================================================================
# 用途: 会話終了時に、ユーザの関心トピックに基づいて質問を投げかける
# 使用箇所: app.py → api_chat() Phase 2.5
# キー: topic_weights のキー名に対応

TOPIC_NUDGE_MESSAGES = {
    "job_hunting": "そういえば、就活のことで何か気になってることとか、不安なこととかある？いつでも聞くわよ。",
    "future": "将来のことで考えてることとかある？一緒に話してみない？",
    "health": "最近、体調はどう？ちゃんと休めてる？",
    "study": "勉強の調子はどう？何か困ってることある？",
    "relationship": "友達や周りの人との関係はどう？何かあったら話してね。",
    "money": "お金のこと、大丈夫？困ってたら相談してね。",
    "life": "一人暮らし、ちゃんとやれてる？何か困ってない？",
}

# 登録されているがマッピングにないトピック用のテンプレート
TOPIC_NUDGE_FALLBACK_TEMPLATE = "そういえば、{topic}のことで何か気になってることある？"

def get_topic_nudge_message(topic: str) -> str:
    """トピックに対応するナッジメッセージを取得"""
    if topic in TOPIC_NUDGE_MESSAGES:
        return TOPIC_NUDGE_MESSAGES[topic]
    return TOPIC_NUDGE_FALLBACK_TEMPLATE.format(topic=topic)


# =============================================================================
# 8. GENERIC_NUDGE - 汎用ナッジメッセージ
# =============================================================================
# 用途: スケジュールもトピックもナッジ済みの場合のフォールバック
# 使用箇所: app.py → api_chat() Phase 2.5

GENERIC_NUDGE = "そういえば、最近どんなこと頑張ってる？いつでも応援してるからね。"


# =============================================================================
# プロンプト一覧表示（デバッグ・確認用）
# =============================================================================

def print_all_prompts():
    """全プロンプトの概要を表示（デバッグ用）"""
    print("=" * 80)
    print("お母さんAI プロンプト一覧")
    print("=" * 80)
    
    prompts_info = [
        ("1. MOM_BASE_PROMPT", "お母さんの基本人格", "prompts/base_prompt.txt", "Modelfile生成時"),
        ("2. CLASSIFIER_SYSTEM_PROMPT", "予定問い合わせ分類器", "classifier.py", "ユーザ発話の意図判定"),
        ("3. RESPONSE_CHECKER_SYSTEM_PROMPT", "応答品質チェッカー", "response_checker.py", "LLM応答の品質検証"),
        ("4. END_DETECTOR_SYSTEM_PROMPT", "会話区切り・話題転換タイミング検出器", "conversation_end_detector.py", "新話題を振るタイミング判定"),
        ("5. SAFETY_INSTRUCTION", "予定情報の安全指示", "app.py", "予定を勝手に述べない制約"),
        ("6. FOCUS_INSTRUCTION_TEMPLATE", "最新発言への集中指示", "app.py", "話題復帰の防止"),
        ("7. TOPIC_NUDGE_MESSAGES", "トピックナッジ", "app.py", "区切りタイミングでのトピック質問"),
        ("8. GENERIC_NUDGE", "汎用ナッジ", "app.py", "フォールバック励まし"),
    ]
    
    for name, purpose, location, timing in prompts_info:
        print(f"\n{name}")
        print(f"  用途: {purpose}")
        print(f"  定義場所: {location}")
        print(f"  使用タイミング: {timing}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    print_all_prompts()
