"""مسح الانتهاء: تنبيه قبل الانتهاء + إزالة تلقائية عند الانتهاء.

يعمل من cycle.py كل ساعة. كل الإرسالات best-effort (لا تكسر الدورة).
التخزين عبر `backend` (SQLite محليًا، Supabase على Actions).
"""
from datetime import datetime, timezone

from . import backend


def _parse(ts: str):
    try:
        d = datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def sweep(api, cfg):
    store = backend.get_backend()
    now = datetime.now(timezone.utc)
    for sub in store.list_active_for_sweep():
        chat_id = sub["chat_id"]
        exp = _parse(sub["expires_at"]) if sub.get("expires_at") else None
        if not exp:
            continue
        if exp <= now:
            store.set_subscriber_status(chat_id, "expired")
            try:
                api.ban(cfg.channel_id, chat_id)
                if sub.get("invite_link"):
                    api.revoke_invite_link(cfg.channel_id, sub["invite_link"])
            except Exception:
                pass
        elif (exp - now).days < cfg.expiry_warn_days and not sub.get("warned"):
            try:
                api.send_message(chat_id,
                                 f"⏰ اشتراكك ينتهي {exp.strftime('%Y-%m-%d')} — "
                                 "تواصل مع محمد للتجديد قبل انتهائه.")
            except Exception:
                pass
            store.set_warned(chat_id)
