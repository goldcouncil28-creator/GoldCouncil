"""X2 — ضغط الشراء/البيع ودلتا الحجم التراكمية (CVD).

الطريقة: ضغط الشمعة = (close-open)/(high-low) × volume (موقّع: + شراء / - بيع).
CVD = المجموع التراكمي للضغط. ميل CVD على آخر N شمعة (انحدار خطي مُطبَّع) →
إشارة استمرار/انعكاس ضغط.
signal: +1 ضغط شرائي / -1 ضغط بيعي / 0 محايد.
"""
import numpy as np
import pandas as pd

N = 20  # نافذة ميل CVD


def _pressure(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    body = (df["close"] - df["open"]) / rng
    return (body.fillna(0.0) * df["volume"]).fillna(0.0)


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < N + 10:
        return {"agent": "X2", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}

    p = _pressure(df)
    cvd = p.cumsum().tail(N).values
    x = np.arange(N)
    slope, _ = np.polyfit(x, cvd, 1)
    scale = float(p.tail(N).abs().sum()) / N  # متوسط الضغط المطلق للشمعة
    norm = slope / scale if scale > 0 else 0.0

    signal, conf = 0, 0
    if norm > 0.35:
        signal, conf = 1, int(min(55 + abs(norm) * 40, 90))
        detail = f"CVD صاعد بميل {norm:.2f} — ضغط شرائي متراكم"
    elif norm < -0.35:
        signal, conf = -1, int(min(55 + abs(norm) * 40, 90))
        detail = f"CVD هابط بميل {norm:.2f} — ضغط بيعي متراكم"
    else:
        detail = f"CVD محايد (ميل {norm:.2f}) — لا ضغط واضح"

    return {"agent": "X2", "signal": signal, "confidence": conf,
            "detail": detail, "cvd_slope": round(float(norm), 3)}
