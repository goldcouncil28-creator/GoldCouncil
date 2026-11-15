"""النشر إلى القناة + تسجيل سجل كل مشترك.

النشر = رسالة واحدة في القناة + صف subscriber_signals لكل مشترك نشط
(سجله = التوصيات المنشورة أثناء اشتراكه النشط، كما في التصميم).
التخزين عبر `backend` (SQLite محليًا، Supabase على Actions).
"""
from datetime import datetime, timezone
from pathlib import Path

from . import backend, cards


def _now():
    return datetime.now(timezone.utc).isoformat()


def publish(api, cfg, signal_id: int) -> int | None:
    """ينشر توصية معتمدة إلى القناة (صورة + بطاقة). يرجع message_id أو None."""
    store = backend.get_backend()
    row = store.get_pending(signal_id)
    if not row:
        return None
    card_text, chart_path = row["card_text"], row["chart_path"]
    text = cards.channel_card(card_text, mode="paper")
    kb = cards.entered_keyboard(signal_id)
    if chart_path and Path(chart_path).exists():
        msg = api.send_photo(cfg.channel_id, Path(chart_path), text, reply_markup=kb)
    else:
        msg = api.send_message(cfg.channel_id, text, reply_markup=kb)
    mid = msg["message_id"]
    if not store.publish_signal(signal_id, mid):
        return None
    return mid


def published_today(c=None) -> int:
    return backend.get_backend().published_today()
