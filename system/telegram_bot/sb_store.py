"""Supabase store for the Gold Council bot runtime (GitHub Actions hosting).

Same backend interface as `sqlite_backend` (see `backend.py`); active only
when `GC_STORE=supabase`. All state lives in the Gold Council Supabase
project — the runner itself is stateless.

Connection: direct psycopg to Postgres as the table owner (bypasses RLS).
Credentials come from env vars only; the DSN is NEVER logged or printed.
Dry run (`GC_DRY_RUN=1`): reads stay live, all writes become no-ops that
log what they *would* do — used for the first Actions test.

Rules enforced here (same as the approved Narmer behaviour):
- 3 signals/day CAP (per UTC day), never a quota.
- Dedup: same (symbol, direction, entry, stop, tp1, tp2) with an open signal
  OR a pending review row is NOT logged again (returns -2).
- Settle: TP2 is checked before TP1; a time-only expiry close has NO exit
  price / pnl (never invented) and writes NO settlements row.
- Direction is stored `long`/`short` (SQLite held Arabic `شراء`/`بيع`).
"""
import os
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

DRY_RUN = os.environ.get("GC_DRY_RUN", "0") == "1"

DIR_EN = {"شراء": "long", "بيع": "short"}
DIR_AR = {"long": "شراء", "short": "بيع"}

AGENTS_35 = {
    "R0", "N0", "R1", "R2",
    "C1", "C2", "C3", "C4", "C5", "C6", "C7",
    "S1", "S2", "S3a", "S3b", "S4a", "S4b", "S4c", "S5a", "S5b", "S5c",
    "S6", "S10", "S11", "S12", "S13",
    "X1", "X2", "X3",
    "M1", "M2", "M3", "E1", "E2", "J1",
}

DAILY_CAP = 3
RATE_WINDOW_SECONDS = 60
RATE_MAX_ACTIONS = 20


def _layer_of(agent: str) -> str:
    if agent in ("R0", "N0", "R1", "R2"):
        return "L0-router"
    if agent.startswith("C"):
        return "L1-context"
    if agent.startswith(("S", "X")) and agent not in ("X1", "X2", "X3"):
        return "L2-structure"
    if agent in ("X1", "X2", "X3"):
        return "L3-execution"
    return "L4-judgement"


def _conn():
    host = os.environ.get("SUPABASE_DB_HOST", "")
    password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not host or not password:
        raise RuntimeError("sb_store: SUPABASE_DB_HOST / SUPABASE_DB_PASSWORD are required")
    return psycopg.connect(
        host=host,
        port=int(os.environ.get("SUPABASE_DB_PORT", "5432")),
        dbname=os.environ.get("SUPABASE_DB_NAME", "postgres"),
        user=os.environ.get("SUPABASE_DB_USER", "postgres"),
        password=password,
        connect_timeout=20,
        row_factory=dict_row,
    )


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _iso(value):
    """Timestamps cross the backend boundary as ISO strings (the SQLite
    path stores ISO text; call sites slice strings, e.g. t[11:16])."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _num(value):
    """numeric() columns come back as Decimal — the bot math needs floats."""
    return None if value is None else float(value)


def _signal_dict(row):
    if not row:
        return None
    row = dict(row)
    for k in ("entry", "stop_loss", "tp1", "tp2", "exit_price", "pnl_r", "atr"):
        if k in row:
            row[k] = _num(row[k])
    for k in ("created_at", "updated_at", "reviewed_at", "published_at"):
        if k in row:
            row[k] = _iso(row[k])
    # Call sites written against the SQLite journal use `ts` and `stop`.
    if "created_at" in row:
        row["ts"] = row["created_at"]
    if "stop_loss" in row:
        row["stop"] = row["stop_loss"]
    return row


# ---------------------------------------------------------------- signals

def log_signal(card, votes: dict, e1=None, m3=None, r0=None, chart_path=None,
               mode: str = "paper") -> int:
    """Log a new signal. Returns the new id, -1 at the daily cap, -2 for a
    duplicate setup. `votes` is the M1 verdict dict keyed by agent name."""
    direction = DIR_EN.get(card.direction, card.direction)
    if direction not in ("long", "short"):
        print(f"sb_store: unknown direction {card.direction!r}, refusing")
        return -2
    day = _today_utc()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM signals WHERE day_utc = %s", (day,))
            n = cur.fetchone()["n"]
            if n >= DAILY_CAP:
                return -1
            cur.execute(
                """SELECT id FROM signals
                   WHERE symbol=%s AND direction=%s AND entry=%s AND stop_loss=%s
                     AND tp1=%s AND tp2=%s
                     AND (status='open' OR review_status='pending') LIMIT 1""",
                (card.symbol, direction, card.entry, card.stop,
                 card.tp1, card.tp2))
            if cur.fetchone():
                return -2
            if DRY_RUN:
                # Cap/dedup were evaluated read-only above; only the write is skipped.
                print("sb_store: DRY RUN — signal NOT written "
                      f"({card.symbol} {direction} @{card.entry})")
                return 1
            regime = (r0 or {}).get("regime")
            if regime not in ("trend", "range", "shock"):
                regime = None
            atr = (r0 or {}).get("atr")
            cur.execute(
                """INSERT INTO signals(symbol, direction, entry, stop_loss, tp1, tp2,
                                      confidence, e1_score, mode, day_utc, daily_seq,
                                      card_text, chart_path, review_status, regime, atr)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s)
                   RETURNING id""",
                (card.symbol, direction, card.entry, card.stop, card.tp1, card.tp2,
                 card.confidence, (e1 or {}).get("score"), mode, day, n + 1,
                 card.text(), str(chart_path) if chart_path else None, regime,
                 float(atr) if atr is not None else None))
            sid = cur.fetchone()["id"]
            skipped = 0
            for agent, v in (votes or {}).items():
                if agent not in AGENTS_35:
                    skipped += 1
                    continue
                degraded = bool(v.get("degraded")) or ("skipped" in v)
                if "skipped" in v:
                    reason = f"skipped by {v['skipped']}"
                elif degraded:
                    reason = v.get("detail") or None
                else:
                    reason = None
                cur.execute(
                    """INSERT INTO agent_votes(signal_id, agent, layer, vote,
                                              confidence, detail, weight,
                                              degraded, degrade_reason)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (sid, agent, _layer_of(agent), v["signal"], v["confidence"],
                     v.get("detail") or "", float(v.get("weight_applied") or 0),
                     degraded, reason))
            if skipped:
                print(f"sb_store: skipped {skipped} unknown agent vote(s) for #{sid}")
            if e1 and e1.get("score") is not None:
                cur.execute(
                    """INSERT INTO evaluations(signal_id, evaluator, score, passed, reasons)
                       VALUES(%s,'E1',%s,%s,%s)""",
                    (sid, e1["score"], e1["score"] >= 70,
                     "; ".join(e1.get("checks") or [])))
            if m3 and m3.get("attacks") is not None:
                cur.execute(
                    """INSERT INTO corrections(signal_id, proposed_direction, attacks,
                                              veto, attack_text)
                       VALUES(%s,NULL,%s,%s,%s)""",
                    (sid, len(m3["attacks"]), bool(m3.get("veto")),
                     "; ".join(m3["attacks"])))
    return sid


def list_open_signals() -> list:
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, created_at, symbol, direction, entry, stop_loss, tp1, tp2,
                      status, card_text, chart_path, channel_message_id,
                      published_at, review_status
               FROM signals WHERE status='open' ORDER BY created_at""").fetchall()
    return [_signal_dict(r) for r in rows]


def get_signal(signal_id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE id=%s", (signal_id,)).fetchone()
    return _signal_dict(row)


def close_signal(signal_id: int, status: str, exit_price, pnl_r) -> bool:
    """Close a signal. When exit_price is None (time-only expiry) no
    settlements row is written — the price is never invented."""
    if DRY_RUN:
        print(f"sb_store: DRY RUN — close #{signal_id} -> {status} NOT written")
        return True
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE signals SET status=%s, exit_price=%s, pnl_r=%s WHERE id=%s",
                (status, exit_price, pnl_r, signal_id))
            if cur.rowcount == 0:
                return False
            if exit_price is not None:
                cur.execute(
                    """INSERT INTO settlements(signal_id, outcome, exit_price, pnl_r, settler)
                       VALUES(%s,%s,%s,%s,'settle.py')
                       ON CONFLICT (signal_id) DO NOTHING""",
                    (signal_id, status, exit_price, pnl_r))
    return True


def stats() -> dict:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n, COALESCE(AVG(pnl_r),0) AS a FROM signals "
            "WHERE status != 'open' GROUP BY status").fetchall()
    wins = sum(r["n"] for r in rows if r["status"] in ("tp1", "tp2"))
    losses = sum(r["n"] for r in rows if r["status"] == "sl")
    total = wins + losses
    avg_r = sum(r["n"] * float(r["a"]) for r in rows) / total if total else 0
    return {"closed": total, "wins": wins, "losses": losses,
            "win_rate": round(100 * wins / total, 1) if total else 0,
            "avg_r": round(avg_r, 2)}


def journal_stats_by_direction() -> dict:
    """{direction: {trades, win_rate}} over closed signals — for J1."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT direction, status, COUNT(*) AS n FROM signals "
            "WHERE status != 'open' GROUP BY direction, status").fetchall()
    agg = {}
    for r in rows:
        d = agg.setdefault(r["direction"], {"wins": 0, "losses": 0})
        if r["status"] in ("tp1", "tp2"):
            d["wins"] += r["n"]
        elif r["status"] == "sl":
            d["losses"] += r["n"]
    stats, out = {}, {}
    for direction, d in agg.items():
        total = d["wins"] + d["losses"]
        out[direction] = {
            "trades": total,
            "wins": d["wins"],
            "win_rate": round(100 * d["wins"] / total, 1) if total else 0,
        }
    return out


# ---------------------------------------------------------------- review queue (signals columns)

def queue_pending(signal_id: int, card_text: str, chart_path=None) -> str:
    if DRY_RUN:
        print(f"sb_store: DRY RUN — queue #{signal_id} NOT written")
        return "pending"
    with _conn() as conn:
        conn.execute(
            "UPDATE signals SET card_text=%s, chart_path=%s, review_status='pending' "
            "WHERE id=%s",
            (card_text, str(chart_path) if chart_path else None, signal_id))
    return "pending"


def get_pending(signal_id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT review_status AS status, card_text, chart_path FROM signals "
            "WHERE id=%s", (signal_id,)).fetchone()
    return dict(row) if row else None


def list_pending() -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id AS signal_id, created_at FROM signals "
            "WHERE review_status='pending' ORDER BY created_at").fetchall()
    return [{"signal_id": r["signal_id"], "created_at": _iso(r["created_at"])}
            for r in rows]


def count_pending() -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM signals WHERE review_status='pending'").fetchone()
    return row["n"]


def set_review_status(signal_id: int, status: str, reviewed_by=None) -> bool:
    if DRY_RUN:
        print(f"sb_store: DRY RUN — review #{signal_id} -> {status} NOT written")
        return True
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE signals SET review_status=%s, reviewed_at=now(), reviewed_by=%s "
            "WHERE id=%s", (status, reviewed_by, signal_id))
        return cur.rowcount > 0


def publish_signal(signal_id: int, channel_message_id: int) -> bool:
    if DRY_RUN:
        print(f"sb_store: DRY RUN — publish #{signal_id} NOT written")
        return True
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE signals SET review_status='published', published_at=now(), "
                "channel_message_id=%s WHERE id=%s",
                (channel_message_id, signal_id))
            if cur.rowcount == 0:
                return False
            cur.execute(
                """INSERT INTO subscriber_signals(subscriber_id, signal_id)
                   SELECT telegram_id, %s FROM subscribers WHERE status='active'
                   ON CONFLICT DO NOTHING""", (signal_id,))
    return True


# ---------------------------------------------------------------- subscribers

def get_subscriber(chat_id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT telegram_id, username, name, status, activated_at, expires_at, "
            "invite_link, warned FROM subscribers WHERE telegram_id=%s",
            (chat_id,)).fetchone()
    if not row:
        return None
    row = dict(row)
    row["chat_id"] = row.pop("telegram_id")
    row["activated_at"] = _iso(row["activated_at"])
    row["expires_at"] = _iso(row["expires_at"])
    return row


def upsert_subscriber(chat_id: int, name: str, expires_at: str, invite_link):
    if DRY_RUN:
        print(f"sb_store: DRY RUN — activate {chat_id} NOT written")
        return
    with _conn() as conn:
        conn.execute(
            """INSERT INTO subscribers(telegram_id, name, status, activated_at,
                                      expires_at, invite_link, warned)
               VALUES(%s,%s,'active',now(),%s,%s,false)
               ON CONFLICT (telegram_id) DO UPDATE SET
                 status='active', expires_at=EXCLUDED.expires_at,
                 invite_link=EXCLUDED.invite_link, warned=false""",
            (chat_id, name, expires_at, invite_link))


def set_subscriber_status(chat_id: int, status: str):
    if DRY_RUN:
        print(f"sb_store: DRY RUN — subscriber {chat_id} -> {status} NOT written")
        return
    with _conn() as conn:
        conn.execute("UPDATE subscribers SET status=%s WHERE telegram_id=%s",
                     (status, chat_id))


def get_subscriber_invite(chat_id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT invite_link FROM subscribers WHERE telegram_id=%s",
            (chat_id,)).fetchone()
    return row["invite_link"] if row else None


def list_subscribers(limit: int = 0) -> list:
    sql = ("SELECT telegram_id AS chat_id, name, status, expires_at FROM subscribers "
           "ORDER BY status, expires_at")
    with _conn() as conn:
        rows = conn.execute(sql + (" LIMIT %s" % limit if limit else "")).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["expires_at"] = _iso(d["expires_at"])
        out.append(d)
    return out


def list_active_subscribers() -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT telegram_id AS chat_id, username, name, expires_at FROM subscribers "
            "WHERE status='active'").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["expires_at"] = _iso(d["expires_at"])
        out.append(d)
    return out


def list_active_for_sweep() -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT telegram_id AS chat_id, expires_at, invite_link, warned "
            "FROM subscribers WHERE status='active'").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["expires_at"] = _iso(d["expires_at"])
        out.append(d)
    return out


def set_warned(chat_id: int):
    if DRY_RUN:
        return
    with _conn() as conn:
        conn.execute("UPDATE subscribers SET warned=true WHERE telegram_id=%s",
                     (chat_id,))


# ---------------------------------------------------------------- subscriber_signals / deliveries

def user_signal_stats(chat_id: int) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT s.status, COUNT(*) AS n FROM subscriber_signals ss "
            "JOIN signals s ON s.id = ss.signal_id "
            "WHERE ss.subscriber_id=%s GROUP BY s.status", (chat_id,)).fetchall()
    return [{"status": r["status"], "n": r["n"]} for r in rows]


def recent_published(limit: int = 10) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, direction, status FROM signals "
            "WHERE published_at IS NOT NULL ORDER BY published_at DESC LIMIT %s",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def has_subscriber_signal(chat_id: int, signal_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM subscriber_signals "
            "WHERE subscriber_id=%s AND signal_id=%s",
            (chat_id, signal_id)).fetchone()
    return row is not None


def mark_entered(chat_id: int, signal_id: int):
    if DRY_RUN:
        return
    with _conn() as conn:
        conn.execute(
            "UPDATE subscriber_signals SET entered_self=true "
            "WHERE subscriber_id=%s AND signal_id=%s", (chat_id, signal_id))


def get_delivery(signal_id: int):
    with _conn() as conn:
        row = conn.execute(
            "SELECT channel_message_id, published_at FROM signals WHERE id=%s",
            (signal_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["published_at"] = _iso(d["published_at"])
    return d


def published_today() -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM signals WHERE published_at IS NOT NULL "
            "AND (published_at AT TIME ZONE 'UTC')::date = %s",
            (_today_utc(),)).fetchone()
    return row["n"]


def panel_stats() -> dict:
    with _conn() as conn:
        subs = conn.execute(
            "SELECT status, COUNT(*) AS n FROM subscribers GROUP BY status").fetchall()
        pend = conn.execute(
            "SELECT COUNT(*) AS n FROM signals WHERE review_status='pending'").fetchone()
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM signals "
            "WHERE published_at IS NOT NULL AND status != 'open' "
            "GROUP BY status").fetchall()
    wins = sum(r["n"] for r in rows if r["status"] in ("tp1", "tp2"))
    losses = sum(r["n"] for r in rows if r["status"] == "sl")
    return {
        "subs": [(r["status"], r["n"]) for r in subs],
        "pending": pend["n"],
        "wins": wins, "losses": losses, "total": wins + losses,
    }


# ---------------------------------------------------------------- processed_updates / offset

def is_processed(update_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_updates WHERE update_id=%s", (update_id,)).fetchone()
    return row is not None


def mark_processed(update_id: int):
    if DRY_RUN:
        return
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO processed_updates(update_id) VALUES(%s) "
                "ON CONFLICT DO NOTHING", (update_id,))
            cur.execute(
                "DELETE FROM processed_updates WHERE update_id <= "
                "(SELECT MAX(update_id) - 2000 FROM processed_updates)")


def get_offset() -> int:
    try:
        value = get_bot_state("poll_offset", "0")
    except Exception:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def set_offset(value: int):
    if DRY_RUN:
        return
    set_bot_state("poll_offset", str(int(value)))


# ---------------------------------------------------------------- audit / rate limit / bot_state

def audit(admin_id: int, action: str, target="", detail="", ok=1):
    if DRY_RUN:
        return
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO admin_audit(admin_chat_id, action, target, detail, ok) "
                "VALUES(%s,%s,%s,%s,%s)",
                (admin_id, action, str(target), detail, bool(ok)))
    except Exception:
        pass


def recent_audit(limit: int = 10) -> list:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, action, target, ok FROM admin_audit "
            "ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["ts"] = _iso(d["ts"])
        out.append(d)
    return out


def rate_check_and_record(admin_id: int) -> bool:
    """20 admin actions/minute. Returns False when the limit is hit."""
    if DRY_RUN:
        return True
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM admin_rate WHERE ts < now() - interval '60 seconds'")
                cur.execute(
                    "SELECT COUNT(*) AS n FROM admin_rate WHERE admin_chat_id=%s",
                    (admin_id,))
                if cur.fetchone()["n"] >= RATE_MAX_ACTIONS:
                    return False
                cur.execute(
                    "INSERT INTO admin_rate(admin_chat_id) VALUES(%s)", (admin_id,))
                return True
    except Exception:
        return True  # never lock the admin out because the limiter broke


def get_bot_state(key: str, default=None):
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM bot_state WHERE key=%s", (key,)).fetchone()
    return row["value"] if row else default


def set_bot_state(key: str, value: str):
    if DRY_RUN:
        return
    with _conn() as conn:
        conn.execute(
            """INSERT INTO bot_state(key, value) VALUES(%s,%s)
               ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()""",
            (key, str(value)))
