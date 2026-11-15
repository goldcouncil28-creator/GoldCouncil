"""مسح الانتهاء: تنبيه قبل الانتهاء + إزالة تلقائية عند الانتهاء.

يعمل من cycle.py كل ساعة. كل الإرسالات best-effort (لا تكسر الدورة).
"""
from datetime import datetime, timezone

from . import store


def _parse(ts: str):
    try:
        d = datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def sweep(api, cfg):
    now = datetime.now(timezone.utc)
    with store.conn() as c:
        rows = c.execute("SELECT chat_id, expires_at, invite_link, warned "
                         "FROM subscribers WHERE status='active'").fetchall()
        for chat_id, exp_s, link, warned in rows:
            exp = _parse(exp_s) if exp_s else None
            if not exp:
                continue
            if exp <= now:
                c.execute("UPDATE subscribers SET status='expired' WHERE chat_id=?",
                          (chat_id,))
                try:
                    api.ban(cfg.channel_id, chat_id)
                    if link:
                        api.revoke_invite_link(cfg.channel_id, link)
                except Exception:
                    pass
            elif (exp - now).days < cfg.expiry_warn_days and not warned:
                try:
                    api.send_message(chat_id,
                                     f"⏰ اشتراكك ينتهي {exp.strftime('%Y-%m-%d')} — "
                                     "تواصل مع محمد للتجديد قبل انتهائه.")
                except Exception:
                    pass
                c.execute("UPDATE subscribers SET warned=1 WHERE chat_id=?", (chat_id,))
