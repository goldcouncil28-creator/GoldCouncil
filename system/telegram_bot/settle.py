"""تسوية التوصيات المفتوحة: مراقبة السعر حتى الهدف/الوقف/انتهاء الصلاحية.

عند الإغلاق: يحدّث journal + يعدّل رسالة القناة بسطر النتيجة.
السعر: آخر 3 أيام H1 من Dukascopy (خفيف، بلا تحميل 6 شهور).
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import cards, store

JOURNAL_DB = Path(__file__).parent.parent / "data" / "journal.db"
VALIDITY_HOURS = 8


def _latest_bars():
    from dukascopy_python import fetch, INTERVAL_HOUR_1, OFFER_SIDE_BID
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=3)
    df = fetch("xauusd", INTERVAL_HOUR_1, OFFER_SIDE_BID, start, end)
    df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
    return df


def settle(api, cfg):
    try:
        bars = _latest_bars()
    except Exception:
        return 0
    jc = sqlite3.connect(JOURNAL_DB)
    jc.row_factory = sqlite3.Row
    rows = jc.execute("SELECT * FROM signals WHERE status='open'").fetchall()
    closed = 0
    for r in rows:
        direction = 1 if r["direction"] == "شراء" else -1
        ts = datetime.fromisoformat(r["ts"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        fut = bars[bars.index > ts]
        status, exit_price = None, None
        for _, b in fut.iterrows():
            hi, lo = float(b["high"]), float(b["low"])
            if direction > 0:
                if lo <= r["stop"]:
                    status, exit_price = "sl", r["stop"]
                    break
                if hi >= r["tp1"]:
                    status, exit_price = "tp1", r["tp1"]
                    break
                if hi >= r["tp2"]:
                    status, exit_price = "tp2", r["tp2"]
                    break
            else:
                if hi >= r["stop"]:
                    status, exit_price = "sl", r["stop"]
                    break
                if lo <= r["tp1"]:
                    status, exit_price = "tp1", r["tp1"]
                    break
                if lo <= r["tp2"]:
                    status, exit_price = "tp2", r["tp2"]
                    break
        if status is None and fut.empty is False and \
                (datetime.now(timezone.utc) - ts) > timedelta(hours=VALIDITY_HOURS):
            status, exit_price = "expired", float(fut["close"].iloc[-1])
        if status is None:
            continue
        sl_dist = abs(r["entry"] - r["stop"])
        pnl_r = direction * (exit_price - r["entry"]) / sl_dist if sl_dist else 0
        jc.execute("UPDATE signals SET status=?, exit_price=?, pnl_r=? WHERE id=?",
                   (status, exit_price, round(pnl_r, 3), r["id"]))
        jc.commit()
        closed += 1
        _announce(api, cfg, r["id"], status, round(pnl_r, 3))
    jc.close()
    return closed


def _announce(api, cfg, signal_id: int, status: str, pnl_r: float):
    """يعدّل رسالة القناة بسطر النتيجة (caption لو كانت صورة)."""
    try:
        with store.conn() as c:
            d = c.execute("SELECT channel_message_id FROM deliveries WHERE signal_id=?",
                          (signal_id,)).fetchone()
            p = c.execute("SELECT card_text, chart_path FROM pending WHERE signal_id=?",
                          (signal_id,)).fetchone()
        if not d or not p:
            return
        text = cards.channel_card(p[0], mode="paper") + cards.result_line(status, pnl_r)
        if p[1]:
            api.edit_message_caption(cfg.channel_id, d[0], text)
        else:
            api.edit_message_text(cfg.channel_id, d[0], text)
    except Exception:
        pass
