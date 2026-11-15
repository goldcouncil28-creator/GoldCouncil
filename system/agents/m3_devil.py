"""M3 — محامي الشيطان: يهاجم التوصية المقترحة هيكليًا.

نسخة كود حقيقية (تعمل الآن) + خطاف LLM للسرد لاحقًا.
الفيتو: 3+ هجمات هيكلية = إلغاء التوصية.
"""
PROMPT = """أنت محامِ الشيطان لمنظومة توصيات. أمامك توصية مقترحة مع أصوات الوكلاء.
مهمتك الوحيدة: اكتشاف ما قد يجعلها خاسرة. اذكر 3-5 نقاط ضعف محددة
(تعارض وكلاء، نظام سوق غير ملائم، أخبار قريبة، مخاطرة/عائد ضعيف).
أخرج JSON: {"attacks": [...], "veto": true|false}"""


def challenge(card, verdict, r0: dict, backend=None) -> dict:
    attacks = []
    voters = [v for v in verdict.votes.values() if not v.get("skipped")]
    agree = [v for v in voters if v.get("signal") == verdict.direction]
    silent = [v for v in voters if not v.get("signal")]

    if len(silent) > len(agree):
        attacks.append(f"الصامتون ({len(silent)}) أكثر من الموافقين ({len(agree)}) — إجماع هش")
    contra = [v["agent"] for v in voters
              if v.get("signal") == -verdict.direction and v.get("confidence", 0) >= 60]
    if contra:
        attacks.append(f"معارضة قوية من: {', '.join(contra)}")
    if r0.get("regime") == "mixed":
        attacks.append("نظام السوق مختلط — الإشارات الهيكلية أضعف تاريخيًا")
    if verdict.confidence < 70:
        attacks.append(f"ثقة الحاكم حدية ({verdict.confidence}%)")
    if card and card.risk_reward < 1.5:
        attacks.append(f"مخاطرة/عائد ضعيف (1:{card.risk_reward})")
    degraded = sum(1 for v in voters if v.get("degraded"))
    if degraded >= 3:
        attacks.append(f"{degraded} وكلاء في وضع degraded — الصورة ناقصة")

    llm_attacks = []
    if backend:
        try:
            llm_attacks = backend(PROMPT).get("attacks", [])
        except Exception:
            pass

    all_attacks = attacks + llm_attacks
    return {"agent": "M3", "attacks": all_attacks,
            "veto": len(all_attacks) >= 3,
            "detail": f"{len(all_attacks)} هجمات هيكلية" if all_attacks else "لا هجمات"}
