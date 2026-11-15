"""C6 — الارتباطات البينية: علاقة الذهب بالدولار والنفط (20 فترة).

المنطق: في النظام الطبيعي الذهب عكس الدولار. إذا كان الارتباط قويًا
سالبًا والدولار يهبط → إشارة شراء للدهب. انهيار الارتباط = signal=0.
"""
import pandas as pd
from ._common import sma

MIN_BARS = 45


def analyze(ctx: dict) -> dict:
    gold, dxy, oil = ctx.get("gold"), ctx.get("dxy"), ctx.get("oil")
    if gold is None or dxy is None or len(gold) < MIN_BARS or len(dxy) < MIN_BARS:
        return {"agent": "C6", "signal": 0, "confidence": 0,
                "detail": "بيانات الذهب/الدولار ناقصة — degraded"}

    gr, dr = gold.pct_change(), dxy.pct_change()
    corr_gd = float(gr.rolling(20).corr(dr).iloc[-1])

    dxy_slope = float((sma(dxy, 20).iloc[-1] - sma(dxy, 20).iloc[-21]) / sma(dxy, 20).iloc[-21])

    oil_note = ""
    if oil is not None and len(oil) >= MIN_BARS:
        corr_go = float(gr.rolling(20).corr(oil.pct_change()).iloc[-1])
        oil_note = f" | ارتباط الذهب/النفط {corr_go:+.2f}"

    if abs(corr_gd) < 0.2:
        return {"agent": "C6", "signal": 0, "confidence": 0,
                "detail": f"الارتباط الذهب/دولار منهار ({corr_gd:+.2f}) — لا إشارة" + oil_note}

    signal, conf = 0, 0
    if corr_gd < -0.4 and dxy_slope < -0.005:
        signal, conf = 1, 70
        note = "الدولار يهبط والارتباط العكسي سليم"
    elif corr_gd < -0.4 and dxy_slope > 0.005:
        signal, conf = -1, 70
        note = "الدولار يصعد والارتباط العكسي سليم"
    else:
        note = "الدولار بلا اتجاه واضح"
    return {"agent": "C6", "signal": signal, "confidence": conf,
            "detail": f"{note} (ارتباط {corr_gd:+.2f})" + oil_note,
            "corr_gold_dxy": round(corr_gd, 3)}
