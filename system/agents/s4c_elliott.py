"""S4c — موجات إليوت (مبسط): دافع (5 سوينغات) مقابل تصحيحي (3) فقط.

الطريقة: ZigZag للسوينغات → آخر 5 نقاط: قمم/قيعان أعلى = دافع صاعد،
والعكس = دافع هابط → إشارة مع الاتجاه الدافع. آخر 3 نقاط متعاكسة
= تصحيح → لا إشارة.
"""
import pandas as pd
from ._common import atr


def _zigzag(df: pd.DataFrame, n: int = 5, lookback: int = 350):
    d = df.tail(lookback)
    h, l = d["high"].values, d["low"].values
    piv = []
    for i in range(n, len(d) - n):
        if h[i] == h[i - n:i + n + 1].max():
            piv.append((float(h[i]), "H"))
        elif l[i] == l[i - n:i + n + 1].min():
            piv.append((float(l[i]), "L"))
    a = float(atr(df, 14).iloc[-1])
    zz = []
    for p, k in piv:
        if not zz:
            zz.append((p, k))
            continue
        lp, lk = zz[-1]
        if k == lk:
            if (k == "H" and p > lp) or (k == "L" and p < lp):
                zz[-1] = (p, k)
        elif abs(p - lp) >= 0.8 * a:
            zz.append((p, k))
    return zz


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 150:
        return {"agent": "S4c", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    zz = _zigzag(df)
    if len(zz) < 5:
        return {"agent": "S4c", "signal": 0, "confidence": 0,
                "detail": "سوينغات غير كافية للعد الموجي"}

    last5 = zz[-5:]
    kinds = [k for _, k in last5]
    if kinds not in (["L", "H", "L", "H", "L"], ["H", "L", "H", "L", "H"]):
        return {"agent": "S4c", "signal": 0, "confidence": 0,
                "detail": "تسلسل موجي غير مكتمل"}

    px = [p for p, _ in last5]
    if kinds[0] == "L":  # قيعان: L0,H1,L1,H2,L2
        hh = px[1] < px[3]
        hl = px[0] < px[2] < px[4]
        ll = px[0] > px[2] > px[4]
        lh = px[1] > px[3]
        if hh and hl:
            return {"agent": "S4c", "signal": 1, "confidence": 62,
                    "detail": "موجة دافعة صاعدة (قمم وقيعان أعلى)"}
        if ll and lh:
            return {"agent": "S4c", "signal": -1, "confidence": 62,
                    "detail": "موجة دافعة هابطة (قمم وقيعان أدنى)"}
    else:  # قمم أولًا: H0,L1,H2,L3,H4
        hh = px[0] < px[2] < px[4]
        hl = px[1] < px[3]
        ll = px[0] > px[2] > px[4]
        lh = px[1] > px[3]
        if hh and hl:
            return {"agent": "S4c", "signal": 1, "confidence": 62,
                    "detail": "موجة دافعة صاعدة (قمم وقيعان أعلى)"}
        if ll and lh:
            return {"agent": "S4c", "signal": -1, "confidence": 62,
                    "detail": "موجة دافعة هابطة (قمم وقيعان أدنى)"}

    return {"agent": "S4c", "signal": 0, "confidence": 0,
            "detail": "حركة تصحيحية (3 موجات) — بلا إشارة اتجاه"}
