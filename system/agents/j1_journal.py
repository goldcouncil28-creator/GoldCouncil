"""J1 — ذاكرة الأداء: معدل الفوز لكل اتجاه من سجل الصفقات.

معلوماتي لمقيّم E2 فقط — signal=0 دائمًا.
يقرأ نفس قاعدة السجل: data/journal.db جدول signals.
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "journal.db"
WINS = ("tp1", "tp2")


def analyze() -> dict:
    base = {"agent": "J1", "signal": 0, "confidence": 0}
    if not DB.exists():
        return {**base, "detail": "لا سجل صفقات بعد — degraded", "stats": {}}
    try:
        c = sqlite3.connect(DB)
        rows = c.execute(
            "SELECT direction, status, COUNT(*) FROM signals "
            "WHERE status != 'open' GROUP BY direction, status").fetchall()
        c.close()
    except Exception:
        return {**base, "detail": "تعذر قراءة السجل — degraded", "stats": {}}
    if not rows:
        return {**base, "detail": "لا صفقات مغلقة بعد — degraded", "stats": {}}

    agg: dict = {}
    for direction, status, n in rows:
        d = agg.setdefault(direction, {"wins": 0, "losses": 0})
        if status in WINS:
            d["wins"] += n
        elif status == "sl":
            d["losses"] += n
    stats, parts = {}, []
    for direction, d in agg.items():
        total = d["wins"] + d["losses"]
        wr = round(100 * d["wins"] / total, 1) if total else 0
        stats[direction] = {"trades": total, "win_rate": wr}
        parts.append(f"{direction}: {wr}% ({d['wins']}/{total})")
    return {**base, "detail": "معدل الفوز التاريخي — " + "، ".join(parts),
            "stats": stats}
