"""الباكتست v3 — Precompute-once + walk-forward.

1. compute_agent_signals: إشارات الوكلاء لكل شمعة (مرة واحدة، multiprocessing، cached).
2. E2 vectorized على in-sample (60%) → أوزان (مقياس R المتوقع).
3. finalize على out-of-sample (40%): البوابات + M1 + M3 + M2 + E1.
4. محاكاة صريحة: دخول بافتتاح التالية + سبريد، bracket وقف/هدف، صلاحية 8 شموع.
"""
import json
from pathlib import Path

import pandas as pd

from agents._common import atr as atr_fn
from data_loader import load_xauusd_h1, load_dxy_proxy, load_oil
from signals import compute_agent_signals
from patterns.optimizer import learn_weights

SPLIT = 0.6
WARMUP = 260
RISK_USD = 100.0
SPREAD_PCT = 0.0001
WEIGHTS_FILE = Path(__file__).parent / "data" / "learned_weights.json"


def finalize(df, agent_sig, weights, start_pos):
    """خط الإشارة النهائي على الشموع من start_pos: بوابات + سلسلة M1→M3→M2→E1."""
    from agents import r0_regime, n0_news, r2_timeframe, m3_devil
    from m1_arbiter import arbitrate
    from m2_risk import build_signal
    from patterns.evaluator import evaluate

    names = [c for c in agent_sig.columns if not c.endswith("_c")]
    atr_s = atr_fn(df)
    h4 = df.resample("4h", origin="start").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}).dropna()
    rows, r0_cache = {}, {}
    for pos in range(start_pos, len(df)):
        ts = df.index[pos]
        if ts not in agent_sig.index:
            continue
        row = agent_sig.loc[ts]
        key = pos // 12
        if key not in r0_cache:
            r0_cache[key] = r0_regime.analyze(df.iloc[:pos])
        r0 = r0_cache[key]
        if r0["regime"] == "shock":
            continue
        bt_ = ts.tz_localize("UTC") if ts.tzinfo is None else ts
        n0 = n0_news.analyze(now=bt_)
        if n0.get("block"):
            continue
        r2 = r2_timeframe.analyze(df.iloc[:pos],
                                  h4.iloc[:pos // 4] if len(h4) else h4)
        outs = [{"agent": n, "signal": int(row[n]),
                 "confidence": int(row[n + "_c"]), "detail": ""} for n in names]
        v = arbitrate(outs, r0, weights)
        if v.direction == 0:
            continue
        ch = m3_devil.challenge(None, v, r0)
        if ch["veto"]:
            continue
        entry = float(df["close"].iloc[pos])
        a = float(atr_s.iloc[pos])
        card = build_signal("XAUUSD", v.direction, entry, a,
                            v.confidence, ["إجماع الوكلاء"])
        if not card:
            continue
        ev = evaluate(card, v, r0, n0)
        if not ev["pass"]:
            continue
        rows[ts] = {"direction": v.direction, "confidence": v.confidence,
                    "stop": card.stop, "tp1": card.tp1, "e1": ev["score"]}
    f = pd.DataFrame.from_dict(rows, orient="index")
    return f.sort_index() if not f.empty else f


def simulate(df, final, cash: float = 10_000):
    """محاكاة صريحة بلا Backtrader: دخول الافتتاح التالي + سبريد."""
    trades, pos = [], None
    fmap = {ts: r for ts, r in final.iterrows()}
    for k in range(len(df)):
        ts = df.index[k]
        if pos:
            hi, lo = float(df["high"].iloc[k]), float(df["low"].iloc[k])
            d = pos["dir"]
            closed = None
            if d > 0:
                if lo <= pos["sl"]:
                    closed = pos["sl"]
                elif hi >= pos["tp"]:
                    closed = pos["tp"]
            else:
                if hi >= pos["sl"]:
                    closed = pos["sl"]
                elif lo <= pos["tp"]:
                    closed = pos["tp"]
            if closed is None and k - pos["k0"] >= 8:
                closed = float(df["close"].iloc[k])  # انتهاء الصلاحية
            if closed is not None:
                trades.append(d * (closed - pos["entry"]) * pos["size"])
                pos = None
        if pos is None and ts in fmap and k + 1 < len(df):
            r = fmap[ts]
            d = int(r["direction"])
            entry = float(df["open"].iloc[k + 1]) * (1 + SPREAD_PCT * d)
            sl_d = abs(float(df["close"].iloc[k]) - float(r["stop"]))
            size = RISK_USD / sl_d if sl_d > 0 else 0
            if size > 0:
                pos = {"dir": d, "entry": entry, "sl": float(r["stop"]),
                       "tp": float(r["tp1"]), "size": size, "k0": k + 1}
    return trades


def run(symbol: str = "XAUUSD", cash: float = 10_000) -> dict:
    import time
    t0 = time.time()
    df = load_xauusd_h1()
    try:
        dxy = load_dxy_proxy()
    except Exception:
        dxy = None
    oil = load_oil()
    h4 = df.resample("4h", origin="start").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}).dropna()

    t1 = time.time()
    agent_sig = compute_agent_signals(df, dxy, oil, h4)
    t2 = time.time()

    n = int(len(df) * SPLIT)
    split_ts = df.index[n]
    sig_in = agent_sig[agent_sig.index < split_ts]
    e2 = learn_weights(sig_in, df, atr_fn(df))
    weights = e2["weights"]
    WEIGHTS_FILE.write_text(json.dumps(e2, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    t3 = time.time()

    final = finalize(df, agent_sig, weights, n)
    t4 = time.time()
    trades = simulate(df, final, cash)
    t5 = time.time()

    won = sum(1 for p in trades if p > 0)
    pnl = sum(trades)
    import statistics
    return {
        "trades": len(trades), "won": won,
        "win_rate": round(100 * won / len(trades), 1) if trades else 0,
        "pnl_net": round(pnl, 2), "final_value": round(cash + pnl, 2),
        "avg_r": round(statistics.mean([p / RISK_USD for p in trades]), 3) if trades else 0,
        "weights": weights, "e2_detail": e2["detail"],
        "timing": {"signals_s": round(t2 - t1, 1), "e2_s": round(t3 - t2, 1),
                   "finalize_s": round(t4 - t3, 1), "sim_s": round(t5 - t4, 1),
                   "total_s": round(t5 - t0, 1)},
    }
