"""S11 — الشموع اليابانية: مطرقة/شهاب/ابتلاع/دوجي/نجمتا الصباح والمساء فقط.

درجة مركبة من آخر 3 شموع → إشارة عند |الدرجة| ≥ 2.
"""
import pandas as pd


def _shape(o, h, l, c):
    body = c - o
    rng = h - l
    if rng <= 0:
        return None
    return {"body": body, "rng": rng,
            "up": h - max(o, c), "lo": min(o, c) - l,
            "bull": body > 0}


def analyze(df: pd.DataFrame) -> dict:
    if len(df) < 10:
        return {"agent": "S11", "signal": 0, "confidence": 0,
                "detail": "بيانات غير كافية"}
    d = df.tail(3)
    s = [_shape(r.open, r.high, r.low, r.close) for r in d.itertuples()]
    score, notes = 0, []

    c0 = s[-1]
    ab = abs(c0["body"])
    # مطرقة / رجل مشنوق
    if c0["lo"] >= 2 * ab and c0["up"] <= 0.4 * ab and ab > 0:
        score += 1; notes.append("مطرقة")
    # شهاب
    if c0["up"] >= 2 * ab and c0["lo"] <= 0.4 * ab and ab > 0:
        score -= 1; notes.append("شهاب")
    # ابتلاع
    p = s[-2]
    if abs(p["body"]) > 0 and c0["bull"] != p["bull"] \
            and ab > abs(p["body"]) * 1.1:
        score += 1 if c0["bull"] else -1
        notes.append("ابتلاع " + ("شرائي" if c0["bull"] else "بيعي"))
    # دوجي → حياد (لا نقاط)
    if ab <= 0.1 * c0["rng"]:
        notes.append("دوجي (تردد)")
    # نجمة الصباح / المساء
    if len(s) == 3:
        a, b, e = s
        gap_down = b["rng"] and min(d.iloc[1].open, d.iloc[1].close) < min(d.iloc[0].open, d.iloc[0].close)
        if not a["bull"] and abs(a["body"]) > 0.5 * a["rng"] and e["bull"] \
                and abs(e["body"]) > 0.5 * e["rng"] and gap_down:
            score += 2; notes.append("نجمة الصباح")
        gap_up = min(d.iloc[1].open, d.iloc[1].close) > max(d.iloc[0].open, d.iloc[0].close)
        if a["bull"] and abs(a["body"]) > 0.5 * a["rng"] and not e["bull"] \
                and abs(e["body"]) > 0.5 * e["rng"] and gap_up:
            score -= 2; notes.append("نجمة المساء")

    if abs(score) >= 2:
        return {"agent": "S11", "signal": 1 if score > 0 else -1,
                "confidence": min(55 + abs(score) * 8, 85),
                "detail": " + ".join(notes)}
    return {"agent": "S11", "signal": 0, "confidence": 0,
            "detail": " + ".join(notes) if notes else "لا نماذج شموع حاسمة"}
