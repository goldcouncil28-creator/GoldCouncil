"""الأوركستريتر (Pattern 04 — Orchestrator-Workers).

يملك دورة حياة الإشارة: routers (تسلسلي) → طبقات الوكلاء (توازي) →
سلسلة التحقق (M1 → M3 → M2 → E1).

الوكلاء workers: كل واحد تخصص واحد وعقد واحد. الأوركستريتر لا يحلل السوق.
"""
from datetime import datetime, timezone

from patterns.runner import run_parallel, chain
from patterns.evaluator import evaluate
from agents import m3_devil
from m1_arbiter import arbitrate
from m2_risk import build_signal


def build_roster():
    from agents import (r0_regime, n0_news, r1_pair, r2_timeframe,
                        c1_macro, c2_sentiment, c3_geopolitics, c4_calendar,
                        c5_cot, c6_intermarket, c7_oil, j1_journal,
                        s1_levels, s2_fib, s3a_harmonic, s3b_classical,
                        s4a_smc, s4b_wyckoff, s4c_elliott,
                        s5a_momentum, s5b_trend, s5c_volatility,
                        s6_gann, s10_flows, s11_candles, s12_volprofile,
                        s13_seasonality, x1_walls, x2_delta, x3_ofi)
    return {
        # L1 — السياق (7)
        "C1": lambda d, c: c1_macro.analyze(c),
        "C2": lambda d, c: c2_sentiment.analyze(backend=c.get("llm")),
        "C3": lambda d, c: c3_geopolitics.analyze(backend=c.get("llm")),
        "C4": lambda d, c: c4_calendar.analyze(now=c.get("now")),
        "C5": lambda d, c: c5_cot.analyze(),
        "C6": lambda d, c: c6_intermarket.analyze(c),
        "C7": lambda d, c: c7_oil.analyze(c),
        # L2 — الهيكل (15)
        "S1": lambda d, c: s1_levels.analyze(d),
        "S2": lambda d, c: s2_fib.analyze(d),
        "S3a": lambda d, c: s3a_harmonic.analyze(d),
        "S3b": lambda d, c: s3b_classical.analyze(d),
        "S4a": lambda d, c: s4a_smc.analyze(d),
        "S4b": lambda d, c: s4b_wyckoff.analyze(d),
        "S4c": lambda d, c: s4c_elliott.analyze(d),
        "S5a": lambda d, c: s5a_momentum.analyze(d),
        "S5b": lambda d, c: s5b_trend.analyze(d),
        "S5c": lambda d, c: s5c_volatility.analyze(d),
        "S6": lambda d, c: s6_gann.analyze(d),
        "S10": lambda d, c: s10_flows.analyze(d),
        "S11": lambda d, c: s11_candles.analyze(d),
        "S12": lambda d, c: s12_volprofile.analyze(d),
        "S13": lambda d, c: s13_seasonality.analyze(d),
        # L3 — التنفيذ (3)
        "X1": lambda d, c: x1_walls.analyze(d),
        "X2": lambda d, c: x2_delta.analyze(d),
        "X3": lambda d, c: x3_ofi.analyze(d),
    }


def build_ctx(df, dxy=None, oil=None, i=None, now=None, llm=None, h4=None):
    sl = lambda s: s.iloc[:i] if (s is not None and i) else s
    if h4 is None:
        h4 = df.resample("4h", origin="start").agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).dropna()
    return {"dxy": sl(dxy), "oil": sl(oil), "gold": df["close"].iloc[:i] if i else df["close"],
            "h4": h4.iloc[:i // 4] if (i and len(h4)) else h4, "now": now, "llm": llm}


def run_pipeline(df, ctx, weights=None, now=None):
    """خط الإشارة الكامل. يرجع dict بالحالة والبطاقة والأصوات."""
    from agents import r0_regime, n0_news, r1_pair, r2_timeframe, j1_journal

    # ── L0: routers تسلسليًا (اعتماد بيانات حقيقي) ──
    r1 = r1_pair.route()
    symbol = r1["symbol"]
    r0 = r0_regime.analyze(df)
    n0 = n0_news.analyze(now=now)
    if n0.get("block"):
        return {"status": "blocked_by_news", "detail": n0["reason"]}
    if r0["regime"] == "shock":
        return {"status": "blocked_by_shock", "detail": "صدمة سعرية — الكل مسكوت"}
    r2 = r2_timeframe.analyze(df, ctx["h4"])

    # ── L1+L2+L3: توازي ──
    roster = build_roster()
    tasks = [(n, fn, (df, ctx), {}) for n, fn in roster.items()]
    outs = run_parallel(tasks, max_workers=10)
    outs = [o for o in outs.values() if isinstance(o, dict) and o.get("agent")]

    # ── السلسلة: M1 → M3 → M2 → E1 ──
    def s_arbitrate(_):
        v = arbitrate(outs, r0, weights)
        return None if v.direction == 0 else v
    def s_devil(v):
        ch = m3_devil.challenge(None, v, r0)
        return None if ch["veto"] else (v, ch)
    def s_risk(vch):
        v, ch = vch
        entry = float(df["close"].iloc[-1])
        fib = next((o.get("targets") for o in outs if o.get("agent") == "S2"), None)
        card = build_signal(symbol, v.direction, entry, r0["atr"],
                            v.confidence, v.reasons, fib_targets=fib)
        return None if not card else (v, ch, card)
    def s_eval(vchc):
        v, ch, card = vchc
        ev = evaluate(card, v, r0, n0)
        return None if not ev["pass"] else (v, ch, card, ev)

    res = chain([s_arbitrate, s_devil, s_risk, s_eval], True)
    j1 = j1_journal.analyze()
    if res is None:
        return {"status": "no_signal", "r0": r0, "r2": r2,
                "n_votes": len(outs), "j1": j1.get("stats")}
    v, ch, card, ev = res
    return {"status": "signal", "card": card, "verdict": v, "m3": ch,
            "e1": ev, "r0": r0, "r2": r2, "symbol": symbol}
