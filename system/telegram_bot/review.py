"""طابور المراجعة — التوصية تصل للأدمن أولًا، يعتمدها بضغطة.

التلقائي: بعد auto_after_reviewed توصية مراجَعة (30 افتراضيًا)،
ينقلب الوضع إلى auto تلقائيًا — كما في التصميم.
"""
from datetime import datetime, timezone
from pathlib import Path

from . import cards, publisher, store


def _now():
    return datetime.now(timezone.utc).isoformat()


def queue(api, cfg, signal_id: int, card_text: str, chart_path=None) -> str:
    """يضع التوصية في الطابور. يرجع 'published' أو 'pending'."""
    with store.conn() as c:
        c.execute("INSERT OR REPLACE INTO pending(signal_id, card_text, chart_path, status, created_at) "
                  "VALUES(?,?,?, 'pending', ?)",
                  (signal_id, card_text, str(chart_path) if chart_path else None, _now()))
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
    with store.conn() as c:
        row = c.execute("SELECT status FROM pending WHERE signal_id=?",
                        (signal_id,)).fetchone()
        if not row or row[0] not in ("pending", "approved"):
            return False
        c.execute("UPDATE pending SET status='approved', reviewed_at=? "
                  "WHERE signal_id=?", (_now(), signal_id))
    publisher.publish(api, cfg, signal_id)
    cfg.set("reviewed_count", (cfg.reviewed_count or 0) + 1)
    if cfg.mode == "review" and cfg.reviewed_count >= cfg.auto_after_reviewed:
        cfg.set("mode", "auto")
    return True


def reject(cfg, signal_id: int) -> bool:
    with store.conn() as c:
        row = c.execute("SELECT status FROM pending WHERE signal_id=?",
                        (signal_id,)).fetchone()
        if not row or row[0] != "pending":
            return False
        c.execute("UPDATE pending SET status='rejected', reviewed_at=? "
                  "WHERE signal_id=?", (_now(), signal_id))
    return True
