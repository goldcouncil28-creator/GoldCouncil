"""R2 — اتفاق الأطر الزمنية: H1 مع H4.

الطريقة: ميل EMA50 (آخر قيمة − قيمة قبل 10 شموع، مُطبَّعًا بـ ATR)
في كل إطار. الاتفاق = 100 − 50×|فرق الإشارتين المُطبَّع|.
aligned=True عندما يتفق الاتجاهان (كلاهما صاعد أو كلاهما هابط).
"""
import pandas as pd
from ._common import ema, atr


def _slope(close: pd.Series, atr_now: float, n: int = 50, back: int = 10) -> float:
    e = ema(close, n)
    if len(e) < n + back or atr_now <= 0:
        return 0.0
    return float((e.iloc[-1] - e.iloc[-back]) / atr_now)


def analyze(df_h1: pd.DataFrame, df_h4: pd.DataFrame) -> dict:
    a1 = float(atr(df_h1, 14).iloc[-1])
    a4 = float(atr(df_h4, 14).iloc[-1])
    s1 = _slope(df_h1["close"], a1)
    s4 = _slope(df_h4["close"], a4)

    d1 = 1 if s1 > 0.05 else (-1 if s1 < -0.05 else 0)
    d4 = 1 if s4 > 0.05 else (-1 if s4 < -0.05 else 0)

    aligned = bool(d1 != 0 and d1 == d4)
    if aligned:
        agreement = 100
    elif d1 == 0 or d4 == 0:
        agreement = 50
    else:
        agreement = 0  # تعارض صريح بين الإطارين

    names = {1: "صاعد", -1: "هابط", 0: "محايد"}
    return {"agent": "R2", "agreement": agreement, "aligned": aligned,
            "h1": names[d1], "h4": names[d4],
            "detail": f"H1 {names[d1]} / H4 {names[d4]} — "
                      + ("متفقان" if aligned else "غير متفقين")}
