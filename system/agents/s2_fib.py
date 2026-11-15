"""S2 — فيبوناتشي: ارتداد + امتداد فقط.

الطريقة: اكتشاف آخر سوينغ مهم (أعلى قمة/أدنى قاع في N شمعة) →
حساب نسب الارتداد → إشارة دخول مع الاتجاه عند المنطقة الذهبية (38.2–61.8%).
+ مستويات الامتداد كأهداف مقترحة لـ M2.
"""
import pandas as pd
from ._common import atr

RETRACEMENTS = [0.382, 0.5, 0.618]
EXTENSIONS = [1.272, 1.618]


def _swing(df: pd.DataFrame, n: int = 120):
    d = df.tail(n)
    hi_idx = d["high"].idxmax()
    lo_idx = d["low"].idxmin()
    hi = float(d.loc[hi_idx, "high"])
    lo = float(d.loc[lo_idx, "low"])
    # الاتجاه = من الأقدم للأحدث بين القمة والقاع
    uptrend = lo_idx < hi_idx
    return (lo, hi) if uptrend else (hi, lo), uptrend


def analyze(df: pd.DataFrame) -> dict:
    (p0, p1), uptrend = _swing(df)
    price = float(df["close"].iloc[-1])
    a = float(atr(df, 14).iloc[-1])
    rng = abs(p1 - p0)
    if rng < 2 * a:  # سوينغ ضعيف — لا إشارة
        return {"agent": "S2", "signal": 0, "confidence": 0,
                "detail": "لا سوينغ واضح", "levels": {}, "targets": []}

    if uptrend:
        levels = {r: p1 - r * rng for r in RETRACEMENTS}
        targets = [p1 + e * rng for e in EXTENSIONS]
        zone_lo, zone_hi = levels[0.618], levels[0.382]
        in_zone = zone_lo - 0.2 * a <= price <= zone_hi + 0.2 * a
        signal = 1 if in_zone else 0
        detail = (f"تصحيح صاعد داخل المنطقة الذهبية {zone_lo:.2f}–{zone_hi:.2f}"
                  if in_zone else "خارج منطقة فيبوناتشي")
    else:
        levels = {r: p0 + r * rng for r in RETRACEMENTS}
        targets = [p0 - e * rng for e in EXTENSIONS]
        zone_lo, zone_hi = levels[0.382], levels[0.618]
        in_zone = zone_lo - 0.2 * a <= price <= zone_hi + 0.2 * a
        signal = -1 if in_zone else 0
        detail = (f"تصحيح هابط داخل المنطقة الذهبية {zone_lo:.2f}–{zone_hi:.2f}"
                  if in_zone else "خارج منطقة فيبوناتشي")

    return {"agent": "S2", "signal": signal,
            "confidence": 75 if signal else 0, "detail": detail,
            "trend": "up" if uptrend else "down",
            "levels": {str(k): round(v, 2) for k, v in levels.items()},
            "targets": [round(t, 2) for t in targets]}
