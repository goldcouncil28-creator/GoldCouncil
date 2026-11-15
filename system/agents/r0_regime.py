"""R0 — حارس النظام: تصنيف نظام السوق فقط (ترند / تذبذب / صدمة).

المخرج: regime + قائمة المدارس المسموحة. لا يعطي إشارة اتجاه بنفسه.
"""
import pandas as pd
from ._common import hurst_exponent, atr

SCHOOLS = ["S1", "S2", "S3a", "S3b", "S4a", "S4b", "S4c", "S5a", "S5b",
           "S5c", "S6", "S10", "S11", "S12", "S13", "S7", "S9",
           "C1", "C2", "C3", "C4", "C5", "C6", "C7",
           "X1", "X2", "X3"]

ALLOW = {
    # الترند: مدارس الاتجاه والزخم والسياق
    "trend": ["S1", "S2", "S3b", "S4a", "S4b", "S4c", "S5a", "S5b", "S5c",
              "S6", "S9", "S11", "S12", "S13",
              "C1", "C5", "C6", "C7", "X1", "X2", "X3"],
    # التذبذب: مدارس الارتداد فقط
    "range": ["S1", "S2", "S3a", "S5a", "S5c", "S11", "S12", "S13"],
    "shock": [],                                       # صدمة: الكل مسكوت
    "mixed": SCHOOLS,                                  # مختلط: الكل بثقة مخفضة
}


def analyze(df: pd.DataFrame) -> dict:
    close = df["close"]
    h = hurst_exponent(close.tail(240))
    a = atr(df, 14)
    atr_now = float(a.iloc[-1])
    price = float(close.iloc[-1])

    # كشف الصدمة: مدى آخر شمعة > 3× ATR
    last_range = float(df["high"].iloc[-1] - df["low"].iloc[-1])
    shock = last_range > 3.0 * atr_now if atr_now > 0 else False

    if shock:
        regime = "shock"
    elif h > 0.55:
        regime = "trend"
    elif h < 0.45:
        regime = "range"
    else:
        regime = "mixed"

    return {
        "agent": "R0",
        "regime": regime,
        "hurst": round(h, 3),
        "atr": round(atr_now, 2),
        "atr_pct": round(100 * atr_now / price, 3) if price else 0,
        "allowed": ALLOW[regime],
        "confidence": 90 if regime != "mixed" else 60,
    }
