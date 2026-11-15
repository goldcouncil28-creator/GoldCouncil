"""M1 — الحاكم: الجمع والتحكيم فقط. لا يحلل السوق بنفسه.

- يطبق فلتر R0 (المدارس غير المسموحة وزنها صفر).
- تصويت موزون؛ الأوزان تُتعلَّم من الباكتست (الآن قيم ابتدائية).
- العتبة: |الدرجة المرجحة| >= 0.55 وإجماع 2+ وكيل.
"""
from dataclasses import dataclass

# أوزان ابتدائية — تُستبدل بالمُتعلَّمة من E2 (walk-forward)
DEFAULT_WEIGHTS = {"S1": 1.0, "S2": 1.2, "S5": 1.0}
THRESHOLD = 0.55


@dataclass
class Verdict:
    direction: int          # +1 شراء / -1 بيع / 0 لا إشارة
    confidence: int         # 0-100
    score: float            # الدرجة المرجحة -1..1
    votes: dict             # {agent: {signal, confidence, detail}}
    reasons: list           # أسباب بشرية للبطاقة


def arbitrate(agent_outputs: list, r0: dict, weights: dict | None = None) -> Verdict:
    w = weights or DEFAULT_WEIGHTS
    allowed = set(r0.get("allowed", []))
    votes, num, den, reasons = {}, 0.0, 0.0, []

    for out in agent_outputs:
        name = out["agent"]
        if name not in allowed:
            votes[name] = {**out, "weight_applied": 0.0, "skipped": "R0"}
            continue
        if out.get("degraded"):
            votes[name] = {**out, "weight_applied": 0.0, "skipped": "degraded"}
            continue
        wt = w.get(name, 1.0) * (out.get("confidence", 50) / 100)
        votes[name] = {**out, "weight_applied": round(wt, 3)}
        num += out.get("signal", 0) * wt
        den += wt
        if out.get("signal"):
            reasons.append(f"{name}: {out.get('detail', '')}")

    score = num / den if den else 0.0
    n_agree = sum(1 for v in votes.values()
                  if v.get("signal") and v.get("signal") == (1 if score > 0 else -1)
                  and not v.get("skipped"))

    if abs(score) >= THRESHOLD and n_agree >= 2:
        direction = 1 if score > 0 else -1
        confidence = min(int(abs(score) * 100), 95)
    else:
        direction, confidence = 0, 0

    return Verdict(direction, confidence, round(score, 3), votes, reasons)
