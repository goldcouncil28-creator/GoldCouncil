"""N0 — حارس الأخبار: منع التوصيات حول الأحداث عالية التأثير فقط.

المصدر: مرآة JSON لتقويم ForexFactory (مجاني).
التدهور الرشيق: لو الجلب فشل → status=unknown (لا يمنع، لكن يُعلَّم).
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CACHE = Path(__file__).parent.parent / "data" / "calendar_cache.json"
BLOCK_MINUTES = 30
HIGH_IMPACT_CURRENCIES = {"USD"}  # XAUUSD يتأثر بالدولار أساسًا

# تخزين مؤقت داخل العملية — التقويم أسبوعي فلا داعي لجلبه مع كل شمعة
_MEM_CACHE = {"at": None, "data": None}
_MEM_TTL = 6 * 3600


def _fetch_calendar() -> list:
    import time
    now_ts = time.time()
    if _MEM_CACHE["data"] is not None and now_ts - _MEM_CACHE["at"] < _MEM_TTL:
        return _MEM_CACHE["data"]
    try:
        req = urllib.request.Request(CAL_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data), encoding="utf-8")
        _MEM_CACHE.update(at=now_ts, data=data)
        return data
    except Exception:
        if _MEM_CACHE["data"] is not None:
            return _MEM_CACHE["data"]
        if CACHE.exists():
            try:
                data = json.loads(CACHE.read_text(encoding="utf-8"))
                _MEM_CACHE.update(at=now_ts, data=data)
                return data
            except Exception:
                return []
        return []


def analyze(now: datetime | None = None, impact_currencies: set | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cur = impact_currencies or HIGH_IMPACT_CURRENCIES
    events = _fetch_calendar()

    if not events:
        return {"agent": "N0", "block": False, "status": "unknown",
                "reason": "تعذر جلب التقويم — لا منع، بثقة مخفضة", "confidence": 40}

    window = timedelta(minutes=BLOCK_MINUTES)
    for ev in events:
        try:
            if ev.get("impact") != "High":
                continue
            if ev.get("country") not in cur:
                continue
            # صيغة التاريخ: 2026-10-12T12:30:00-04:00
            dt = datetime.fromisoformat(ev["date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if abs((dt - now)) <= window:
                return {"agent": "N0", "block": True, "status": "blocked",
                        "reason": f"حدث عالي التأثير: {ev.get('title')} ({ev.get('country')}) الساعة {dt:%H:%M}",
                        "confidence": 100}
        except Exception:
            continue
    return {"agent": "N0", "block": False, "status": "clear",
            "reason": "لا أحداث عالية التأثير خلال ±30 دقيقة", "confidence": 95}
