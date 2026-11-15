"""C1 — السيولة الكلية: اتجاه الدولار + النفط فقط → إشارة للدهب.

المنطق: دولار ضعيف = إيجابي للدهب (علاقة عكسية تاريخية)،
نفط صاعد = نبض تضخمي يدعم الدهب كملاذ.
بلا مفاتيح API — يعمل على السلاسل الممررة في ctx.
"""
import pandas as pd
from ._common import sma

MIN_BARS = 45


def _slope(s: pd.Series, n: int = 20) -> float | None:
    m = sma(s, n)
    if len(m.dropna()) < n + 1:
        return None
    base = m.iloc[-n - 1]
    if not base:
        return None
    return float((m.iloc[-1] - base) / abs(base))


def analyze(ctx: dict) -> dict:
    dxy = ctx.get("dxy")
    oil = ctx.get("oil")
    if dxy is None or oil is None or len(dxy) < MIN_BARS or len(oil) < MIN_BARS:
        return {"agent": "C1", "signal": 0, "confidence": 0,
                "detail": "بيانات الدولار/النفط ناقصة — degraded"}

    dxy_trend = _slope(dxy)
    oil_trend = _slope(oil)
    if dxy_trend is None or oil_trend is None:
        return {"agent": "C1", "signal": 0, "confidence": 0,
                "detail": "سلاسل قصيرة جدًا لحساب الميل — degraded"}

    # الدولار: ميل سالب = ضعف = إيجابي للدهب
    d_score = 0
    if dxy_trend < -0.005:
        d_score = 1
    elif dxy_trend > 0.005:
        d_score = -1
    # النفط: ميل موجب = تضخم = إيجابي للدهب
    o_score = 0
    if oil_trend > 0.01:
        o_score = 1
    elif oil_trend < -0.01:
        o_score = -1

    score = 0.6 * d_score + 0.4 * o_score
    signal = 1 if score >= 0.5 else (-1 if score <= -0.5 else 0)
    conf = min(int(abs(score) * 100), 80) if signal else 0
    parts = []
    parts.append("الدولار ضعيف" if d_score > 0 else ("الدولار قوي" if d_score < 0 else "الدولار محايد"))
    parts.append("النفط صاعد" if o_score > 0 else ("النفط هابط" if o_score < 0 else "النفط محايد"))
    return {"agent": "C1", "signal": signal, "confidence": conf,
            "detail": " + ".join(parts) + f" (ميل DXY={dxy_trend:+.2%})"}
