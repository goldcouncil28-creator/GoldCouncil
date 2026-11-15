"""S3a — النماذج الهارمونيك: جارتلي/خفاش/فراشة فقط.

الطريقة: ZigZag لاستخراج السوينغات (X-A-B-C-D) → فحص النسب
(0.618/0.786/0.886/1.27/1.618) بتفاوت ±0.08 → إشارة عند اكتمال
النقطة D قرب السعر الحالي (ضمن 0.3 ATR).
الغموض = لا إشارة.
"""
import numpy as np
import pandas as pd
from ._common import atr

TOL = 0.08  # تفاوت النسب المقبول


def _pivots(df: pd.DataFrame, n: int = 5, lookback: int = 400):
    d = df.tail(lookback)
    h, l = d["high"].values, d["low"].values
    piv = []
    for i in range(n, len(d) - n):
        if h[i] == h[i - n:i + n + 1].max():
            piv.append((d.index[i], float(h[i]), "H"))
        elif l[i] == l[i - n:i + n + 1].min():
            piv.append((d.index[i], float(l[i]), "L"))
    return piv


def _zigzag(piv, atr_now: float):
    """تصفية النقاط المحورية لسوينغات متعاقبة بحركة دنيا 1.0 ATR."""
    zz = []
    for t, p, k in piv:
        if not zz:
            zz.append((t, p, k))
            continue
        lt, lp, lk = zz[-1]
        if k == lk:  # نفس النوع: الاحتفاظ بالأقصى
            if (k == "H" and p > lp) or (k == "L" and p < lp):
                zz[-1] = (t, p, k)
        else:
            if abs(p - lp) >= 1.0 * atr_now:
                zz.append((t, p, k))
    return zz


def _ratio(a, b):
    return abs(a) / abs(b) if abs(b) > 1e-9 else 0.0


def _in(v, lo, hi):
    return lo - TOL <= v <= hi + TOL


def _check_bullish(X, A, B, C, D):
    # X قاع، A قمة، B قاع، C قمة، D قاع
    xa, ab, bc = A - X, A - B, C - B
    if xa <= 0 or ab <= 0 or bc <= 0:
        return None
    b_xa, d_xa = _ratio(xa - ab, xa), _ratio(xa - (D - X), xa)
    bc_ab = _ratio(bc, ab)
    # جارتلي: B≈0.618 ، D≈0.786
    if _in(b_xa, 0.60, 0.64) and _in(d_xa, 0.75, 0.82) and _in(bc_ab, 0.382, 0.886):
        return "جارتلي"
    # خفاش: B≈0.382-0.5 ، D≈0.886
    if _in(b_xa, 0.36, 0.52) and _in(d_xa, 0.85, 0.92) and _in(bc_ab, 0.382, 0.886):
        return "خفاش (Bat)"
    # فراشة: B≈0.786 ، D≈1.27
    if _in(b_xa, 0.75, 0.82) and _in(d_xa, 1.24, 1.32) and _in(bc_ab, 0.382, 0.886):
        return "فراشة (Butterfly)"
    return None


def _check_bearish(X, A, B, C, D):
    # معكوس الصاعد
    return _check_bullish(-X, -A, -B, -C, -D)


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 120:
        return {"agent": "S3a", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    a = float(atr(df, 14).iloc[-1])
    price = float(df["close"].iloc[-1])
    zz = _zigzag(_pivots(df), a)
    if len(zz) < 5:
        return {"agent": "S3a", "signal": 0, "confidence": 0,
                "detail": "لا سوينغات كافية لنموذج هارمونيك"}

    pts = zz[-5:]
    kinds = [k for _, _, k in pts]
    if kinds not in (["L", "H", "L", "H", "L"], ["H", "L", "H", "L", "H"]):
        return {"agent": "S3a", "signal": 0, "confidence": 0,
                "detail": "لا تسلسل XABCD مكتمل"}

    X, A, B, C, D = [p for _, p, _ in pts]
    bullish = kinds[0] == "L"
    name = _check_bullish(X, A, B, C, D) if bullish else _check_bearish(X, A, B, C, D)
    if not name:
        return {"agent": "S3a", "signal": 0, "confidence": 0,
                "detail": "لا نسب هارمونيك مطابقة"}

    # اكتمال النقطة D قرب السعر الحالي؟
    if abs(price - D) <= 0.35 * a:
        sig = 1 if bullish else -1
        return {"agent": "S3a", "signal": sig, "confidence": 78,
                "detail": f"اكتمال نموذج {name} {'صاعد' if bullish else 'هابط'} عند {D:.2f}"}
    return {"agent": "S3a", "signal": 0, "confidence": 0,
            "detail": f"نموذج {name} غير مكتمل بعد (D={D:.2f})"}
