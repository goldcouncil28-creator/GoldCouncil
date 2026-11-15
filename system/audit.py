"""سجل التدقيق — JSONL append-only (فكرة مستعارة من وثيقة الأوركسترا).

كل قرار يُسجَّل: أصوات الوكلاء + الأوزان + الفيتو + النتيجة. لا يُحذف سطر أبدًا.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent / "data" / "audit"


def log(event: str, payload: dict):
    BASE.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rec = {"ts": datetime.now(timezone.utc).isoformat(),
           "event": event, **payload}
    with open(BASE / f"{day}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
