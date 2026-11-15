"""S5b — الاتجاه: EMA50/200 + MACD + ميل الاتجاه فقط (تفكيك S5).

درجة مركبة → إشارة عند |الدرجة| ≥ 3.
"""
import pandas as pd
from ._common import ema, macd


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 220:
        return {"agent": "S5b", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    close = df["close"]
    e50 = ema(close, 50)
    e200 = ema(close, 200)
    m, s, _ = macd(close)
    slope = float(e50.iloc[-1] - e50.iloc[-6])  # ميل EMA50 على 5 شموع

    score, notes = 0, []
    if e50.iloc[-1] > e200.iloc[-1]:
        score += 2; notes.append("EMA50 فوق EMA200 (اتجاه صاعد)")
    else:
        score -= 2; notes.append("EMA50 تحت EMA200 (اتجاه هابط)")
    if m.iloc[-1] > s.iloc[-1]:
        score += 1; notes.append("MACD فوق خط الإشارة")
    else:
        score -= 1; notes.append("MACD تحت خط الإشارة")
    if slope > 0:
        score += 1; notes.append("ميل الاتجاه صاعد")
    else:
        score -= 1; notes.append("ميل الاتجاه هابط")

    if abs(score) >= 3:
        return {"agent": "S5b", "signal": 1 if score > 0 else -1,
                "confidence": min(55 + abs(score) * 8, 88),
                "detail": " + ".join(notes)}
    return {"agent": "S5b", "signal": 0, "confidence": 0,
            "detail": " + ".join(notes)}
