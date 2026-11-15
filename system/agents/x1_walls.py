"""X1 — امتصاص السيولة (proxy لرصد الجدران/الامتصاص في دفتر الأوامر).

الطريقة: طفرة حجم (أعلى من 2× الوسيط المتحرك) مع حركة سعرية صافية ضعيفة
(أقل من 0.4× ATR) = طرف كبير يمتص التدفق → إشارة انعكاس عكس الحركة السابقة.
signal: +1 امتصاص بيعي (انعكاس صاعد) / -1 امتصاص شرائي (انعكاس هابط) / 0 لا امتصاص.

ملاحظة صدق: هذا proxy — الفوركس السبوت بلا دفتر أوامر مركزي،
والإشارة مبنية على الحجم/السعر لا على DOM حقيقي.
"""
import numpy as np
import pandas as pd
from ._common import atr


def analyze(df: pd.DataFrame) -> dict:
    a = float(atr(df, 14).iloc[-1])
    if a <= 0 or len(df) < 60:
        return {"agent": "X1", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية", "proxy": True}

    vol = df["volume"]
    vol_med = float(vol.tail(40).median())
    last = df.iloc[-1]
    last_vol = float(last["volume"])
    net_move = abs(float(last["close"]) - float(last["open"]))

    # الحركة السابقة: اتجاه آخر 10 شموع قبل الأخيرة
    prev = df.iloc[-11:-1]
    prev_dir = float(prev["close"].iloc[-1] - prev["close"].iloc[0])

    absorption = last_vol > 2.0 * vol_med and net_move < 0.4 * a

    signal, conf, detail = 0, 0, "لا امتصاص واضح (proxy)"
    if absorption:
        strength = min(last_vol / (2.0 * vol_med), 3.0)  # 1..3
        if prev_dir < 0:
            signal = 1
            detail = (f"امتصاص بيعي: حجم {last_vol/vol_med:.1f}× الوسيط بلا متابعة هبوطية "
                      f"(proxy — بلا DOM مركزي)")
        elif prev_dir > 0:
            signal = -1
            detail = (f"امتصاص شرائي: حجم {last_vol/vol_med:.1f}× الوسيط بلا متابعة صعودية "
                      f"(proxy — بلا DOM مركزي)")
        conf = int(min(55 + strength * 12, 88)) if signal else 0

    return {"agent": "X1", "signal": signal, "confidence": conf,
            "detail": detail, "proxy": True,
            "vol_ratio": round(last_vol / vol_med, 2) if vol_med else 0.0}
