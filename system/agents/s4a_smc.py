"""S4a — مفاهيم الأموال الذكية: كتل الأوامر (OB) + فجوات القيمة العادلة (FVG) فقط.

الطريقة: رصد الاندفاع (مدى > 2.2 ATR وإغلاق قوي) → كتلة الأوامر =
آخر شمعة معاكسة قبل الاندفاع؛ FVG = فجوة بين low[i] و high[i-2] →
إشارة عند عودة السعر لمنطقة غير مُخفَّضة (ضمن 0.3 ATR).
"""
import pandas as pd
from ._common import atr


def _displacements(df, a: float):
    """فهارس شموع الاندفاع: (i, الاتجاه)."""
    out = []
    o, c = df["open"].values, df["close"].values
    rng = (df["high"] - df["low"]).values
    for i in range(3, len(df)):
        body = c[i] - o[i]
        if rng[i] > 2.2 * a and abs(body) / rng[i] > 0.6:
            out.append((i, 1 if body > 0 else -1))
    return out


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 60:
        return {"agent": "S4a", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    a = float(atr(df, 14).iloc[-1])
    price = float(df["close"].iloc[-1])
    o = df["open"].values
    c = df["close"].values
    hi = df["high"].values
    lo = df["low"].values

    zones = []  # (lo, hi, dir, kind)
    for i, d in _displacements(df, a)[-6:]:
        # كتلة الأوامر: آخر شمعة معاكسة قبل الاندفاع
        for j in range(i - 1, max(i - 6, 0), -1):
            if (c[j] - o[j]) * d < 0:
                zones.append((float(lo[j]), float(hi[j]), d, "OB"))
                break
        # FVG
        if d == 1 and lo[i] > hi[i - 2]:
            zones.append((float(hi[i - 2]), float(lo[i]), d, "FVG"))
        elif d == -1 and hi[i] < lo[i - 2]:
            zones.append((float(hi[i]), float(lo[i - 2]), d, "FVG"))

    # إسقاط المناطق المُخفَّضة (السعر اخترق منتصفها بعد تكونها)
    for z_lo, z_hi, d, kind in reversed(zones[-4:]):
        mid = (z_lo + z_hi) / 2
        if abs(price - mid) <= (z_hi - z_lo) / 2 + 0.3 * a:
            # داخل المنطقة أو عند حافتها → إشارة مع اتجاه الاندفاع
            sig = d
            return {"agent": "S4a", "signal": sig, "confidence": 70,
                    "detail": f"عودة السعر لمنطقة {kind} "
                              f"{'شرائية' if d == 1 else 'بيعية'} "
                              f"{z_lo:.2f}–{z_hi:.2f}"}

    return {"agent": "S4a", "signal": 0, "confidence": 0,
            "detail": "لا عودة لمناطق OB/FVG غير مُخفَّضة"}
