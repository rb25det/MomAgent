import json
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class LogManager:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_log_file = self.log_dir / f"chat_{datetime.datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def save_log(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "role": role,
            "content": content,
            "metadata": metadata or {}
        }
        with self.current_log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            