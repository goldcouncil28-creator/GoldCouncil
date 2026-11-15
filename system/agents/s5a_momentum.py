"""S5a — الزخم: RSI + ستوكاستيك + الدايفرجنس فقط (تفكيك S5).

درجة مركبة → إشارة عند |الدرجة| ≥ 3.
"""
import pandas as pd
from ._common import rsi, stochastic


def _divergence(close: pd.Series, osc: pd.Series, lookback: int = 30) -> int:
    c, o = close.tail(lookback), osc.tail(lookback)
    try:
        c1, c2 = c.iloc[-15:].idxmax(), c.iloc[-5:].idxmax()
        o1 = o.loc[c.index.get_indexer([c1], method="nearest")[0]]
        o2 = o.loc[c.index.get_indexer([c2], method="nearest")[0]]
        if c.loc[c2] > c.loc[c1] and o2 < o1:
            return -1
        t1, t2 = c.iloc[-15:].idxmin(), c.iloc[-5:].idxmin()
        oo1 = o.loc[c.index.get_indexer([t1], method="nearest")[0]]
        oo2 = o.loc[c.index.get_indexer([t2], method="nearest")[0]]
        if c.loc[t2] < c.loc[t1] and oo2 > oo1:
            return 1
    except Exception:
        pass
    return 0


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 60:
        return {"agent": "S5a", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    close = df["close"]
    r = rsi(close)
    k, d_ = stochastic(df)
    rl, kl, dl = float(r.iloc[-1]), float(k.iloc[-1]), float(d_.iloc[-1])

    score, notes = 0, []
    if rl < 30:
        score += 2; notes.append("RSI تشبع بيعي")
    elif rl > 70:
        score -= 2; notes.append("RSI تشبع شرائي")
    if kl < 20 and kl > dl:
        score += 1; notes.append("ستوكاستيك صاعد من تشبع بيعي")
    elif kl > 80 and kl < dl:
        score -= 1; notes.append("ستوكاستيك هابط من تشبع شرائي")
    div = _divergence(close, r)
    if div:
        score += div * 2
        notes.append("دايفرجنس RSI " + ("إيجابي" if div > 0 else "سلبي"))

    if abs(score) >= 3:
        return {"agent": "S5a", "signal": 1 if score > 0 else -1,
                "confidence": min(abs(score) * 12, 88),
                "detail": " + ".join(notes), "rsi": round(rl, 1)}
    return {"agent": "S5a", "signal": 0, "confidence": 0,
            "detail": " + ".join(notes) if notes else "زخم محايد",
            "rsi": round(rl, 1)}
