"""النشر إلى القناة + تسجيل سجل كل مشترك.

النشر = رسالة واحدة في القناة + صف subscriber_signals لكل مشترك نشط
(سجله = التوصيات المنشورة أثناء اشتراكه النشط، كما في التصميم).
"""
from datetime import datetime, timezone
from pathlib import Path

from . import cards, store


def _now():
    return datetime.now(timezone.utc).isoformat()


def publish(api, cfg, signal_id: int) -> int | None:
    """ينشر توصية معتمدة إلى القناة (صورة + بطاقة). يرجع message_id أو None."""
    with store.conn() as c:
        row = c.execute("SELECT card_text, chart_path FROM pending WHERE signal_id=?",
                        (signal_id,)).fetchone()
        if not row:
            return None
        card_text, chart_path = row
        text = cards.channel_card(card_text, mode="paper")
        kb = cards.entered_keyboard(signal_id)
        if chart_path and Path(chart_path).exists():
            msg = api.send_photo(cfg.channel_id, Path(chart_path), text, reply_markup=kb)
        else:
            msg = api.send_message(cfg.channel_id, text, reply_markup=kb)
        mid = msg["message_id"]
        c.execute("INSERT OR REPLACE INTO deliveries(signal_id, channel_message_id, published_at) "
                  "VALUES(?,?,?)", (signal_id, mid, _now()))
        c.execute("UPDATE pending SET status='published', reviewed_at=? "
                  "WHERE signal_id=?", (_now(), signal_id))
        for (chat_id, _u, _n, _e) in store.active_subscribers(c):
            c.execute("INSERT OR IGNORE INTO subscriber_signals"
                      "(subscriber_chat_id, signal_id) VALUES(?,?)",
                      (chat_id, signal_id))
        return mid


def published_today(c) -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = c.execute("SELECT COUNT(*) FROM deliveries WHERE substr(published_at,1,10)=?",
                  (day,)).fetchone()
    return n[0] if n else 0
