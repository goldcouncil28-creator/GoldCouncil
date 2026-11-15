"""اختبار لوحة تحكم الأدمن في تيليجرام — واجهة وهمية، بلا شبكة.

يغطي: /admin + الأزرار (مشتركون/بانتظار/إحصائيات/وضع/سجل) +
إجراءات المشترك من اللوحة + الاعتماد من اللوحة + تبديل الوضع +
سجل التدقيق + حد المعدل (20/دقيقة) + رفض غير الأدمن +
إصلاح review.queue مع صورة شارت.
"""
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from telegram_bot import commands, review, store
from telegram_bot.config import Config


class FakeApi:
    def __init__(self):
        self.sent = []          # (chat_id, text, reply_markup)
        self.bans = []
        self.revokes = []
        self._mid = 100

    def send_message(self, chat_id, text, reply_markup=None):
        self._mid += 1
        self.sent.append((chat_id, text, reply_markup))
        return {"message_id": self._mid, "chat": {"id": chat_id}}

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.sent.append((chat_id, f"[edit {message_id}] {text}", reply_markup))
        return True

    def edit_message_caption(self, chat_id, message_id, caption, reply_markup=None):
        self.sent.append((chat_id, f"[edit-cap {message_id}] {caption}", reply_markup))
        return True

    def send_photo(self, chat_id, photo_path, caption, reply_markup=None):
        self._mid += 1
        self.sent.append((chat_id, f"[photo] {caption}", reply_markup))
        return {"message_id": self._mid, "chat": {"id": chat_id}}

    def create_invite_link(self, chat_id, name):
        return {"invite_link": f"https://t.me/+fake_{name}"}

    def revoke_invite_link(self, chat_id, invite_link):
        self.revokes.append(invite_link)

    def ban(self, chat_id, user_id):
        self.bans.append(user_id)

    def unban(self, chat_id, user_id):
        pass

    def answer_callback(self, callback_query_id, text=None):
        self.sent.append(("cb", text or "ok", None))


def make_cfg(tmp: Path) -> Config:
    tok = tmp / ".bot-token"
    tok.write_text("FAKE:123")
    cfg = Config({"token_file": str(tok), "channel_id": -100999,
                  "admin_ids": [111], "mode": "review",
                  "reviewed_count": 0, "auto_after_reviewed": 30,
                  "expiry_warn_days": 3, "welcome": "أهلًا"})
    cfg._data["token_file"] = str(tok)
    return cfg


def msg(uid, text, update_id=1):
    return {"update_id": update_id, "message": {
        "chat": {"id": uid}, "from": {"id": uid}, "text": text}}


def cb(uid, data, mid=55, text=""):
    return {"update_id": 99, "callback_query": {
        "id": "q1", "from": {"id": uid}, "data": data,
        "message": {"chat": {"id": uid}, "message_id": mid, "text": text}}}


def audit_rows():
    with store.conn() as c:
        return c.execute("SELECT action, target, ok FROM admin_audit ORDER BY id").fetchall()


def main():
    tmp = Path(tempfile.mkdtemp())
    store.DB = tmp / "subs.db"
    import telegram_bot.config as config_mod
    config_mod.CONFIG_FILE = tmp / "bot_config.json"
    cfg = make_cfg(tmp)
    api = FakeApi()
    now = datetime.now(timezone.utc)

    with store.conn() as c:
        c.execute("INSERT INTO subscribers(chat_id, name, status, activated_at, expires_at) "
                  "VALUES(?,?, 'active', ?, ?)", (222, "Ali", now.isoformat(),
                                                 (now + timedelta(days=10)).isoformat()))
        c.execute("INSERT INTO subscribers(chat_id, name, status, activated_at, expires_at) "
                  "VALUES(?,?, 'active', ?, ?)", (333, "Sara", now.isoformat(),
                                                 (now + timedelta(days=1)).isoformat()))
    jdb = tmp / "journal.db"
    jc = sqlite3.connect(jdb)
    jc.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, "
               "status TEXT, entry REAL, stop REAL, tp1 REAL, tp2 REAL)")
    jc.commit(); jc.close()
    commands.JOURNAL_DB = jdb

    # 1. غير الأدمن: /admin مرفوض + يُسجَّل
    commands.handle_update(api, cfg, msg(222, "/admin", 1))
    assert any("للأدمن فقط" in t for _, t, _ in api.sent), "non-admin not refused"
    assert ("unauthorized", "/admin", 0) in audit_rows(), "unauthorized not audited"
    commands.handle_update(api, cfg, msg(222, "/list", 2))
    assert ("unauthorized", "/list", 0) in audit_rows(), "unauthorized /list not audited"

    # 2. /admin يعرض اللوحة بأزرارها
    before = len(api.sent)
    commands.handle_update(api, cfg, msg(111, "/admin", 3))
    _, text, kb = api.sent[before]
    assert "لوحة تحكم" in text, "panel text missing"
    assert kb and any(d.get("callback_data") == "panel:subs"
                      for row in kb["inline_keyboard"] for d in row), "subs button missing"
    assert ("/admin", "", 1) in audit_rows(), "/admin not audited"

    # 3. زر المشتركين + تفاصيل مشترك + إجراءات من اللوحة
    commands.handle_update(api, cfg, cb(111, "panel:subs"))
    assert any("Ali" in t and "Sara" in t for _, t, _ in api.sent), "subs list missing"
    commands.handle_update(api, cfg, cb(111, "sub:333"))
    assert any("Sara" in t and "333" in t for _, t, _ in api.sent), "sub detail missing"
    commands.handle_update(api, cfg, cb(111, "subact:pause:333"))
    with store.conn() as c:
        assert c.execute("SELECT status FROM subscribers WHERE chat_id=333").fetchone()[0] == "paused"
    assert 333 in api.bans, "pause did not ban"
    assert any("paused" in t for _, t, _ in api.sent), "detail not refreshed after pause"
    commands.handle_update(api, cfg, cb(111, "subact:act30:222"))
    with store.conn() as c:
        exp = c.execute("SELECT expires_at FROM subscribers WHERE chat_id=222").fetchone()[0]
        assert exp > (now + timedelta(days=29)).isoformat(), "act30 did not extend"
    assert any(cid == 222 and "تم تفعيل اشتراكك" in t for cid, t, _ in api.sent), "activation DM missing"

    # 4. بانتظار المراجعة + اعتماد من اللوحة يحدّث اللوحة
    assert review.queue(api, cfg, 9, "🟢 شراء XAUUSD") == "pending"
    commands.handle_update(api, cfg, cb(111, "panel:pending"))
    assert any("#9" in t for _, t, _ in api.sent), "pending list missing #9"
    before = len(api.sent)
    commands.handle_update(api, cfg, cb(111, "approve:9", text="📥 بانتظار المراجعة:\n#9 منذ 05:00"))
    with store.conn() as c:
        assert c.execute("SELECT status FROM pending WHERE signal_id=9").fetchone()[0] == "published"
        assert c.execute("SELECT COUNT(*) FROM deliveries WHERE signal_id=9").fetchone()[0] == 1
    assert any("لا شيء" in t for _, t, _ in api.sent[before:]), "panel not refreshed after approve"

    # 5. الوضع: عرض + تبديل ذهابًا وإيابًا
    commands.handle_update(api, cfg, cb(111, "panel:mode"))
    assert any("الوضع الحالي: review" in t for _, t, _ in api.sent), "mode view missing"
    commands.handle_update(api, cfg, cb(111, "panel:mode_toggle"))
    assert cfg.mode == "auto", f"toggle failed, mode={cfg.mode}"
    commands.handle_update(api, cfg, cb(111, "panel:mode_toggle"))
    assert cfg.mode == "review", f"toggle back failed, mode={cfg.mode}"

    # 6. الإحصائيات + سجل العمليات
    commands.handle_update(api, cfg, cb(111, "panel:stats"))
    assert any("الإحصائيات" in t for _, t, _ in api.sent), "stats view missing"
    commands.handle_update(api, cfg, cb(111, "panel:audit"))
    assert any("آخر عمليات الأدمن" in t for _, t, _ in api.sent), "audit view missing"
    assert ("/admin", "", 1) in audit_rows(), "/admin row missing from audit log"
    before = len(api.sent)
    commands.handle_update(api, cfg, msg(111, "/audit", 4))
    assert any("آخر عمليات الأدمن" in t for _, t, _ in api.sent[before:]), "/audit missing"

    # 7. حد المعدل: 20 إجراء مسموح، الـ 21 يُحجب
    with store.conn() as c:
        c.execute("DELETE FROM admin_rate")
    before = len(api.sent)
    for i in range(21):
        commands.handle_update(api, cfg, msg(111, "/mode", 10 + i))
    mode_replies = [t for _, t, _ in api.sent[before:] if "الوضع:" in t]
    assert len(mode_replies) == 20, f"expected 20 mode replies, got {len(mode_replies)}"
    assert any("تمهل" in t for _, t, _ in api.sent[before:]), "rate limit message missing"
    assert ("rate_limit", "/mode", 0) in audit_rows(), "rate limit not audited"

    # 8. إصلاح review.queue مع صورة: رسالة المراجعة تصل كصورة
    from telegram_bot.charts import render_signal_chart
    import pandas as pd
    from types import SimpleNamespace
    rng = pd.date_range("2026-10-01", periods=100, freq="h", tz="UTC")
    base = 4000 + (pd.Series(range(100)) * 0.3)
    fake_df = pd.DataFrame({"open": base, "high": base + 2, "low": base - 2,
                            "close": base + 1}, index=rng)
    fake_card = SimpleNamespace(symbol="XAUUSD", direction="شراء", entry=4030.0,
                                stop=4020.0, tp1=4045.0, tp2=4060.0, confidence=78)
    chart_path = render_signal_chart(fake_df, fake_card, tmp / "chart9.png")
    before = len(api.sent)
    assert review.queue(api, cfg, 7, "🟢 شراء XAUUSD", chart_path) == "pending"
    assert any("[photo]" in t and "بانتظار المراجعة" in t
               for _, t, _ in api.sent[before:]), "chart review DM not sent as photo"

    print("ALL PANEL TESTS PASSED")


if __name__ == "__main__":
    main()
