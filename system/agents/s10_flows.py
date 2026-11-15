"""S10 — تدفقات إعادة التوازن: نهاية الشهر/الربع فقط.

وكيل حذر بطبيعته: لا يعطي إشارة اتجاه أبدًا (signal=0 دائمًا)،
مهمته تحذير بقية المنظومة من نوافذ التدفقات المؤسسية الإجبارية.
"""
import pandas as pd


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 5:
        return {"agent": "S10", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    now = df.index[-1]
    # آخر يوم تداول في الشهر/الربع: اليومان الأخيران من الشهر الميلادي
    month_end = now + pd.offsets.MonthEnd(0)
    days_left = (month_end.normalize() - now.normalize()).days
    is_quarter_end = now.month in (3, 6, 9, 12)

    if days_left <= 2:
        kind = "نهاية ربع سنوي" if is_quarter_end else "نهاية شهر"
        return {"agent": "S10", "signal": 0, "confidence": 80,
                "detail": f"حذر: {kind} — تدفقات إعادة توازن مؤسسية، "
                          f"تقلبات مصطنعة محتملة (متبقي {days_left} يوم)"}
    if now.day <= 2:
        return {"agent": "S10", "signal": 0, "confidence": 60,
                "detail": "بداية شهر — انتهت تدفقات إعادة التوازن"}
    return {"agent": "S10", "signal": 0, "confidence": 95,
            "detail": "لا نوافذ تدفقات مؤسسية حالية"}
