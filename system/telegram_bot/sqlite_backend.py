"""SQLite backend — the original on-disk implementation of the backend
interface (see `backend.py`). Used when `GC_STORE` is not `supabase`
(local runs, VM, tests). Behaviour is unchanged from the pre-Actions code,
except `log_signal` carries the dedup guard backported from the approved
Narmer fix (2026-11-14).

All functions return the same shapes as `sb_store` (dicts; timestamps as
ISO strings; direction as stored, i.e. Arabic here).
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import journal  # noqa: E402
from . import store  # noqa: E402

DIR = Path(__file__).parent
OFFSET_FILE = DIR / ".offset"
SUBS_DB = DIR / "subs.db"
DRY_RUN = os.environ.get("GC_DRY_RUN", "0") == "1"


def _signal_dict(row):
    if not row:
        return None
    d = dict(row)
    d["created_at"] = d.get("ts")
    d["stop_loss"] = d.get("stop")
    d.setdefault("card_text", None)
    d.setdefault("chart_path", None)
    d.setdefault("channel_message_id", None)
    d.setdefault("published_at", None)
    d.setdefault("review_status", None)
    return d


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- signals

def log_signal(card, votes: dict, e1=None, m3=None, r0=None, chart_path=None,
               mode: str = "paper") -> int:
    """Thin wrapper over journal.log_signal (cap + dedup live there).
    e1/m3/r0/chart_path are accepted for interface parity and ignored —
    SQLite has no evaluations/corrections tables."""
    if DRY_RUN:
        day = _today_utc()
        with journal._conn() as c:
            n = c.execute("SELECT n FROM daily_count WHERE day=?", (day,)).fetchone()
            if n and n[0] >= 3:
                return -1
        print("sb_store: DRY RUN — signal NOT written "
              f"({card.symbol} {card.direction} @{card.entry})")
        return 1
    return journal.log_signal(card, votes, mode=mode)


def list_open_signals() -> list:
    with journal._conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM signals WHERE status='open' "
                         "ORDER BY ts").fetchall()
    return [_signal_dict(r) for r in rows]


def get_signal(signal_id: int):
    with journal._conn() as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
    return _signal_dict(row)


def close_signal(signal_id: int, status: str, exit_price, pnl_r) -> bool:
    if DRY_RUN:
        print(f"sb_store: DRY RUN — close #{signal_id} -> {status} NOT written")
        return True
    with journal._conn() as c:
        cur = c.execute(
            "UPDATE signals SET status=?, exit_price=?, pnl_r=? WHERE id=?",
            (status, exit_price, pnl_r, signal_id))
        return cur.rowcount > 0


def stats() -> dict:
    return journal.stats()


def journal_stats_by_direction() -> dict:
    with journal._conn() as c:
        rows = c.execute(
            "SELECT direction, status, COUNT(*) FROM signals "
            "WHERE status != 'open' GROUP BY direction, status").fetchall()
    agg = {}
    for direction, status, n in rows:
        d = agg.setdefault(direction, {"wins": 0, "losses": 0})
        if status in ("tp1", "tp2"):
            d["wins"] += n
        elif status == "sl":
            d["losses"] += n
    out = {}
    for direction, d in agg.items():
        total = d["wins"] + d["losses"]
        out[direction] = {
            "trades": total,
            "wins": d["wins"],
            "win_rate": round(100 * d["wins"] / total, 1) if total else 0,
        }
    return out


# ---------------------------------------------------------------- review queue (pending table)

def queue_pending(signal_id: int, card_text: str, chart_path=None) -> str:
    if DRY_RUN:
        print(f"sb_store: DRY RUN — queue #{signal_id} NOT written")
        return "pending"
    from datetime import datetime, timezone as _tz
    with store.conn() as c:
        c.execute("INSERT OR REPLACE INTO pending(signal_id, card_text, chart_path, status, created_at) "
                  "VALUES(?,?,?, 'pending', ?)",
                  (signal_id, card_text, str(chart_path) if chart_path else None,
                   datetime.now(_tz.utc).isoformat()))
    return "pending"


def get_pending(signal_id: int):
    with store.conn() as c:
        row = c.execute("SELECT status, card_text, chart_path FROM pending "
                        "WHERE signal_id=?", (signal_id,)).fetchone()
    if not row:
        return None
    return {"status": row[0], "card_text": row[1], "chart_path": row[2]}


def list_pending() -> list:
    with store.conn() as c:
        rows = c.execute("SELECT signal_id, created_at FROM pending "
                         "WHERE status='pending' ORDER BY created_at").fetchall()
    return [{"signal_id": i, "created_at": t} for i, t in rows]


def count_pending() -> int:
    with store.conn() as c:
        row = c.execute("SELECT COUNT(*) FROM pending WHERE status='pending'").fetchone()
    return row[0]


def set_review_status(signal_id: int, status: str, reviewed_by=None) -> bool:
    if DRY_RUN:
        print(f"sb_store: DRY RUN — review #{signal_id} -> {status} NOT written")
        return True
    from datetime import datetime, timezone as _tz
    with store.conn() as c:
        cur = c.execute("UPDATE pending SET status=?, reviewed_at=? WHERE signal_id=?",
                        (status, datetime.now(_tz.utc).isoformat(), signal_id))
        return cur.rowcount > 0


def publish_signal(signal_id: int, channel_message_id: int) -> bool:
    if DRY_RUN:
        print(f"sb_store: DRY RUN — publish #{signal_id} NOT written")
        return True
    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc).isoformat()
    with store.conn() as c:
        row = c.execute("SELECT 1 FROM pending WHERE signal_id=?",
                        (signal_id,)).fetchone()
        if not row:
            return False
        c.execute("INSERT OR REPLACE INTO deliveries(signal_id, channel_message_id, published_at) "
                  "VALUES(?,?,?)", (signal_id, channel_message_id, now))
        c.execute("UPDATE pending SET status='published', reviewed_at=? "
                  "WHERE signal_id=?", (now, signal_id))
        for (chat_id, _u, _n, _e) in store.active_subscribers(c):
            c.execute("INSERT OR IGNORE INTO subscriber_signals"
                      "(subscriber_chat_id, signal_id) VALUES(?,?)",
                      (chat_id, signal_id))
    return True


# ---------------------------------------------------------------- subscribers

def get_subscriber(chat_id: int):
    with store.conn() as c:
        row = c.execute(
            "SELECT chat_id, username, name, status, activated_at, expires_at, "
            "invite_link, warned FROM subscribers WHERE chat_id=?",
            (chat_id,)).fetchone()
    if not row:
        return None
    keys = ("chat_id", "username", "name", "status", "activated_at",
            "expires_at", "invite_link", "warned")
    return dict(zip(keys, row))


def upsert_subscriber(chat_id: int, name: str, expires_at: str, invite_link):
    if DRY_RUN:
        print(f"sb_store: DRY RUN — activate {chat_id} NOT written")
        return
    from datetime import datetime, timezone as _tz
    with store.conn() as c:
        c.execute("INSERT INTO subscribers(chat_id, name, status, activated_at, expires_at, invite_link, warned) "
                  "VALUES(?,?, 'active', ?, ?, ?, 0) "
                  "ON CONFLICT(chat_id) DO UPDATE SET status='active', expires_at=excluded.expires_at, "
                  "invite_link=excluded.invite_link, warned=0",
                  (chat_id, name, datetime.now(_tz.utc).isoformat(), expires_at, invite_link))


def set_subscriber_status(chat_id: int, status: str):
    if DRY_RUN:
        print(f"sb_store: DRY RUN — subscriber {chat_id} -> {status} NOT written")
        return
    with store.conn() as c:
        c.execute("UPDATE subscribers SET status=? WHERE chat_id=?", (status, chat_id))


def get_subscriber_invite(chat_id: int):
    with store.conn() as c:
        row = c.execute("SELECT invite_link FROM subscribers WHERE chat_id=?",
                        (chat_id,)).fetchone()
    return row[0] if row else None


def list_subscribers(limit: int = 0) -> list:
    sql = ("SELECT chat_id, name, status, expires_at FROM subscribers "
           "ORDER BY status, expires_at")
    with store.conn() as c:
        rows = c.execute(sql + (" LIMIT ?" if limit else ""),
                         (limit,) if limit else ()).fetchall()
    return [{"chat_id": i, "name": n, "status": s, "expires_at": e}
            for i, n, s, e in rows]


def list_active_subscribers() -> list:
    with store.conn() as c:
        rows = store.active_subscribers(c)
    return [{"chat_id": i, "username": u, "name": n, "expires_at": e}
            for i, u, n, e in rows]


def list_active_for_sweep() -> list:
    with store.conn() as c:
        rows = c.execute("SELECT chat_id, expires_at, invite_link, warned "
                         "FROM subscribers WHERE status='active'").fetchall()
    return [{"chat_id": i, "expires_at": e, "invite_link": l, "warned": w}
            for i, e, l, w in rows]


def set_warned(chat_id: int):
    if DRY_RUN:
        return
    with store.conn() as c:
        c.execute("UPDATE subscribers SET warned=1 WHERE chat_id=?", (chat_id,))


# ---------------------------------------------------------------- subscriber_signals / deliveries

def _attach_journal(c):
    c.execute(f"ATTACH DATABASE '{journal.DB}' AS j")
    return c


def user_signal_stats(chat_id: int) -> list:
    with store.conn() as c:
        _attach_journal(c)
        rows = c.execute(
            "SELECT j.status, COUNT(*) FROM subscriber_signals ss "
            "JOIN j.signals j ON j.id = ss.signal_id "
            "WHERE ss.subscriber_chat_id=? GROUP BY j.status",
            (chat_id,)).fetchall()
    return [{"status": s, "n": n} for s, n in rows]


def recent_published(limit: int = 10) -> list:
    with store.conn() as c:
        _attach_journal(c)
        rows = c.execute(
            "SELECT j.id, j.symbol, j.direction, j.status FROM deliveries d "
            "JOIN j.signals j ON j.id = d.signal_id "
            "ORDER BY d.published_at DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": i, "symbol": s, "direction": d, "status": st}
            for i, s, d, st in rows]


def has_subscriber_signal(chat_id: int, signal_id: int) -> bool:
    with store.conn() as c:
        row = c.execute("SELECT 1 FROM subscriber_signals "
                        "WHERE subscriber_chat_id=? AND signal_id=?",
                        (chat_id, signal_id)).fetchone()
    return row is not None


def mark_entered(chat_id: int, signal_id: int):
    if DRY_RUN:
        return
    with store.conn() as c:
        c.execute("UPDATE subscriber_signals SET entered_self=1 "
                  "WHERE subscriber_chat_id=? AND signal_id=?",
                  (chat_id, signal_id))


def get_delivery(signal_id: int):
    with store.conn() as c:
        row = c.execute("SELECT channel_message_id, published_at FROM deliveries "
                        "WHERE signal_id=?", (signal_id,)).fetchone()
    if not row:
        return None
    return {"channel_message_id": row[0], "published_at": row[1]}


def published_today() -> int:
    day = _today_utc()
    with store.conn() as c:
        row = c.execute("SELECT COUNT(*) FROM deliveries WHERE substr(published_at,1,10)=?",
                        (day,)).fetchone()
    return row[0] if row else 0


def panel_stats() -> dict:
    with store.conn() as c:
        subs = c.execute("SELECT status, COUNT(*) FROM subscribers GROUP BY status").fetchall()
        pend = c.execute("SELECT COUNT(*) FROM pending WHERE status='pending'").fetchone()[0]
        try:
            _attach_journal(c)
            rows = c.execute("SELECT j.status, COUNT(*) FROM deliveries d "
                             "JOIN j.signals j ON j.id = d.signal_id GROUP BY j.status").fetchall()
        except Exception:
            rows = []
    wins = sum(n for s, n in rows if s in ("tp1", "tp2"))
    losses = sum(n for s, n in rows if s == "sl")
    return {"subs": [(s, n) for s, n in subs], "pending": pend,
            "wins": wins, "losses": losses, "total": wins + losses}


# ---------------------------------------------------------------- processed_updates / offset

def is_processed(update_id: int) -> bool:
    with store.conn() as c:
        return store.is_processed(c, update_id)


def mark_processed(update_id: int):
    if DRY_RUN:
        return
    from datetime import datetime, timezone as _tz
    with store.conn() as c:
        store.mark_processed(c, update_id, datetime.now(_tz.utc).isoformat())


def get_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text()) if OFFSET_FILE.exists() else 0
    except (ValueError, OSError):
        return 0


def set_offset(value: int):
    if DRY_RUN:
        return
    OFFSET_FILE.write_text(str(int(value)))


# ---------------------------------------------------------------- audit / rate limit / bot_state

def audit(admin_id: int, action: str, target="", detail="", ok=1):
    if DRY_RUN:
        return
    try:
        from datetime import datetime, timezone as _tz
        with store.conn() as c:
            c.execute("INSERT INTO admin_audit(ts, admin_chat_id, action, target, detail, ok) "
                      "VALUES(?,?,?,?,?,?)",
                      (datetime.now(_tz.utc).isoformat(), admin_id, action,
                       str(target), detail, int(ok)))
    except Exception:
        pass


def recent_audit(limit: int = 10) -> list:
    with store.conn() as c:
        rows = c.execute("SELECT ts, action, target, ok FROM admin_audit "
                         "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"ts": t, "action": a, "target": tg, "ok": ok} for t, a, tg, ok in rows]


def rate_check_and_record(admin_id: int) -> bool:
    """20 admin actions/minute. Returns False when the limit is hit."""
    if DRY_RUN:
        return True
    try:
        from datetime import datetime, timedelta, timezone as _tz
        now = datetime.now(_tz.utc)
        with store.conn() as c:
            cutoff = (now - timedelta(seconds=60)).isoformat()
            c.execute("DELETE FROM admin_rate WHERE ts < ?", (cutoff,))
            n = c.execute("SELECT COUNT(*) FROM admin_rate WHERE admin_chat_id=?",
                          (admin_id,)).fetchone()[0]
            if n >= 20:
                return False
            c.execute("INSERT INTO admin_rate(admin_chat_id, ts) VALUES(?, ?)",
                      (admin_id, now.isoformat()))
            return True
    except Exception:
        return True  # never lock the admin out because the limiter broke


def get_bot_state(key: str, default=None):
    """SQLite has no bot_state table: mode/reviewed_count live in
    bot_config.json (managed by Config) and the offset in the .offset file.
    Returns the default so callers fall back gracefully."""
    return default


def set_bot_state(key: str, value: str):
    """No-op on SQLite (see get_bot_state). Only the Supabase backend
    persists bot_state."""
    return None
