"""C7 — نبض التضخم (النفط): اتجاه النفط وتقلبه → إشارة للدهب.

المنطق: نفط صاعد = ضغوط تضخمية = طلب على الذهب كتحوط.
تقلب النفط المتصاعد = عدم يقين = دعم إضافي للملاذات.
"""
import pandas as pd
from ._common import sma

MIN_BARS = 70


def analyze(ctx: dict) -> dict:
    oil = ctx.get("oil")
    if oil is None or len(oil) < MIN_BARS:
        return {"agent": "C7", "signal": 0, "confidence": 0,
                "detail": "بيانات النفط ناقصة — degraded"}

    m20 = sma(oil, 20)
    slope = float((m20.iloc[-1] - m20.iloc[-21]) / m20.iloc[-21])
    vol_short = float(oil.pct_change().rolling(20).std().iloc[-1])
    vol_long = float(oil.pct_change().rolling(60).std().iloc[-1])
    vol_rising = vol_short > 1.3 * vol_long if vol_long else False

    score = 0
    notes = []
    if slope > 0.02:
        score += 2
        notes.append("النفط صاعد بقوة (تضخم)")
    elif slope > 0.005:
        score += 1
        notes.append("النفط يميل للصعود")
    elif slope < -0.03:
        score -= 1
        notes.append("النفط يهبط بحدة")
    if vol_rising:
        score += 1
        notes.append("تقلب النفط متصاعد (عدم يقين يدعم الملاذات)")

    signal = 1 if score >= 2 else (-1 if score <= -1 else 0)
    conf = min(55 + abs(score) * 8, 80) if signal else 0
    return {"agent": "C7", "signal": signal, "confidence": conf,
            "detail": " + ".join(notes) if notes else "النفط بلا نبض واضح",
            "oil_slope": round(slope, 4)}
