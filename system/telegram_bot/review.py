"""طابور المراجعة — التوصية تصل للأدمن أولًا، يعتمدها بضغطة.

التلقائي: بعد auto_after_reviewed توصية مراجَعة (30 افتراضيًا)،
ينقلب الوضع إلى auto تلقائيًا — كما في التصميم.
التخزين عبر `backend` (SQLite محليًا، Supabase على Actions).
"""
from datetime import datetime, timezone
from pathlib import Path

from . import backend, cards, publisher


def queue(api, cfg, signal_id: int, card_text: str, chart_path=None) -> str:
    """يضع التوصية في الطابور. يرجع 'published' أو 'pending'."""
    store = backend.get_backend()
    store.queue_pending(signal_id, card_text, chart_path)
    if cfg.mode == "auto":
        publisher.publish(api, cfg, signal_id)
        return "published"
    for admin_id in cfg.admin_ids:
        try:
            caption = (f"📥 توصية جديدة بانتظار المراجعة (#{signal_id}):\n\n{card_text}")
            kb = cards.review_keyboard(signal_id)
            if chart_path and Path(chart_path).exists():
                api.send_photo(admin_id, Path(chart_path), caption, reply_markup=kb)
            else:
                api.send_message(admin_id, caption, reply_markup=kb)
        except Exception:
            pass  # الأدمن غير متاح — تبقى في الطابور حتى /pending
    return "pending"


def approve(api, cfg, signal_id: int) -> bool:
    store = backend.get_backend()
    row = store.get_pending(signal_id)
    if not row or row["status"] not in ("pending", "approved"):
        return False
    reviewed_by = (cfg.admin_ids or [None])[0]
    if not store.set_review_status(signal_id, "approved", reviewed_by=reviewed_by):
        return False
    publisher.publish(api, cfg, signal_id)
    cfg.set("reviewed_count", (cfg.reviewed_count or 0) + 1)
    if cfg.mode == "review" and cfg.reviewed_count >= cfg.auto_after_reviewed:
        cfg.set("mode", "auto")
    return True


def reject(cfg, signal_id: int) -> bool:
    store = backend.get_backend()
    row = store.get_pending(signal_id)
    if not row or row["status"] != "pending":
        return False
    reviewed_by = (cfg.admin_ids or [None])[0]
    return store.set_review_status(signal_id, "rejected", reviewed_by=reviewed_by)
