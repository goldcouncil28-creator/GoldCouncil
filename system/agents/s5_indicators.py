"""S5 — المؤشرات: RSI/Stoch/MACD/BB/ATR/المتوسطات + الدايفرجنس فقط.

يجمع قراءات الزخم والاتجاه والتقلب في درجة مركبة → signal/confidence.
"""
import numpy as np
import pandas as pd
from ._common import atr, rsi, macd, stochastic, bollinger, ema


def _divergence(close: pd.Series, osc: pd.Series, lookback: int = 30) -> int:
    """دايفرجنس كلاسيكي بسيط: قمتان سعريتان صاعدتان + قمتا مؤشر هابطتان = -1."""
    c, o = close.tail(lookback), osc.tail(lookback)
    try:
        c1, c2 = c.iloc[-15:].idxmax(), c.iloc[-5:].idxmax()
        o1 = o.loc[c.index.get_indexer([c1], method="nearest")[0]]
        o2 = o.loc[c.index.get_indexer([c2], method="nearest")[0]]
        if c.loc[c2] > c.loc[c1] and o2 < o1:
            return -1  # دايفرجنس سلبي
        t1, t2 = c.iloc[-15:].idxmin(), c.iloc[-5:].idxmin()
        oo1 = o.loc[c.index.get_indexer([t1], method="nearest")[0]]
        oo2 = o.loc[c.index.get_indexer([t2], method="nearest")[0]]
        if c.loc[t2] < c.loc[t1] and oo2 > oo1:
            return 1   # دايفرجنس إيجابي
    except Exception:
        pass
    return 0


def analyze(df: pd.DataFrame) -> dict:
    close = df["close"]
    r = rsi(close).iloc[-1]
    m, s, _ = macd(close)
    k, d_ = stochastic(df)
    mid, upper, lower = bollinger(close)
    e50, e200 = ema(close, 50).iloc[-1], ema(close, 200).iloc[-1]
    price = float(close.iloc[-1])

    score, notes = 0, []
    if r < 30:
        score += 2; notes.append("RSI تشبع بيعي")
    elif r > 70:
        score -= 2; notes.append("RSI تشبع شرائي")
    if m.iloc[-1] > s.iloc[-1] and m.iloc[-2] <= s.iloc[-2]:
        score += 1; notes.append("تقاطع MACD إيجابي")
    elif m.iloc[-1] < s.iloc[-1] and m.iloc[-2] >= s.iloc[-2]:
        score -= 1; notes.append("تقاطع MACD سلبي")
    if k.iloc[-1] < 20 and k.iloc[-1] > d_.iloc[-1]:
        score += 1; notes.append("ستوكاستيك صاعد من تشبع")
    elif k.iloc[-1] > 80 and k.iloc[-1] < d_.iloc[-1]:
        score -= 1; notes.append("ستوكاستيك هابط من تشبع")
    if price < lower.iloc[-1]:
        score += 1; notes.append("السعر تحت البولنجر السفلي")
    elif price > upper.iloc[-1]:
        score -= 1; notes.append("السعر فوق البولنجر العلوي")
    if e50 > e200:
        score += 1; notes.append("فوق المتوسطات (اتجاه صاعد)")
    else:
        score -= 1; notes.append("تحت المتوسطات (اتجاه هابط)")

    div = _divergence(close, rsi(close))
    if div:
        score += div * 2
        notes.append("دايفرجنس " + ("إيجابي" if div > 0 else "سلبي"))

    signal = 1 if score >= 3 else (-1 if score <= -3 else 0)
    conf = min(abs(score) * 12, 88) if signal else 0
    return {"agent": "S5", "signal": signal, "confidence": conf,
            "detail": "، ".join(notes) if notes else "لا إشارات واضحة",
            "rsi": round(float(r), 1), "score": score}
