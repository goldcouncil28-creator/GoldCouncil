"""S12 — الملف الحجمي: POC/VAH/VAL فقط (من هستوجرام الحجم على H1).

الطريقة: 24 سلة سعرية على آخر 240 شمعة → POC أعلى حجم →
منطقة القيمة 70% حوله → إشارة قبول (خارج المنطقة) أو رفض
(ذيل خارجها وإغلاق داخلها).
"""
import numpy as np
import pandas as pd


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 260:
        return {"agent": "S12", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    d = df.tail(240)
    price = float(d["close"].iloc[-1])
    prev = float(d["close"].iloc[-2])
    hi, lo = float(d["high"].max()), float(d["low"].min())

    bins = np.linspace(lo, hi, 25)
    mids = (bins[:-1] + bins[1:]) / 2
    vol = np.zeros(24)
    tp = ((d["high"] + d["low"] + d["close"]) / 3).values
    vv = d["volume"].values
    idx = np.clip(np.digitize(tp, bins) - 1, 0, 23)
    for i, v in zip(idx, vv):
        vol[i] += v

    poc_i = int(np.argmax(vol))
    poc = float(mids[poc_i])
    total = vol.sum()
    # منطقة القيمة: التوسع من POC حتى 70% من الحجم
    lo_i = hi_i = poc_i
    acc = vol[poc_i]
    while acc < 0.7 * total and (lo_i > 0 or hi_i < 23):
        down = vol[lo_i - 1] if lo_i > 0 else -1
        up = vol[hi_i + 1] if hi_i < 23 else -1
        if up >= down:
            hi_i += 1; acc += vol[hi_i]
        else:
            lo_i -= 1; acc += vol[lo_i]
    vah, val = float(mids[hi_i]), float(mids[lo_i])

    if price > vah and prev > vah:
        return {"agent": "S12", "signal": 1, "confidence": 65,
                "detail": f"قبول فوق منطقة القيمة (VAH={vah:.2f})",
                "poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2)}
    if price < val and prev < val:
        return {"agent": "S12", "signal": -1, "confidence": 65,
                "detail": f"قبول تحت منطقة القيمة (VAL={val:.2f})",
                "poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2)}
    # رفض: ذيل يتجاوز ثم إغلاق داخل المنطقة
    last = d.iloc[-1]
    if float(last["high"]) > vah and price <= vah:
        return {"agent": "S12", "signal": -1, "confidence": 60,
                "detail": f"رفض من أعلى منطقة القيمة ({vah:.2f})",
                "poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2)}
    if float(last["low"]) < val and price >= val:
        return {"agent": "S12", "signal": 1, "confidence": 60,
                "detail": f"رفض من أسفل منطقة القيمة ({val:.2f})",
                "poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2)}
    return {"agent": "S12", "signal": 0, "confidence": 0,
            "detail": f"السعر داخل منطقة القيمة ({val:.2f}–{vah:.2f})",
            "poc": round(poc, 2), "vah": round(vah, 2), "val": round(val, 2)}
