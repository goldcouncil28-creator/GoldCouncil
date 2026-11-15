"""Pattern 05 (جزء 2) — E2 Optimizer: تعلم الأوزان walk-forward.

المقياس (v2): العائد المتوقع بوحدة R لكل وكيل — يحاكي منطق M2 الحقيقي:
  دخول بسعر الإغلاق، وقف = 1R (1.5×ATR)، هدف = 1.5R، نافذة 8 شموع.
  النتيجة لكل إشارة: +1.5 / -1 / 0 (مرجحة بثقة الوكيل).
  ثم انكماش (shrinkage) نحو الصفر للعينات الصغيرة بدل التصفير الحدّي:
  score × n/(n+20) — عادل للوكلاء بطيئي الإشارات (C1/C4/..).

يعمل على إطار الإشارات المحسوب مسبقًا (vectorized) — بلا إعادة حساب الوكلاء.
"""
import pandas as pd

TP_R, SL_R, LOOKAHEAD = 1.5, 1.0, 8
SHRINK_K = 20


def outcome_r(direction: int, entry: float, atr_v: float, fut: pd.DataFrame) -> float:
    """محاكاة صفقة M2: +1.5R / -1R / 0 — متحفظ (الوقف أولًا عند التلامس المزدوج)."""
    sl_d = 1.5 * atr_v
    if direction > 0:
        sl, tp = entry - sl_d, entry + TP_R * sl_d
    else:
        sl, tp = entry + sl_d, entry - TP_R * sl_d
    for j in range(len(fut)):
        hi, lo = float(fut["high"].iloc[j]), float(fut["low"].iloc[j])
        if direction > 0:
            if lo <= sl:
                return -SL_R
            if hi >= tp:
                return TP_R
        else:
            if hi >= sl:
                return -SL_R
            if lo <= tp:
                return TP_R
    return 0.0


def learn_weights(agent_sig: pd.DataFrame, df: pd.DataFrame,
                  atr_series: pd.Series) -> dict:
    names = [c for c in agent_sig.columns if not c.endswith("_c")]
    pos_of = {ts: k for k, ts in enumerate(df.index)}
    scores, detail = {}, {}
    for n in names:
        col, conf = agent_sig[n], agent_sig[n + "_c"]
        s_sum, cnt = 0.0, 0
        for ts, s in col[col != 0].items():
            k = pos_of.get(ts)
            if k is None:
                continue
            a = float(atr_series.iloc[k])
            px = float(df["close"].iloc[k])
            if a <= 0:
                continue
            fut = df.iloc[k + 1:k + 1 + LOOKAHEAD]
            if len(fut) == 0:
                continue
            r = outcome_r(int(s), px, a, fut)
            s_sum += r * (float(conf.loc[ts]) / 100)
            cnt += 1
        raw = (s_sum / cnt) if cnt else 0.0
        shrunk = raw * (cnt / (cnt + SHRINK_K))
        scores[n] = shrunk
        detail[n] = f"{shrunk:+.3f}R (n={cnt})"

    pos = {n: s for n, s in scores.items() if s > 0}
    mean = sum(pos.values()) / max(len(pos), 1) or 1.0
    weights = {n: round(scores[n] / mean, 3) if scores[n] > 0 else 0.0
               for n in scores}
    return {"agent": "E2", "weights": weights, "detail": detail,
            "metric": "r_expectancy_shrunk",
            "note": "الأوزان = عائد R متوقع بانكماش — السالب والمعدوم يُصفَّر"}
