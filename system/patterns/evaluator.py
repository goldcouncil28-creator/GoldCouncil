"""Pattern 05 (جزء 1) — E1 Evaluator: بوابة جودة الإشارة.

يمنح كل توصية مقترحة درجة 0-100؛ النشر فقط لو ≥ 70.
هذا هو "الأمان" الحقيقي في المنظومة — لا عدد الوكلاء.
"""
THRESHOLD = 70


def evaluate(card, verdict, r0: dict, n0: dict) -> dict:
    checks, score = [], 0.0

    # 1. الإجماع (30): نسبة الوكلاء الموافقين من المصوتين *ذوي الوزن*
    # (التماسك مع E2: من صفّرهم المحسّن لا يُحسبون ضد الإجماع)
    voters = [v for v in verdict.votes.values()
              if not v.get("skipped") and v.get("weight_applied", 0) > 0]
    agree = [v for v in voters if v.get("signal") == verdict.direction]
    s = 30 * len(agree) / max(len(voters), 1)
    score += s
    checks.append(f"إجماع {len(agree)}/{len(voters)} ({s:.0f}/30)")

    # 2. متوسط الثقة (20)
    confs = [v.get("confidence", 0) for v in agree]
    s = 20 * (sum(confs) / max(len(confs), 1) / 100)
    score += s
    checks.append(f"متوسط الثقة ({s:.0f}/20)")

    # 3. ملاءمة النظام (15): R0 سمح لكل المصوتين؟
    s = 15 if r0.get("regime") != "shock" else 0
    score += s
    checks.append(f"نظام السوق {r0.get('regime')} ({s:.0f}/15)")

    # 4. العائد/المخاطرة (15)
    rr = card.risk_reward if card else 0
    s = 15 if rr >= 1.5 else (8 if rr >= 1.2 else 0)
    score += s
    checks.append(f"R:R=1:{rr} ({s:.0f}/15)")

    # 5. خلو الأخبار (10)
    s = 10 if not n0.get("block") else 0
    score += s
    checks.append(f"الأخبار ({s:.0f}/10)")

    total = round(score)
    return {"agent": "E1", "score": total, "pass": total >= THRESHOLD,
            "checks": checks}
