"""سجل الصفقات — SQLite (مقاوم للمسح، يعيش في workspace)."""
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "data" / "journal.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry REAL NOT NULL,
    stop REAL NOT NULL,
    tp1 REAL NOT NULL,
    tp2 REAL NOT NULL,
    confidence INTEGER,
    votes_json TEXT,
    status TEXT DEFAULT 'open',       -- open / tp1 / tp2 / sl / expired
    exit_price REAL,
    pnl_r REAL,                        -- الربح/الخسارة بوحدة المخاطرة R
    mode TEXT DEFAULT 'paper'          -- paper / live (النزاهة: يُوسم دائمًا)
);
CREATE TABLE IF NOT EXISTS daily_count (
    day TEXT PRIMARY KEY,
    n INTEGER DEFAULT 0
);
"""


def _conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


def log_signal(card, votes: dict, mode: str = "paper") -> int:
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _conn() as c:
        n = c.execute("SELECT n FROM daily_count WHERE day=?", (day,)).fetchone()
        n = (n[0] if n else 0)
        if n >= 3:  # سقف التوصيات اليومي — لا تُخترع توصيات
            return -1
        c.execute("INSERT OR REPLACE INTO daily_count(day,n) VALUES(?,?)", (day, n + 1))
        cur = c.execute(
            """INSERT INTO signals(ts,symbol,direction,entry,stop,tp1,tp2,
                                   confidence,votes_json,mode)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now(timezone.utc).isoformat(), card.symbol, card.direction,
             card.entry, card.stop, card.tp1, card.tp2, card.confidence,
             json.dumps(votes, ensure_ascii=False), mode))
        return cur.lastrowid


def stats() -> dict:
    with _conn() as c:
        rows = c.execute(
            "SELECT status, COUNT(*), COALESCE(AVG(pnl_r),0) FROM signals "
            "WHERE status != 'open' GROUP BY status").fetchall()
    wins = sum(n for s, n, _ in rows if s in ("tp1", "tp2"))
    losses = sum(n for s, n, _ in rows if s == "sl")
    total = wins + losses
    avg_r = sum(n * a for _, n, a in rows) / total if total else 0
    return {"closed": total, "wins": wins, "losses": losses,
            "win_rate": round(100 * wins / total, 1) if total else 0,
            "avg_r": round(avg_r, 2)}
