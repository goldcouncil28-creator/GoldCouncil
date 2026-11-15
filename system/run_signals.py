"""المشغّل الورقي v2 — خط الـ 35 وكيل كاملًا.

الاستخدام: venv/bin/python run_signals.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data_loader import load_xauusd_h1, load_dxy_proxy, load_oil
from pipeline import run_pipeline, build_ctx
import journal
import audit

WEIGHTS_FILE = Path(__file__).parent / "data" / "learned_weights.json"


def main():
    df = load_xauusd_h1()
    print(f"الشموع: {len(df)} | آخر إغلاق: {df['close'].iloc[-1]:.2f}")
    try:
        dxy = load_dxy_proxy()
        print(f"DXY proxy: {dxy.iloc[-1]:.2f}")
    except Exception as e:
        dxy = None
        print(f"DXY: degraded ({type(e).__name__})")
    oil = load_oil()
    print(f"Oil: {'متاح' if oil is not None else 'degraded'}")

    ctx = build_ctx(df, dxy, oil)
    weights = json.loads(WEIGHTS_FILE.read_text())["weights"] if WEIGHTS_FILE.exists() else None
    print(f"الأوزان: {'مُتعلَّمة (E2)' if weights else 'ابتدائية'}")

    res = run_pipeline(df, ctx, weights)
    print(f"الحالة: {res['status']}")
    audit.log("pipeline", {k: v for k, v in res.items()
                           if k in ("status", "detail")})

    if res["status"] != "signal":
        if res["status"] == "no_signal":
            print("لا إشارة — لم تجتز السلسلة (M1/M3/E1).")
        return

    card = res["card"]
    print(f"\nE1 الجودة: {res['e1']['score']}/100")
    print(" | ".join(res["e1"]["checks"]))
    if res["m3"]["attacks"]:
        print("M3 هجمات:", "؛ ".join(res["m3"]["attacks"]))
    print("\n" + card.text() + "\n")

    sid = journal.log_signal(card, res["verdict"].votes, mode="paper")
    print("⚠️ سقف الـ 3 توصيات ممتلئ." if sid == -1
          else f"✅ سُجّلت (paper) برقم {sid}")
    audit.log("signal", {"id": sid, "card": card.text(),
                         "e1": res["e1"]["score"]})


if __name__ == "__main__":
    main()
