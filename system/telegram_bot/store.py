"""سجل المشتركين والتوصيات — SQLite منفصل عن journal.db.

- subscribers: كل مشترك + حالته + انتهاؤه + رابط دعوته
- deliveries: رسالة القناة لكل توصية منشورة
- subscriber_signals: سجل كل مشترك = التوصيات المنشورة أثناء اشتراكه النشط
- pending: طابور المراجعة (مرجع لـ journal.signals.id)
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "subs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    status TEXT DEFAULT 'active',   -- active / paused / expired / kicked
    activated_at TEXT,
    expires_at TEXT,
    invite_link TEXT,
    warned INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS deliveries (
    signal_id INTEGER PRIMARY KEY,
    channel_message_id INTEGER,
    published_at TEXT
);
CREATE TABLE IF NOT EXISTS subscriber_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_chat_id INTEGER NOT NULL,
    signal_id INTEGER NOT NULL,
    entered_self INTEGER DEFAULT 0,
    UNIQUE(subscriber_chat_id, signal_id)
);
CREATE TABLE IF NOT EXISTS pending (
    signal_id INTEGER PRIMARY KEY,
    card_text TEXT NOT NULL,
    chart_path TEXT,
    status TEXT DEFAULT 'pending',  -- pending / approved / rejected / published
    created_at TEXT,
    reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_chat_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    currency TEXT DEFAULT 'USD',
    method TEXT,                     -- تحويل بنكي / فودافون كاش / USDT / غيره
    period_days INTEGER,
    paid_at TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS admin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    admin_chat_id INTEGER NOT NULL,
    action TEXT NOT NULL,            -- /activate, callback:approve:5, rate_limit, unauthorized...
    target TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    ok INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS admin_rate (
    admin_chat_id INTEGER NOT NULL,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    ts TEXT NOT NULL,
    ok INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS processed_updates (
    update_id INTEGER PRIMARY KEY,
    processed_at TEXT NOT NULL
);
"""


def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


def is_processed(c, update_id: int) -> bool:
    """هل سبق معالجة هذا الـ update_id؟ (حماية منع التكرار)."""
    row = c.execute("SELECT 1 FROM processed_updates WHERE update_id=?",
                    (update_id,)).fetchone()
    return row is not None


def mark_processed(c, update_id: int, processed_at: str) -> None:
    """سجّل update_id كمعالَج، مع تقليم القديم (نحتفظ بآخر 2000 فقط)."""
    c.execute("INSERT OR IGNORE INTO processed_updates(update_id, processed_at) "
              "VALUES(?, ?)", (update_id, processed_at))
    c.execute("DELETE FROM processed_updates WHERE update_id <= "
              "(SELECT MAX(update_id) - 2000 FROM processed_updates)")


def active_subscribers(c) -> list:
    """المشتركون النشطون غير المنتهين (الانتهاء يُحسم في sweep)."""
    return c.execute(
        "SELECT chat_id, username, name, expires_at FROM subscribers "
        "WHERE status='active'").fetchall()
