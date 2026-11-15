"""C3 — الجيوسياسة (LLM عبر 3a2l).

يراقب: المضايق الملاحية، العقوبات، مشتريات الذهب من البنوك المركزية،
توترات كبرى. بدون backend → امتناع صريح.
"""
PROMPT = """أنت وكيل المخاطر الجيوسياسية لمنظومة توصيات دهب (XAUUSD).
قيّم: توترات ملاحية (هرمز/باب المندب/السويس)، عقوبات جديدة، وتيرة شراء
الذهب من البنوك المركزية، وأي حدث سيادي مؤثر هذا الأسبوع.
أخرج JSON فقط: {"signal": 1|-1|0, "confidence": 0-100, "events": [..]}
signal=+1 يعني مخاطر تدفع للملاذ الآمن (الدهب)."""


def analyze(df=None, backend=None) -> dict:
    if backend is None:
        return {"agent": "C3", "signal": 0, "confidence": 0, "degraded": True,
                "detail": "بانتظار توجيه LLM عبر 3a2l — مُمتنع لا مُخمِّن"}
    try:
        return {"agent": "C3", **backend(PROMPT)}
    except Exception as e:
        return {"agent": "C3", "signal": 0, "confidence": 0, "degraded": True,
                "detail": f"فشل الـ backend: {type(e).__name__}"}
