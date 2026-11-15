"""X3 — اختلال تدفق الأوامر OFI (proxy).

الطريقة: مجموع الضغط الموقّع لآخر N شمعة ÷ مجموع القيم المطلقة =
مؤشر اختلال بين -1 و+1. تجاوز العتبة → إشارة لحظية.
signal: +1 اختلال شرائي / -1 اختلال بيعي / 0 متوازن.

ملاحظة صدق: proxy — لا يوجد tape/DOM مركزي في السبوت.
"""
import numpy as np
import pandas as pd

N = 12
THRESHOLD = 0.30


def _pressure(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    body = (df["close"] - df["open"]) / rng
    return (body.fillna(0.0) * df["volume"]).fillna(0.0)


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < N + 5:
        return {"agent": "X3", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية", "proxy": True}

    p = _pressure(df).tail(N)
    denom = float(p.abs().sum())
    ofi = float(p.sum()) / denom if denom > 0 else 0.0

    signal, conf = 0, 0
    if ofi > THRESHOLD:
        signal, conf = 1, int(min(55 + ofi * 50, 90))
        detail = f"اختلال شرائي {ofi:.2f} (proxy — بلا tape مركزي)"
    elif ofi < -THRESHOLD:
        signal, conf = -1, int(min(55 + abs(ofi) * 50, 90))
        detail = f"اختلال بيعي {ofi:.2f} (proxy — بلا tape مركزي)"
    else:
        detail = f"تدفق متوازن ({ofi:.2f}) — لا اختلال"

    return {"agent": "X3", "signal": signal, "confidence": conf,
            "detail": detail, "proxy": True, "ofi": round(ofi, 3)}
