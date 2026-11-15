"""C2 — معنويات الفيدرالي والأخبار (LLM عبر 3a2l).

العقد جاهز للتوجيه: analyze(backend=None).
بدون backend → امتناع صريح (degraded). لا إشارة مخترعة أبدًا.
"""
PROMPT = """أنت وكيل معنويات السوق لمنظومة توصيات دهب (XAUUSD).
حلل: نبرة آخر تصريحات الفيدرالي (hawkish/dovish)، عناوين الأخبار الاقتصادية
الكبرى هذا الأسبوع، ومؤشر الخوف/الطمع.
أخرج JSON فقط: {"signal": 1|-1|0, "confidence": 0-100, "reasons": [..]}
signal=+1 يعني بيئة داعمة للدهب (دولار ضعيف/مخاوف)."""

BACKEND_NOTE = "يُوجَّه عبر 3a2l proxy (LiteLLM على جهاز محمد) — تكلفة شبه صفرية"


def analyze(df=None, backend=None) -> dict:
    if backend is None:
        return {"agent": "C2", "signal": 0, "confidence": 0, "degraded": True,
                "detail": "بانتظار توجيه LLM عبر 3a2l — مُمتنع لا مُخمِّن"}
    try:
        return {"agent": "C2", **backend(PROMPT)}
    except Exception as e:
        return {"agent": "C2", "signal": 0, "confidence": 0, "degraded": True,
                "detail": f"فشل الـ backend: {type(e).__name__}"}
