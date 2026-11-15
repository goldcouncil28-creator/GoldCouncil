"""معالجة تحديثات البوت: أوامر المشتركين + أوامر الأدمن + أزرار.

أوامر المشترك: /start /stats /history /help
أوامر الأدمن (ADMIN_IDS فقط): /activate /deactivate /kick /list
  /pending /approve /reject /mode /admin /audit
لوحة الأدمن: /admin — أزرار (مشتركون / بانتظار / إحصائيات / وضع / سجل).
أزرار: اعتماد/رفض (أدمن) + «دخلت الصفقة» (مشترك).
حماية الأدمن: هوية Telegram ID + حد 20 إجراء/دقيقة + سجل تدقيق
  (admin_audit) لكل عملية إدارية ومحاولة غير مصرّح بها.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import cards, review, store

JOURNAL_DB = Path(__file__).parent.parent / "data" / "journal.db"

RATE_WINDOW_SECONDS = 60
RATE_MAX_ACTIONS = 20

ADMIN_COMMANDS = {"/activate", "/deactivate", "/kick", "/list", "/pending",
                  "/approve", "/reject", "/mode", "/admin", "/audit"}


def _now():
    return datetime.now(timezone.utc)


def _is_admin(cfg, chat_id: int) -> bool:
    return chat_id in (cfg.admin_ids or [])


def _attach(c):
    # ATTACH لا يقبل بارامترات مربوطة — المسار من كودنا نفسه
    c.execute(f"ATTACH DATABASE '{JOURNAL_DB}' AS j")
    return c


def _audit(admin_id, action, target="", detail="", ok=1):
    """سجل تدقيق: كل عملية إدارية ومحاولة غير مصرّح بها."""
    try:
        with store.conn() as c:
            c.execute("INSERT INTO admin_audit(ts, admin_chat_id, action, target, detail, ok) "
                      "VALUES(?,?,?,?,?,?)",
                      (_now().isoformat(), admin_id, action, str(target), detail, int(ok)))
    except Exception:
        pass


def _rate_ok(admin_id: int) -> bool:
    """حد 20 إجراء إداري/دقيقة لكل أدمن — محفوظ في SQLite فيبقى عبر دورات poll."""
    try:
        with store.conn() as c:
            cutoff = (_now() - timedelta(seconds=RATE_WINDOW_SECONDS)).isoformat()
            c.execute("DELETE FROM admin_rate WHERE ts < ?", (cutoff,))
            n = c.execute("SELECT COUNT(*) FROM admin_rate WHERE admin_chat_id=?",
                          (admin_id,)).fetchone()[0]
            if n >= RATE_MAX_ACTIONS:
                return False
            c.execute("INSERT INTO admin_rate(admin_chat_id, ts) VALUES(?, ?)",
                      (admin_id, _now().isoformat()))
            return True
    except Exception:
        return True  # لو تعطل التقييد لا نقفل الأدمن


def handle_update(api, cfg, update: dict):
    cb = update.get("callback_query")
    if cb:
        _handle_callback(api, cfg, cb)
        return
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat_id = (msg.get("chat") or {}).get("id")
    if not text or not chat_id:
        return
    if not text.startswith("/"):
        return
    parts = text.split()
    cmd, args = parts[0].split("@")[0], parts[1:]
    if _is_admin(cfg, chat_id):
        if cmd in ADMIN_COMMANDS:
            if not _rate_ok(chat_id):
                api.send_message(chat_id, "⏳ تمهل قليلًا — تجاوزت الحد (20 إجراء/دقيقة).")
                _audit(chat_id, "rate_limit", cmd, ok=0)
                return
            handled = _handle_admin(api, cfg, chat_id, cmd, args)
            _audit(chat_id, cmd, " ".join(args))
            if handled:
                return
        elif _handle_admin(api, cfg, chat_id, cmd, args):
            return
    elif cmd in ADMIN_COMMANDS:
        _audit(chat_id, "unauthorized", cmd, ok=0)
        api.send_message(chat_id, "هذا الأمر للأدمن فقط.")
        return
    _handle_user(api, cfg, chat_id, cmd, args,
                 username=(msg.get("from") or {}).get("username"))


def _handle_user(api, cfg, chat_id, cmd, args, username=None):
    with store.conn() as c:
        sub = c.execute("SELECT status, expires_at FROM subscribers WHERE chat_id=?",
                        (chat_id,)).fetchone()
    if cmd == "/start":
        if sub and sub[0] == "active":
            api.send_message(chat_id,
                             f"{cfg.welcome}\n\nاشتراكك نشط حتى {sub[1][:10]}.")
        else:
            api.send_message(chat_id,
                             f"{cfg.welcome}\n\nللاشتراك تواصل مع محمد مباشرة، "
                             "وبعد التحويل سيتم تفعيلك هنا.")
    elif cmd == "/stats":
        if not sub:
            api.send_message(chat_id, "ليس لديك سجل بعد — اشترك أولًا عبر محمد.")
            return
        with store.conn() as c:
            _attach(c)
            rows = c.execute(
                "SELECT j.status, COUNT(*) FROM subscriber_signals ss "
                "JOIN j.signals j ON j.id = ss.signal_id "
                "WHERE ss.subscriber_chat_id=? GROUP BY j.status",
                (chat_id,)).fetchall()
        wins = sum(n for s, n in rows if s in ("tp1", "tp2"))
        losses = sum(n for s, n in rows if s == "sl")
        total = wins + losses
        api.send_message(chat_id,
                         f"📊 سجلك الشخصي:\nصفقات مغلقة: {total}\n"
                         f"رابحة: {wins} | خاسرة: {losses}\n"
                         f"نسبة الفوز: {round(100*wins/total, 1) if total else 0}%")
    elif cmd == "/history":
        with store.conn() as c:
            _attach(c)
            rows = c.execute(
                "SELECT j.id, j.symbol, j.direction, j.status FROM deliveries d "
                "JOIN j.signals j ON j.id = d.signal_id "
                "ORDER BY d.published_at DESC LIMIT 10").fetchall()
        if not rows:
            api.send_message(chat_id, "لا توصيات منشورة بعد.")
            return
        lines = [f"#{i} {sym} {d} — {s}" for i, sym, d, s in rows]
        api.send_message(chat_id, "🕘 آخر التوصيات:\n" + "\n".join(lines))
    elif cmd == "/help":
        api.send_message(chat_id,
                         "/start — الترحيب وحالة الاشتراك\n"
                         "/stats — سجلك الشخصي\n/history — آخر التوصيات\n/help — هذه الرسالة")


# ---------------------------------------------------------------- أوامر الأدمن

def _admin_activate(api, cfg, uid, days, name=""):
    """تفعيل مشترك + رابط دعوة + رسالة له. يرجع نص النتيجة للأدمن."""
    exp = (_now() + timedelta(days=days)).isoformat()
    link = None
    try:
        link = api.create_invite_link(cfg.channel_id, name=f"sub-{uid}")["invite_link"]
    except Exception:
        pass
    with store.conn() as c:
        c.execute("INSERT INTO subscribers(chat_id, name, status, activated_at, expires_at, invite_link, warned) "
                  "VALUES(?,?, 'active', ?, ?, ?, 0) "
                  "ON CONFLICT(chat_id) DO UPDATE SET status='active', expires_at=excluded.expires_at, "
                  "invite_link=excluded.invite_link, warned=0",
                  (uid, name, _now().isoformat(), exp, link))
    try:
        api.send_message(uid, f"{cfg.welcome}\n\nتم تفعيل اشتراكك حتى {exp[:10]}."
                         + (f"\nرابط القناة: {link}" if link else ""))
        return f"✅ تم تفعيل {uid} حتى {exp[:10]}"
    except Exception:
        return (f"✅ تم تفعيل {uid} حتى {exp[:10]} — لكن لم أستطع مراسلته "
                "(لم يبدأ البوت بعد)." +
                (f"\nانسخ له الرابط: {link}" if link else ""))


def _admin_set_status(api, cfg, uid, status):
    """إيقاف/طرد: تحديث الحالة + حظر من القناة + إلغاء رابط الدعوة."""
    with store.conn() as c:
        row = c.execute("SELECT invite_link FROM subscribers WHERE chat_id=?",
                        (uid,)).fetchone()
        c.execute("UPDATE subscribers SET status=? WHERE chat_id=?", (status, uid))
    try:
        api.ban(cfg.channel_id, uid)
        if row and row[0]:
            api.revoke_invite_link(cfg.channel_id, row[0])
    except Exception:
        pass
    return f"✅ {uid} → {status}"


def _handle_admin(api, cfg, chat_id, cmd, args) -> bool:
    if cmd == "/admin":
        api.send_message(chat_id, _panel_main_text(cfg),
                         reply_markup=cards.panel_main_keyboard())
        return True
    if cmd == "/audit":
        with store.conn() as c:
            rows = c.execute("SELECT ts, action, target, ok FROM admin_audit "
                             "ORDER BY id DESC LIMIT 10").fetchall()
        if not rows:
            api.send_message(chat_id, "🧾 سجل العمليات:\nلا عمليات مسجلة بعد.")
        else:
            lines = [f"{t[11:16]} {a} {tg} {'✅' if ok else '⛔'}"
                     for t, a, tg, ok in rows]
            api.send_message(chat_id, "🧾 آخر عمليات الأدمن:\n" + "\n".join(lines))
        return True
    if cmd == "/activate" and len(args) >= 2:
        try:
            uid, days = int(args[0]), int(args[1])
        except ValueError:
            api.send_message(chat_id, "الاستخدام: /activate <chat_id> <days> [name]")
            return True
        name = args[2] if len(args) > 2 else ""
        api.send_message(chat_id, _admin_activate(api, cfg, uid, days, name))
        return True
    if cmd in ("/deactivate", "/kick") and args:
        try:
            uid = int(args[0])
        except ValueError:
            return True
        status = "paused" if cmd == "/deactivate" else "kicked"
        api.send_message(chat_id, _admin_set_status(api, cfg, uid, status))
        return True
    if cmd == "/list":
        with store.conn() as c:
            rows = c.execute("SELECT chat_id, name, status, expires_at FROM subscribers "
                             "ORDER BY status, expires_at").fetchall()
        lines = [f"{i} {n or ''} — {s} حتى {e[:10] if e else '?'}" for i, n, s, e in rows]
        api.send_message(chat_id, "👥 المشتركون:\n" + ("\n".join(lines) if lines else "لا أحد"))
        return True
    if cmd == "/pending":
        with store.conn() as c:
            rows = c.execute("SELECT signal_id, created_at FROM pending "
                             "WHERE status='pending' ORDER BY created_at").fetchall()
        lines = [f"#{i} منذ {t[11:16]}" for i, t in rows]
        api.send_message(chat_id, "📥 بانتظار المراجعة:\n" + ("\n".join(lines) if lines else "لا شيء"))
        return True
    if cmd in ("/approve", "/reject") and args:
        try:
            sid = int(args[0])
        except ValueError:
            return True
        ok = review.approve(api, cfg, sid) if cmd == "/approve" else review.reject(cfg, sid)
        api.send_message(chat_id, f"{'✅ نُشرت' if ok and cmd == '/approve' else '❌ رُفضت' if ok else '⚠️ غير موجودة'} #{sid}")
        return True
    if cmd == "/mode":
        api.send_message(chat_id,
                         f"الوضع: {cfg.mode} | توصيات مراجَعة: {cfg.reviewed_count} "
                         f"(التلقائي بعد {cfg.auto_after_reviewed})")
        return True
    return False


# ---------------------------------------------------------------- لوحة الأدمن

def _cb_chat(cb):
    return (cb.get("message") or {}).get("chat", {}).get("id")


def _cb_mid(cb):
    return (cb.get("message") or {}).get("message_id")


def _panel_main_text(cfg):
    return (f"🎛️ لوحة تحكم Gold Council\n"
            f"الوضع: {cfg.mode} | توصيات مراجَعة: {cfg.reviewed_count or 0} "
            f"(التلقائي بعد {cfg.auto_after_reviewed})")


def _panel_show(api, cfg, chat_id, message_id, text, reply_markup):
    if not chat_id or not message_id:
        return
    try:
        api.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        try:
            api.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception:
            pass


def _panel_view_main(api, cfg, cb):
    _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb),
                _panel_main_text(cfg), cards.panel_main_keyboard())


def _panel_view_subs(api, cfg, cb):
    with store.conn() as c:
        rows = c.execute("SELECT chat_id, name, status, expires_at FROM subscribers "
                         "ORDER BY status, expires_at LIMIT 10").fetchall()
    if not rows:
        _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb),
                    "👥 المشتركون:\nلا أحد بعد.", cards.panel_back_keyboard())
        return
    lines = [f"{'🟢' if s == 'active' else '🔴'} {i} {n or ''} — {s} حتى {e[:10] if e else '?'}"
             for i, n, s, e in rows]
    kb = {"inline_keyboard": [
        [{"text": f"{n or i} ({s})", "callback_data": f"sub:{i}"}] for i, n, s, e in rows
    ] + [[{"text": "⬅️ رجوع", "callback_data": "panel:main"}]]}
    _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb),
                "👥 المشتركون (دوس على واحد للتحكم):\n" + "\n".join(lines), kb)


def _panel_view_pending(api, cfg, cb):
    with store.conn() as c:
        rows = c.execute("SELECT signal_id, created_at FROM pending "
                         "WHERE status='pending' ORDER BY created_at").fetchall()
    if not rows:
        _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb),
                    "📥 بانتظار المراجعة:\nلا شيء.", cards.panel_back_keyboard())
        return
    lines = [f"#{i} منذ {t[11:16]}" for i, t in rows]
    kb = {"inline_keyboard": [
        [{"text": f"✅ #{i}", "callback_data": f"approve:{i}"},
         {"text": f"❌ #{i}", "callback_data": f"reject:{i}"}] for i, _ in rows
    ] + [[{"text": "⬅️ رجوع", "callback_data": "panel:main"}]]}
    _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb),
                "📥 بانتظار المراجعة:\n" + "\n".join(lines), kb)


def _panel_view_stats(api, cfg, cb):
    with store.conn() as c:
        subs = c.execute("SELECT status, COUNT(*) FROM subscribers GROUP BY status").fetchall()
        pend = c.execute("SELECT COUNT(*) FROM pending WHERE status='pending'").fetchone()[0]
        try:
            _attach(c)
            rows = c.execute("SELECT j.status, COUNT(*) FROM deliveries d "
                             "JOIN j.signals j ON j.id = d.signal_id GROUP BY j.status").fetchall()
        except Exception:
            rows = []
    wins = sum(n for s, n in rows if s in ("tp1", "tp2"))
    losses = sum(n for s, n in rows if s == "sl")
    total = wins + losses
    sub_line = " | ".join(f"{s}: {n}" for s, n in subs) if subs else "لا مشتركين"
    text = (f"📊 الإحصائيات:\nالمشتركون: {sub_line}\n"
            f"بانتظار المراجعة: {pend}\n"
            f"صفقات مغلقة: {total} (رابحة {wins} | خاسرة {losses})\n"
            f"الوضع: {cfg.mode} | مراجَعة: {cfg.reviewed_count or 0}/{cfg.auto_after_reviewed}")
    _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb), text, cards.panel_back_keyboard())


def _panel_view_mode(api, cfg, cb):
    text = (f"⚙️ الوضع الحالي: {cfg.mode}\n"
            f"توصيات مراجَعة: {cfg.reviewed_count or 0} (التلقائي بعد {cfg.auto_after_reviewed})\n"
            "في وضع المراجعة كل توصية توصلك أولًا للاعتماد، وفي التلقائي تُنشر مباشرة.")
    label = "🔀 بدّل للمراجعة" if cfg.mode == "auto" else "🔀 بدّل للتلقائي"
    kb = {"inline_keyboard": [[{"text": label, "callback_data": "panel:mode_toggle"}],
                              [{"text": "⬅️ رجوع", "callback_data": "panel:main"}]]}
    _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb), text, kb)


def _panel_view_audit(api, cfg, cb):
    with store.conn() as c:
        rows = c.execute("SELECT ts, action, target, ok FROM admin_audit "
                         "ORDER BY id DESC LIMIT 10").fetchall()
    if not rows:
        text = "🧾 سجل العمليات:\nلا عمليات مسجلة بعد."
    else:
        lines = [f"{t[11:16]} {a} {tg[:30]} {'✅' if ok else '⛔'}"
                 for t, a, tg, ok in rows]
        text = "🧾 آخر عمليات الأدمن:\n" + "\n".join(lines)
    _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb), text, cards.panel_back_keyboard())


def _handle_panel(api, cfg, cb, view):
    if view == "main":
        _panel_view_main(api, cfg, cb)
    elif view == "subs":
        _panel_view_subs(api, cfg, cb)
    elif view == "pending":
        _panel_view_pending(api, cfg, cb)
    elif view == "stats":
        _panel_view_stats(api, cfg, cb)
    elif view == "mode":
        _panel_view_mode(api, cfg, cb)
    elif view == "mode_toggle":
        new = "auto" if cfg.mode != "auto" else "review"
        cfg.set("mode", new)
        api.answer_callback(cb["id"], f"الوضع الآن: {new}")
        _panel_view_mode(api, cfg, cb)
        return
    elif view == "audit":
        _panel_view_audit(api, cfg, cb)
    else:
        return
    api.answer_callback(cb["id"])


def _handle_sub_detail(api, cfg, cb, sid_str, answer=True):
    try:
        uid = int(sid_str)
    except ValueError:
        if answer:
            api.answer_callback(cb["id"], "؟")
        return
    with store.conn() as c:
        row = c.execute("SELECT chat_id, username, name, status, activated_at, expires_at, invite_link "
                        "FROM subscribers WHERE chat_id=?", (uid,)).fetchone()
    if not row:
        if answer:
            api.answer_callback(cb["id"], "غير موجود")
        return
    cid, username, name, status, act, exp, link = row
    text = (f"👤 {name or username or cid}\nID: {cid}\nالحالة: {status}\n"
            f"مفعّل: {act[:10] if act else '؟'} | ينتهي: {exp[:10] if exp else '؟'}\n"
            f"الرابط: {link or '—'}")
    kb = {"inline_keyboard": [
        [{"text": "✅ تفعيل 30 يوم", "callback_data": f"subact:act30:{cid}"}],
        [{"text": "⏸️ إيقاف", "callback_data": f"subact:pause:{cid}"},
         {"text": "⛔ طرد", "callback_data": f"subact:kick:{cid}"}],
        [{"text": "⬅️ رجوع للمشتركين", "callback_data": "panel:subs"}],
    ]}
    _panel_show(api, cfg, _cb_chat(cb), _cb_mid(cb), text, kb)
    if answer:
        api.answer_callback(cb["id"])


def _handle_sub_action(api, cfg, cb, parts):
    if len(parts) < 2:
        return
    action, sid_str = parts[0], parts[1]
    try:
        uid = int(sid_str)
    except ValueError:
        return
    if action == "act30":
        result = _admin_activate(api, cfg, uid, 30)
    elif action == "pause":
        result = _admin_set_status(api, cfg, uid, "paused")
    elif action == "kick":
        result = _admin_set_status(api, cfg, uid, "kicked")
    else:
        return
    api.answer_callback(cb["id"], result[:180])
    _handle_sub_detail(api, cfg, cb, sid_str, answer=False)


# ---------------------------------------------------------------- الأزرار

def _handle_callback(api, cfg, cb: dict):
    data = cb.get("data", "")
    uid = (cb.get("from") or {}).get("id")
    parts = data.split(":")
    kind = parts[0] if parts else ""
    if kind in ("panel", "sub", "subact", "approve", "reject"):
        if not _is_admin(cfg, uid):
            api.answer_callback(cb["id"], "للأدمن فقط")
            _audit(uid, "unauthorized", data, ok=0)
            return
        if not _rate_ok(uid):
            api.answer_callback(cb["id"], "⏳ تمهل قليلًا")
            _audit(uid, "rate_limit", data, ok=0)
            return
        _audit(uid, "callback", data)
        if kind == "panel":
            _handle_panel(api, cfg, cb, parts[1] if len(parts) > 1 else "main")
            return
        if kind == "sub":
            _handle_sub_detail(api, cfg, cb, parts[1] if len(parts) > 1 else "")
            return
        if kind == "subact":
            _handle_sub_action(api, cfg, cb, parts[1:])
            return
        # approve / reject: يكمل للمنطق الموجود أدناه
    try:
        kind, sid = data.split(":")
        sid = int(sid)
    except ValueError:
        return
    if kind in ("approve", "reject"):
        if not _is_admin(cfg, uid):
            api.answer_callback(cb["id"], "للأدمن فقط")
            return
        ok = review.approve(api, cfg, sid) if kind == "approve" else review.reject(cfg, sid)
        api.answer_callback(cb["id"], "تم ✅" if ok else "انتهت بالفعل")
        if ok:
            api.send_message(uid, f"#{sid}: {'نُشرت في القناة ✅' if kind == 'approve' else 'رُفضت ❌'}")
        # لو الضغطة من لوحة «بانتظار المراجعة» حدّث اللوحة نفسها
        msg = cb.get("message") or {}
        if (msg.get("text") or "").startswith("📥 بانتظار المراجعة:"):
            _panel_view_pending(api, cfg, cb)
        return
    elif kind == "entered":
        with store.conn() as c:
            row = c.execute("SELECT 1 FROM subscriber_signals "
                            "WHERE subscriber_chat_id=? AND signal_id=?", (uid, sid)).fetchone()
            if row:
                c.execute("UPDATE subscriber_signals SET entered_self=1 "
                          "WHERE subscriber_chat_id=? AND signal_id=?", (uid, sid))
                api.answer_callback(cb["id"], "تم تسجيل دخولك ✅")
            else:
                api.answer_callback(cb["id"], "هذه التوصية ليست في سجلك")
