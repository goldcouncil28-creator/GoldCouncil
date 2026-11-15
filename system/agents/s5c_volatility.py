"""S5c — التقلب: عرض البولنجر + موقع السعر + نظام ATR فقط (تفكيك S5).

الإشارة فقط عند توسع التقلب مع اتجاه واضح؛ الانكماش = حياد.
"""
import pandas as pd
from ._common import bollinger, atr


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 150:
        return {"agent": "S5c", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    close = df["close"]
    price = float(close.iloc[-1])
    mid, upper, lower = bollinger(close)
    a = atr(df, 14)
    a_now = float(a.iloc[-1])

    width = (upper - lower) / mid
    w_now = float(width.iloc[-1])
    w_pct = float((width.tail(120) < w_now).mean())  # مرتبة العرض الحالية

    a_trend = float(a.tail(10).mean() - a.tail(30).mean())

    if w_pct < 0.2:
        return {"agent": "S5c", "signal": 0, "confidence": 0,
                "detail": "انكماش تقلب (Squeeze) — انتظار الانفجار"}
    if price > float(mid.iloc[-1]) and a_trend > 0:
        return {"agent": "S5c", "signal": 1, "confidence": 60,
                "detail": "توسع تقلب صاعد فوق متوسط البولنجر"}
    if price < float(mid.iloc[-1]) and a_trend > 0:
        return {"agent": "S5c", "signal": -1, "confidence": 60,
                "detail": "توسع تقلب هابط تحت متوسط البولنجر"}
    return {"agent": "S5c", "signal": 0, "confidence": 0,
            "detail": "تقلب بلا اتجاه واضح"}
