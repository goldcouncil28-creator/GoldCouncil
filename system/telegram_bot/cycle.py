"""دورة البوت الكاملة (تُشغَّل كل ساعة عبر cron):

1. خط الإشارة → journal (سقف 3/يوم) → طابور المراجعة / نشر تلقائي
2. تسوية التوصيات المفتوحة
3. مسح الانتهاء

config-gated: بلا توكن/قناة/أدمن → خروج هادئ.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.api import BotApi
from telegram_bot.config import Config
from telegram_bot import backend, expiry, review, settle


def main() -> int:
    cfg = Config.load()
    if not cfg.configured:
        print("bot: not configured, skipping")
        return 0
    api = BotApi(cfg.token)

    # 1. خط الإشارة
    try:
        from data_loader import load_xauusd_h1, load_dxy_proxy, load_oil
        from pipeline import run_pipeline, build_ctx
        store = backend.get_backend()
        df = load_xauusd_h1()
        try:
            dxy = load_dxy_proxy()
        except Exception:
            dxy = None
        oil = load_oil()
        res = run_pipeline(df, build_ctx(df, dxy, oil))
        if res["status"] == "signal":
            card = res["card"]
            sid = store.log_signal(card, res["verdict"].votes,
                                   e1=res.get("e1"), m3=res.get("m3"),
                                   r0=res.get("r0"), mode="paper")
            if sid == -1:
                print("bot: daily cap reached")
            elif sid == -2:
                print("bot: duplicate signal, skipped")
            else:
                chart = None
                try:
                    from telegram_bot.charts import render_signal_chart
                    chart = render_signal_chart(
                        df, card,
                        path=Path(__file__).parent / "charts" /
                        f"signal_{card.symbol}_{sid}.png")
                except Exception as e:
                    print(f"bot: chart failed: {type(e).__name__}")
                print(f"bot: queued signal #{sid} -> "
                      f"{review.queue(api, cfg, sid, card.text(), chart)}")
        else:
            print(f"bot: no signal ({res['status']})")
    except Exception as e:
        print(f"bot: pipeline error: {type(e).__name__}: {e}")

    # 2. تسوية + 3. انتهاء
    try:
        print(f"bot: settled {settle.settle(api, cfg)} signals")
    except Exception as e:
        print(f"bot: settle error: {type(e).__name__}")
    try:
        expiry.sweep(api, cfg)
    except Exception as e:
        print(f"bot: expiry error: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
