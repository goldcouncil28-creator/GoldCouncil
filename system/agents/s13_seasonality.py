"""S13 — الموسمية: تحيز ساعة اليوم ويوم الأسبوع فقط.

الطريقة: من تاريخ df نفسه — اتجاه الشمعة التالية لكل (يوم، ساعة) →
إشارة فقط لو التحيز قوي (>58% أو <42%) وبعينة كافية (≥15).
"""
import pandas as pd


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 500:
        return {"agent": "S13", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية للتحيز الموسمي"}
    d = df.copy()
    d["fwd_up"] = (d["close"].shift(-1) > d["close"]).astype(int)
    d = d.dropna(subset=["fwd_up"])
    d["dow"] = d.index.dayofweek
    d["hour"] = d.index.hour

    now = d.index[-1]
    key = (now.dayofweek, now.hour)
    grp = d[(d["dow"] == key[0]) & (d["hour"] == key[1])]
    n = len(grp)
    if n < 15:
        return {"agent": "S13", "signal": 0, "confidence": 0,
                "detail": f"عينة غير كافية لهذه الساعة (n={n})"}
    p_up = float(grp["fwd_up"].mean())
    days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    ctx = f"{days[key[0]]} الساعة {key[1]:02d} — صعود {p_up:.0%} من {n} مرة"
    if p_up >= 0.58:
        return {"agent": "S13", "signal": 1, "confidence": 62, "detail": "تحيز صاعد: " + ctx}
    if p_up <= 0.42:
        return {"agent": "S13", "signal": -1, "confidence": 62, "detail": "تحيز هابط: " + ctx}
    return {"agent": "S13", "signal": 0, "confidence": 0,
            "detail": "لا تحيز موسمي واضح: " + ctx}
