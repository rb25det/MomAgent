"""
プロンプト一元管理モジュール

このファイルでは、お母さんAIシステムで使用される全てのプロンプトを一元管理します。
各プロンプトの用途、使用箇所、期待される出力形式を明記しています。

【プロンプト一覧】
1. MOM_BASE_PROMPT           - お母さんの基本人格・振る舞い（テンプレート）
2. CLASSIFIER_SYSTEM_PROMPT  - 予定問い合わせ分類器
3. RESPONSE_CHECKER_PROMPT   - 応答品質チェッカー
4. END_DETECTOR_PROMPT       - 会話終了検出器
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
# 4. END_DETECTOR_PROMPT - 会話終了検出器
# =============================================================================
# 用途: ユーザが会話を終わらせようとしているかを判定
# 使用箇所: conversation_end_detector.py → build_end_detector_prompt()
# 期待出力: JSON {"ending": true|false, "confidence": 0.0-1.0, "reason": "判定根拠"}

END_DETECTOR_SYSTEM_PROMPT = """あなたは会話終了を判定するアシスタントです。与えられた直近の会話と最新のユーザ発話を見て、
ユーザが会話を本当に終わらせようとしているかを判定し、JSONで返してください。

【重要な判定ルール】
1. ネガティブな内容（失敗、不採用、悩み）≠ 会話終了。むしろ相談欲求の可能性が高い。
2. 会話終了の明確な合図：
   - 別れ表現：さようなら、またね、今日はここまで、じゃあね、バイバイ、また今度
   - 感謝で締める：『ありがとうね』『ありがとうございます』などの一文だけで応答
   - 短い同意・決意：『うん』『わかった』『がんばる』『がんばるね』『頑張ります』などの一語〜短文だけで、その後新しい質問や話題がない
   - 疲労表現：『疲れた』『もう無理』『今日は終わり』『おわり』など心理的な終わり
3. 会話継続の合図：質問形式、新しい話題の提示、悩みの報告、相談欲求、今後について語る、複雑な説明。
4. 注意：『ありがとうね』『うん』『がんばる』などは単独または短文で出現した場合は終了の可能性が高い（confidence >= 0.85）。ただし、その後に『〜について』『〜だから』など新しい話題や理由が続いたら継続と判定。
5. 長い説明の後に『以上』『それでいいです』など話の区切りがあり、その後新しい質問や話題がなければ終了の可能性。

返却フォーマット: {"ending": true/false, "confidence": 0.0-1.0, "reason": "判定根拠"}
例1 (終了): {"ending": true, "confidence": 0.95, "reason": "『ありがとうね』という感謝で話を締めている"}
例2 (継続): {"ending": false, "confidence": 0.9, "reason": "不採用の報告だが相談欲求が見られる"}
例3 (終了): {"ending": true, "confidence": 0.9, "reason": "『うん。がんばる』という短い決意表明で、その後新しい話題がない"}
例4 (終了): {"ending": true, "confidence": 0.85, "reason": "『わかった』『頑張ります』という短い同意・決意で締めており、会話の区切りと判断"}"""


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
        ("4. END_DETECTOR_SYSTEM_PROMPT", "会話終了検出器", "conversation_end_detector.py", "会話終了の判定"),
        ("5. SAFETY_INSTRUCTION", "予定情報の安全指示", "app.py", "予定を勝手に述べない制約"),
        ("6. FOCUS_INSTRUCTION_TEMPLATE", "最新発言への集中指示", "app.py", "話題復帰の防止"),
        ("7. TOPIC_NUDGE_MESSAGES", "トピックナッジ", "app.py", "会話終了時のトピック質問"),
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
