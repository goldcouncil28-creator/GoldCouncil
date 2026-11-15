"""S1 — المستويات الكلاسيكية: دعوم/مقاومات + برايس أكشن فقط.

الطريقة: قمم/قيعان فراكتل (نقاط تحول) → تجميع المستويات المتقاربة →
قياس قرب السعر الحالي → إشارة ارتداد متوقع.
signal: +1 قرب دعم / -1 قرب مقاومة / 0 بعيد عن المستويات.
"""
import numpy as np
import pandas as pd
from ._common import atr


def _fractals(df: pd.DataFrame, n: int = 3, lookback: int = 300):
    d = df.tail(lookback)
    highs, lows = [], []
    h, l = d["high"].values, d["low"].values
    for i in range(n, len(d) - n):
        if h[i] == h[i - n:i + n + 1].max():
            highs.append((d.index[i], float(h[i])))
        if l[i] == l[i - n:i + n + 1].min():
            lows.append((d.index[i], float(l[i])))
    return highs, lows


def _cluster(levels: list, atr_now: float):
    """دمج المستويات المتقاربة (ضمن 0.5 ATR) مع عدّ اللمسات."""
    if not levels:
        return []
    px = sorted(p for _, p in levels)
    clusters = [[px[0]]]
    for p in px[1:]:
        if p - clusters[-1][-1] <= 0.5 * atr_now:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [{"price": float(np.mean(c)), "touches": len(c)} for c in clusters]


def analyze(df: pd.DataFrame) -> dict:
    a = float(atr(df, 14).iloc[-1])
    price = float(df["close"].iloc[-1])
    highs, lows = _fractals(df)

    resistances = _cluster(highs, a)
    supports = _cluster(lows, a)

    def nearest(levels, want_below: bool):
        cands = [x for x in levels if (x["price"] < price) == want_below]
        if not cands:
            return None
        return min(cands, key=lambda x: abs(x["price"] - price))

    sup = nearest(supports, True)
    res = nearest(resistances, False)

    signal, conf, detail = 0, 0, "السعر بعيد عن المستويات الرئيسية"
    if sup and abs(price - sup["price"]) <= 0.4 * a:
        signal, conf = 1, min(50 + sup["touches"] * 10, 90)
        detail = f"قرب دعم {sup['price']:.2f} ({sup['touches']} لمسات)"
    elif res and abs(price - res["price"]) <= 0.4 * a:
        signal, conf = -1, min(50 + res["touches"] * 10, 90)
        detail = f"قرب مقاومة {res['price']:.2f} ({res['touches']} لمسات)"

    return {"agent": "S1", "signal": signal, "confidence": conf,
            "detail": detail,
            "supports": [round(x["price"], 2) for x in supports[-3:]],
            "resistances": [round(x["price"], 2) for x in resistances[-3:]]}
