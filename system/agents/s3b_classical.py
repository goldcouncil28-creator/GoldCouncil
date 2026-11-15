"""S3b — النماذج السعرية الكلاسيكية: رأس وكتفين + قمم/قيعان مزدوجة فقط.

الطريقة: قمم/قيعان فراكتل → فحص هندسي للنماذج بتفاوتات صارمة →
إشارة فقط عند كسر خط العنق خلال آخر 12 شمعة.
"""
import pandas as pd
from ._common import atr

RECENT = 12  # نافذة الكسر الحديث


def _pivots(df: pd.DataFrame, n: int = 4, lookback: int = 300):
    d = df.tail(lookback)
    h, l = d["high"].values, d["low"].values
    highs, lows = [], []
    for i in range(n, len(d) - n):
        if h[i] == h[i - n:i + n + 1].max():
            highs.append((i, float(h[i])))
        if l[i] == l[i - n:i + n + 1].min():
            lows.append((i, float(l[i])))
    return highs, lows, len(d)


def _broke(df, level: float, direction: int, after_idx: int, total: int) -> bool:
    """كسر حديث لخط العنق بعد فهرس معين."""
    seg = df.iloc[max(after_idx, total - RECENT):]
    if direction == -1:  # كسر لأسفل
        return bool((seg["close"] < level).any())
    return bool((seg["close"] > level).any())


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 100:
        return {"agent": "S3b", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    a = float(atr(df, 14).iloc[-1])
    price = float(df["close"].iloc[-1])
    highs, lows, total = _pivots(df)

    # --- رأس وكتفين هابط: قمة-قاع-قمة أعلى-قاع-قمة ---
    if len(highs) >= 3 and len(lows) >= 2:
        (i1, ls), (i2, head), (i3, rs) = highs[-3], highs[-2], highs[-1]
        tro = [p for j, p in lows if i1 < j < i3]
        if len(tro) >= 2 and i1 < i2 < i3:
            neck = (tro[0] + tro[-1]) / 2
            if (head > ls * 1.02 and head > rs * 1.02
                    and abs(ls - rs) / ls < 0.05
                    and _broke(df, neck, -1, i3, total)):
                return {"agent": "S3b", "signal": -1, "confidence": 75,
                        "detail": f"رأس وكتفين هابط — كسر خط العنق {neck:.2f}"}
    # --- رأس وكتفين معكوس (صاعد) ---
    if len(lows) >= 3 and len(highs) >= 2:
        (i1, ls), (i2, head), (i3, rs) = lows[-3], lows[-2], lows[-1]
        tro = [p for j, p in highs if i1 < j < i3]
        if len(tro) >= 2 and i1 < i2 < i3:
            neck = (tro[0] + tro[-1]) / 2
            if (head < ls * 0.98 and head < rs * 0.98
                    and abs(ls - rs) / ls < 0.05
                    and _broke(df, neck, 1, i3, total)):
                return {"agent": "S3b", "signal": 1, "confidence": 75,
                        "detail": f"رأس وكتفين معكوس — كسر خط العنق {neck:.2f}"}
    # --- قمة مزدوجة ---
    if len(highs) >= 2 and len(lows) >= 1:
        (i1, h1), (i2, h2) = highs[-2], highs[-1]
        neck_c = [p for j, p in lows if i1 < j < i2]
        if neck_c and abs(h1 - h2) / h1 < 0.02 and _broke(df, neck_c[-1], -1, i2, total):
            return {"agent": "S3b", "signal": -1, "confidence": 68,
                    "detail": f"قمة مزدوجة — كسر {neck_c[-1]:.2f}"}
    # --- قاع مزدوج ---
    if len(lows) >= 2 and len(highs) >= 1:
        (i1, l1), (i2, l2) = lows[-2], lows[-1]
        neck_c = [p for j, p in highs if i1 < j < i2]
        if neck_c and abs(l1 - l2) / l1 < 0.02 and _broke(df, neck_c[-1], 1, i2, total):
            return {"agent": "S3b", "signal": 1, "confidence": 68,
                    "detail": f"قاع مزدوج — كسر {neck_c[-1]:.2f}"}

    return {"agent": "S3b", "signal": 0, "confidence": 0,
            "detail": "لا نموذج كلاسيكي مكتمل بكسر حديث"}
