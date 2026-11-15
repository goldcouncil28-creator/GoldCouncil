"""S4b — منهجية وايكوف: تصنيف الطور فقط (تجميع/تصريف/صعود/هبوط).

الطريقة: انكماش المدى والحجم (تجميع/تصريف) مقابل توسعهما مع
الاتجاه (صعود/هبوط). الإشارة فقط في طوري الصعود/الهبوط المؤكدين.
"""
import pandas as pd
from ._common import atr


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 150:
        return {"agent": "S4b", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    d = df.tail(130)
    rng = d["high"] - d["low"]
    vol = d["volume"]
    price = float(d["close"].iloc[-1])

    mean_rng = float(rng.tail(60).mean())
    mean_vol = float(vol.tail(60).mean())
    cur_rng = float(rng.tail(10).mean())
    cur_vol = float(vol.tail(10).mean())

    lo120, hi120 = float(d["low"].min()), float(d["high"].max())
    pos = (price - lo120) / (hi120 - lo120) if hi120 > lo120 else 0.5
    drift = float(d["close"].tail(20).mean() - d["close"].head(20).mean())

    contracting = cur_rng < 0.7 * mean_rng and cur_vol < 0.9 * mean_vol
    expanding = cur_rng > 1.2 * mean_rng and cur_vol > 1.1 * mean_vol

    if contracting:
        phase = "تجميع" if pos < 0.45 else ("تصريف" if pos > 0.55 else "إعادة تجميع")
        return {"agent": "S4b", "signal": 0, "confidence": 0,
                "detail": f"طور {phase} — انكماش المدى والحجم، بلا إشارة اتجاه",
                "phase": phase}
    if expanding and drift > 0 and pos > 0.5:
        return {"agent": "S4b", "signal": 1, "confidence": 65,
                "detail": "طور صعود (Markup) — توسع المدى والحجم مع الصعود",
                "phase": "صعود"}
    if expanding and drift < 0 and pos < 0.5:
        return {"agent": "S4b", "signal": -1, "confidence": 65,
                "detail": "طور هبوط (Markdown) — توسع المدى والحجم مع الهبوط",
                "phase": "هبوط"}
    return {"agent": "S4b", "signal": 0, "confidence": 0,
            "detail": "طور انتقالي غير واضح", "phase": "انتقالي"}
