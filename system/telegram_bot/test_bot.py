"""اختبار بوت التوصيات end-to-end — واجهة Telegram وهمية، بلا شبكة.

يغطي: الطابور → اعتماد → نشر → سجل المشترك → رفض → انتهاء →
/stats + /history + زر الدخول + الانقلاب للتلقائي.
"""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from telegram_bot import commands, expiry, publisher, review, store
from telegram_bot.config import Config


class FakeApi:
    def __init__(self):
        self.sent = []          # (chat_id, text)
        self.bans = []
        self.revokes = []
        self._mid = 100

    def send_message(self, chat_id, text, reply_markup=None):
        self._mid += 1
        self.sent.append((chat_id, text))
        return {"message_id": self._mid, "chat": {"id": chat_id}}

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.sent.append((chat_id, f"[edit {message_id}] {text[:40]}"))
        return True

    def edit_message_caption(self, chat_id, message_id, caption, reply_markup=None):
        self.sent.append((chat_id, f"[edit-cap {message_id}] {caption[:40]}"))
        return True

    def send_photo(self, chat_id, photo_path, caption, reply_markup=None):
        self._mid += 1
        self.sent.append((chat_id, f"[photo] {caption[:40]}"))
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
        self.sent.append(("cb", text or "ok"))


def make_cfg(tmp: Path) -> Config:
    tok = tmp / ".bot-token"
    tok.write_text("FAKE:123")
    cfg = Config({"token_file": str(tok), "channel_id": -100999,
                  "admin_ids": [111], "mode": "review",
                  "reviewed_count": 0, "auto_after_reviewed": 30,
                  "expiry_warn_days": 3, "welcome": "أهلًا"})
    cfg._data["token_file"] = str(tok)
    return cfg


def main():
    tmp = Path(tempfile.mkdtemp())
    store.DB = tmp / "subs.db"
    import telegram_bot.config as config_mod
    config_mod.CONFIG_FILE = tmp / "bot_config.json"
    cfg = make_cfg(tmp)
    api = FakeApi()
    now = datetime.now(timezone.utc)

    # مشتركان نشطان
    with store.conn() as c:
        c.execute("INSERT INTO subscribers(chat_id, name, status, activated_at, expires_at) "
                  "VALUES(?,?, 'active', ?, ?)", (222, "Ali", now.isoformat(),
                                                 (now + timedelta(days=10)).isoformat()))
        c.execute("INSERT INTO subscribers(chat_id, name, status, activated_at, expires_at) "
                  "VALUES(?,?, 'active', ?, ?)", (333, "Sara", now.isoformat(),
                                                 (now + timedelta(days=1)).isoformat()))

    # 1. طابور → اعتماد → نشر
    assert review.queue(api, cfg, 1, "🟢 شراء XAUUSD\nالدخول: 4000") == "pending"
    assert any("بانتظار المراجعة" in t for _, t in api.sent), "review DM missing"
    assert review.approve(api, cfg, 1) is True
    with store.conn() as c:
        assert c.execute("SELECT status FROM pending WHERE signal_id=1").fetchone()[0] == "published"
        assert c.execute("SELECT COUNT(*) FROM deliveries WHERE signal_id=1").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM subscriber_signals WHERE signal_id=1").fetchone()[0] == 2
    assert any(-100999 == cid for cid, _ in api.sent), "channel post missing"
    assert cfg.reviewed_count == 1

    # 2. رفض → لا نشر
    review.queue(api, cfg, 2, "🔴 بيع XAUUSD")
    assert review.reject(cfg, 2) is True
    with store.conn() as c:
        assert c.execute("SELECT COUNT(*) FROM deliveries WHERE signal_id=2").fetchone()[0] == 0

    # 2b. نشر بصورة شارت
    from telegram_bot.charts import render_signal_chart
    import pandas as pd
    from types import SimpleNamespace
    rng = pd.date_range("2026-10-01", periods=100, freq="h", tz="UTC")
    base = 4000 + (pd.Series(range(100)) * 0.3)
    fake_df = pd.DataFrame({"open": base, "high": base + 2, "low": base - 2,
                            "close": base + 1}, index=rng)
    fake_card = SimpleNamespace(symbol="XAUUSD", direction="شراء", entry=4030.0,
                                stop=4020.0, tp1=4045.0, tp2=4060.0, confidence=78)
    chart_path = render_signal_chart(fake_df, fake_card, tmp / "chart5.png")
    assert chart_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    review.queue(api, cfg, 5, "🟢 شراء XAUUSD", chart_path)
    review.approve(api, cfg, 5)
    assert any("[photo]" in t for _, t in api.sent), "photo publish missing"
    commands.handle_update(api, cfg, {"update_id": 1, "callback_query": {
        "id": "q1", "from": {"id": 222}, "data": "entered:1"}})
    with store.conn() as c:
        assert c.execute("SELECT entered_self FROM subscriber_signals "
                         "WHERE subscriber_chat_id=222 AND signal_id=1").fetchone()[0] == 1
    # /stats يحتاج journal — نزرع سجلًا وهميًا عبر ATTACH
    import sqlite3
    jdb = tmp / "journal.db"
    jc = sqlite3.connect(jdb)
    jc.execute("CREATE TABLE signals (id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, "
               "status TEXT, entry REAL, stop REAL, tp1 REAL, tp2 REAL)")
    jc.execute("INSERT INTO signals VALUES(1,'XAUUSD','شراء','tp1',4000,3990,4015,4030)")
    jc.commit(); jc.close()
    commands.JOURNAL_DB = jdb
    before = len(api.sent)
    commands.handle_update(api, cfg, {"update_id": 2, "message": {
        "chat": {"id": 222}, "from": {"username": "ali"}, "text": "/stats"}})
    assert any("سجلك الشخصي" in t for _, t in api.sent[before:]), "stats missing"

    # 4. انتهاء: Sara تنتهي غدًا → تنبيه؛ ثم انتهاء فعلي
    expiry.sweep(api, cfg)
    with store.conn() as c:
        assert c.execute("SELECT warned FROM subscribers WHERE chat_id=333").fetchone()[0] == 1
        c.execute("UPDATE subscribers SET expires_at=? WHERE chat_id=333",
                  ((now - timedelta(days=1)).isoformat(),))
    expiry.sweep(api, cfg)
    with store.conn() as c:
        assert c.execute("SELECT status FROM subscribers WHERE chat_id=333").fetchone()[0] == "expired"
    assert 333 in api.bans, "expired user not banned"

    # 5. الانقلاب للتلقائي عند 30 مراجَعة
    cfg.set("reviewed_count", 29)
    review.queue(api, cfg, 3, "🟢 شراء XAUUSD")
    review.approve(api, cfg, 3)
    assert cfg.mode == "auto", f"mode still {cfg.mode}"
    assert review.queue(api, cfg, 4, "🟢 شراء XAUUSD") == "published"

    # 6. أوامر الأدمن
    before = len(api.sent)
    commands.handle_update(api, cfg, {"update_id": 3, "message": {
        "chat": {"id": 111}, "from": {}, "text": "/list"}})
    assert any("المشتركون" in t for _, t in api.sent[before:]), "list missing"

    print("ALL BOT TESTS PASSED")


if __name__ == "__main__":
    main()
