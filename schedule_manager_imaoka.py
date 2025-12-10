import requests
import json
import datetime
from typing import Optional, Dict, Any, Tuple

# --- 設定 ---
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
EXTRACT_MODEL = "llama3.1:8b" 

class ScheduleManager:
    def __init__(self, api_url: str = OLLAMA_API_URL, model: str = EXTRACT_MODEL):
        self.api_url = api_url
        self.model = model

    def _call_ollama_json(self, messages: list) -> Dict[str, Any]:
        """OllamaをJSONモードで呼び出す"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0}
        }
        try:
            res = requests.post(self.api_url, json=payload, timeout=30)
            res.raise_for_status()
            content = res.json()["message"]["content"]
            clean_content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_content)
        except Exception as e:
            print(f"[ScheduleManager Error] {e}")
            return {}

    def extract_and_update(self, user_input: str, current_state: Optional[Dict] = None) -> Dict[str, Any]:
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S (%A)')
        
        if not current_state:
            current_state = {"summary": None, "datetime_iso": None, "importance": None}
        
        state_json = json.dumps(current_state, ensure_ascii=False)
        
        system_prompt = f"""
        あなたはスケジュール抽出エンジンです。
        ユーザー入力と現在の登録状況(JSON)から、最新情報を抽出してください。
        
        前提: 現在日時={now_str}
        
        【重要ルール】
        1. ユーザーの発言に「明示的に」含まれていない情報は、絶対に null にしてください。推測禁止。
        2. 重要度(importance)の定義: "1"(大事/絶対), "2"(普通), "3"(適当/なんとなく)。
        
        【学習用データ（例）】
        入力: "バイトがある"
        出力: {{"summary": "バイト", "datetime_iso": null, "importance": null}}
        
        入力: "明日の19時にご飯"
        出力: {{"summary": "ご飯", "datetime_iso": "YYYY-MM-DDT19:00:00", "importance": null}}

        現在の状況: {state_json}
        ユーザー入力: {user_input}
        """

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input}]
        extracted = self._call_ollama_json(messages)
        return extracted if extracted else current_state

    def get_next_action(self, state: Dict[str, Any]) -> Tuple[str, str]:
        summary = state.get("summary")
        dt = state.get("datetime_iso")
        importance = state.get("importance")

        # 1. 基本情報不足
        if not summary or not dt:
            instruction = (
                "【システム指示】情報不足です。"
                f"現在の把握状況: 内容={summary or '未定'}, 日時={dt or '未定'}。"
                "「いつ」「何があるのか」を、会話の流れで自然に聞き出してください。"
            )
            return "incomplete", instruction

        # 2. 重要度不足
        if not importance:
            instruction = (
                f"【システム指示】日時({dt})と内容({summary})は分かりました。"
                "まだ重要度が分かりません。"
                "「それは絶対に外せない大事な用事なのか、それとも普通の用事なのか」を、お母さんらしく心配して聞いてください。"
                "※数字（1,2,3）については一切言わないでください。"
            )
            return "incomplete", instruction

        # 3. 完了
        imp_label = {"1": "大事", "2": "普通", "3": "そんなに"}.get(importance, "普通")
        instruction = (
            "【システム指示】全ての情報が揃いました。"
            f"内容:{summary}, 日時:{dt}, 重要度:{imp_label}。"
            "内容を復唱し、「手帳に書いとくわ（登録完了）」と伝えてください。"
        )
        return "complete", instruction