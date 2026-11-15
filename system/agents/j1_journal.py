"""J1 — ذاكرة الأداء: معدل الفوز لكل اتجاه من سجل الصفقات.

معلوماتي لمقيّم E2 فقط — signal=0 دائمًا.
يقرأ سجل الصفقات عبر `backend` (SQLite محليًا، Supabase على Actions).
"""
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "journal.db"
WINS = ("tp1", "tp2")
DIR_AR = {"long": "شراء", "short": "بيع"}


def analyze() -> dict:
    base = {"agent": "J1", "signal": 0, "confidence": 0}
    try:
        from telegram_bot import backend as _backend
        stats = _backend.get_backend().journal_stats_by_direction()
    except Exception:
        return {**base, "detail": "تعذر قراءة السجل — degraded", "stats": {}}
    if not stats:
        return {**base, "detail": "لا صفقات مغلقة بعد — degraded", "stats": {}}
    parts = []
    for direction, d in stats.items():
        label = DIR_AR.get(direction, direction)
        parts.append(f"{label}: {d['win_rate']}% ({d['wins']}/{d['trades']})")
    return {**base, "detail": "معدل الفوز التاريخي — " + "، ".join(parts),
            "stats": stats}
