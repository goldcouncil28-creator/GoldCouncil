"""C4 — رادار التقويم: أحداث USD عالية التأثير خلال 48 ساعة القادمة.

معلوماتي للراوتر فقط — signal=0 دائمًا (المنع الفعلي مهمة N0).
يستورد _fetch_calendar من .n0_news (نفس المرآة المجانية).
"""
from datetime import datetime, timedelta, timezone
from .n0_news import _fetch_calendar


def analyze(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    events = _fetch_calendar()
    if not events:
        return {"agent": "C4", "signal": 0, "confidence": 0,
                "detail": "تعذر جلب التقويم — degraded"}

    horizon = now + timedelta(hours=48)
    upcoming = []
    for ev in events:
        try:
            if ev.get("impact") != "High" or ev.get("country") != "USD":
                continue
            dt = datetime.fromisoformat(ev["date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if now <= dt <= horizon:
                fc = ev.get("forecast")
                upcoming.append((dt, ev.get("title", "?"),
                                 f" (متوقع {fc})" if fc else ""))
        except Exception:
            continue

    upcoming.sort(key=lambda x: x[0])
    if not upcoming:
        return {"agent": "C4", "signal": 0, "confidence": 0,
                "detail": "لا أحداث USD عالية التأثير خلال 48 ساعة"}
    items = [f"{t} ({d:%d %b %H:%M}){f}" for d, t, f in upcoming[:6]]
    extra = f" +{len(upcoming) - 6} أخرى" if len(upcoming) > 6 else ""
    return {"agent": "C4", "signal": 0, "confidence": 0,
            "detail": f"{len(upcoming)} حدث عالي التأثير خلال 48 ساعة: " + "، ".join(items) + extra,
            "events": [{"title": t, "at": d.isoformat()} for d, t, _ in upcoming]}
