"""تسوية التوصيات المفتوحة: مراقبة السعر حتى الهدف/الوقف/انتهاء الصلاحية.

عند الإغلاق: يحدّث السجل + يعدّل رسالة القناة بسطر النتيجة.
السعر: آخر 3 أيام H1 من Dukascopy (خفيف، بلا تحميل 6 شهور)؛
وعند فشل التحميل الحي يُستخدم باركيه الكاش المحلي إن وُجد.
TP2 يُفحص قبل TP1؛ إغلاق بانتهاء الوقت فقط بلا سعر خروج —
السعر لا يُختلَق أبدًا (exit_price=None, pnl_r=None, وبلا صف settlements).
كل صفقة في try/except خاص بها فلا تُسقط صفقة واحدة باقي التسوية.
التخزين عبر `backend` (SQLite محليًا، Supabase على Actions).
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import backend, cards

VALIDITY_HOURS = 8
CACHE_PARQUET = Path(__file__).parent.parent / "data" / "xauusd_h1.parquet"


def _latest_bars(start):
    """H1 bars from `start` to now. Live Dukascopy first; on failure the
    local parquet cache, filtered to the SAME window — never a shorter one.

    A shorter window would mis-settle old signals: bars starting after a
    signal's entry can only see levels already passed (e.g. an old short
    looks like an instant TP2 hit because its stop-hit happened before the
    window). _settle_one refuses to judge any signal the bars don't cover.
    """
    from dukascopy_python import fetch, INTERVAL_HOUR_1, OFFER_SIDE_BID
    end = datetime.now(timezone.utc)
    try:
        df = fetch("xauusd", INTERVAL_HOUR_1, OFFER_SIDE_BID, start, end)
    except Exception:
        df = None
    if df is not None and len(df):
        df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
        return df
    # Fallback: cached parquet (Actions cache, or the VM's data/ cache).
    try:
        import pandas as pd
        cached = pd.read_parquet(CACHE_PARQUET)
        if len(cached):
            cached.index = cached.index.tz_localize("UTC") if cached.index.tz is None else cached.index.tz_convert("UTC")
            return cached[cached.index > start]
    except Exception:
        pass
    return None


def settle(api, cfg):
    store = backend.get_backend()
    opens = store.list_open_signals()
    if not opens:
        return 0
    # Fetch from the OLDEST open signal — never a fixed 3-day window.
    oldest = min(_parse_ts(r["ts"]) for r in opens)
    start = oldest
    cap = datetime.now(timezone.utc) - timedelta(days=180)
    if start < cap:
        start = cap
    bars = _latest_bars(start)
    if bars is None or len(bars) == 0:
        return 0
    closed = 0
    for r in opens:
        try:
            closed += _settle_one(api, cfg, store, bars, r)
        except Exception as e:
            print(f"settle: signal #{r.get('id')} error: {type(e).__name__}")
    return closed


def _parse_ts(ts):
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _settle_one(api, cfg, store, bars, r):
    direction = 1 if r["direction"] in ("شراء", "long") else -1
    ts = _parse_ts(r["ts"])
    # Coverage guard: if the earliest bar is more than 2h after the entry,
    # the bars don't reach back to the signal — judging would be a guess
    # (an old short would look like an instant TP2 hit). Leave it open.
    if len(bars) and (bars.index[0].to_pydatetime() - ts) > timedelta(hours=2):
        print(f"settle: signal #{r.get('id')} skipped — no bars back to its entry time")
        return 0
    fut = bars[bars.index > ts]
    status, exit_price = None, None
    for _, b in fut.iterrows():
        hi, lo = float(b["high"]), float(b["low"])
        if direction > 0:
            if lo <= r["stop"]:
                status, exit_price = "sl", r["stop"]
                break
            if hi >= r["tp2"]:
                status, exit_price = "tp2", r["tp2"]
                break
            if hi >= r["tp1"]:
                status, exit_price = "tp1", r["tp1"]
                break
        else:
            if hi >= r["stop"]:
                status, exit_price = "sl", r["stop"]
                break
            if lo <= r["tp2"]:
                status, exit_price = "tp2", r["tp2"]
                break
            if lo <= r["tp1"]:
                status, exit_price = "tp1", r["tp1"]
                break
    if status is None and len(fut) and \
            (datetime.now(timezone.utc) - ts) > timedelta(hours=VALIDITY_HOURS):
        # انتهاء الوقت فقط: بلا سعر خروج مختلَق.
        status, exit_price = "expired", None
    if status is None:
        return 0
    if exit_price is None:
        pnl_r = None
    else:
        sl_dist = abs(r["entry"] - r["stop"])
        pnl_r = round(direction * (exit_price - r["entry"]) / sl_dist, 3) if sl_dist else 0
    if not store.close_signal(r["id"], status, exit_price, pnl_r):
        return 0
    _announce(api, cfg, store, r["id"], status, pnl_r)
    return 1


def _announce(api, cfg, store, signal_id: int, status: str, pnl_r):
    """يعدّل رسالة القناة بسطر النتيجة (caption لو كانت صورة)."""
    try:
        d = store.get_delivery(signal_id)
        p = store.get_pending(signal_id)
        if not d or not d.get("channel_message_id") or not p:
            return
        text = cards.channel_card(p["card_text"], mode="paper") + cards.result_line(status, pnl_r)
        if p.get("chart_path"):
            api.edit_message_caption(cfg.channel_id, d["channel_message_id"], text)
        else:
            api.edit_message_text(cfg.channel_id, d["channel_message_id"], text)
    except Exception:
        pass
