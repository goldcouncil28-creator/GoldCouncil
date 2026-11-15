"""S6 — جان والدورات: زاوية 1×1 + مربع التسعة (تقريبي) فقط.

الطريقة: من السوينغ الرئيسي (أعلى قمة/أدنى قاع في 200 شمعة) تُرسم
زاوية 1×1 بميل ATR لكل شمعة → إشارة عند ملامسة السعر للزاوية.
مستويات مربع التسعة: (√السعر ± 0.25k)² للـ k=1..4 — تُذكر في
التفاصيل فقط عند القرب منها.
"""
import numpy as np
import pandas as pd
from ._common import atr


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 220:
        return {"agent": "S6", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    d = df.tail(200)
    a = float(atr(df, 14).iloc[-1])
    price = float(df["close"].iloc[-1])

    hi_idx = d["high"].idxmax()
    lo_idx = d["low"].idxmin()
    hi = float(d.loc[hi_idx, "high"])
    lo = float(d.loc[lo_idx, "low"])
    pos_hi = d.index.get_loc(hi_idx)
    pos_lo = d.index.get_loc(lo_idx)
    now_pos = len(d) - 1

    # زاوية 1×1 من أحدث سوينغ رئيسي
    if pos_lo > pos_hi:  # القاع أحدث → زاوية صاعدة (دعم)
        line = lo + a * (now_pos - pos_lo)
        dist = abs(price - line)
        angle_txt = f"زاوية 1×1 الصاعدة عند {line:.2f}"
        sig = 1 if dist <= 0.3 * a and price >= line - 0.3 * a else 0
    else:  # القمة أحدث → زاوية هابطة (مقاومة)
        line = hi - a * (now_pos - pos_hi)
        dist = abs(price - line)
        angle_txt = f"زاوية 1×1 الهابطة عند {line:.2f}"
        sig = -1 if dist <= 0.3 * a and price <= line + 0.3 * a else 0

    # مربع التسعة: مستويات الزوايا (45° → خطوة 0.25 في الجذر)
    sq = np.sqrt(price)
    sq_levels = [round((sq + k * 0.25) ** 2, 2) for k in range(-4, 5) if k != 0]
    near_sq = [lv for lv in sq_levels if abs(price - lv) <= 0.25 * a]

    if sig != 0:
        return {"agent": "S6", "signal": sig, "confidence": 60,
                "detail": f"ملامسة {angle_txt}"}
    detail = "لا ملامسة لزاوية 1×1"
    if near_sq:
        detail += f" — قرب مستوى مربع التسعة {near_sq[0]:.2f}"
    return {"agent": "S6", "signal": 0, "confidence": 0, "detail": detail}
