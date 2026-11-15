#!/usr/bin/env python3
"""Migrate Gold Council SQLite -> local Postgres (gold_council). Phase B, one-time.

Sources (SQLite, read-only — never modified by this script):
  journal.db : system/data/journal.db   (signals + daily_count)
  subs.db    : system/telegram_bot/subs.db (subscribers, deliveries,
               subscriber_signals, pending, payments, admin_audit,
               login_attempts, processed_updates; admin_rate is ephemeral
               and is NOT migrated)

Target: Supabase Postgres (NEW Gold Council project, ref from the creds
file), schema already applied from design/supabase/schema.sql.
Runs ON NARMER (it reads D:\\Project\\Trade SQLite files); the target DSN
is built from --creds-file (SUPABASE_REF + SUPABASE_DB_PASSWORD, 600 perms).

Differences from the local variant (migrate-sqlite-to-supabase.py):
  * Target is Supabase cloud, not local gold_council.
  * Settlements are DERIVED from closed signals (the local variant never
    wrote them): one row per closed signal with a known exit_price.
    settled_at is the migration time — an APPROXIMATION, documented here
    and in the run summary, because SQLite records no settle timestamp.
    Closed signals with a NULL exit_price (time-only expiry close) are
    SKIPPED with a warning, never invented.

Safety rules (deliberate, do not relax):
  * Run ONCE against an EMPTY target. The script aborts if any migrated
    table already has rows (except faq, which keeps its 7-row seed and is
    never touched). There is no --force. A re-run must be a conscious
    manual decision, not a flag.
  * One transaction: --dry-run validates everything and rolls back.
  * The DSN / password is NEVER printed, logged, or stored. Pass it via
    --dsn, PG_DSN, or an interactive prompt (getpass).
  * Unknown values abort the run with the offending row identified —
    nothing is silently dropped or guessed, except the two documented
    mappings below (both reported in the summary):
      - payments.recorded_by: SQLite has no recorder column. All payments
        were recorded by the only admin, Mohamed (Telegram 2122313931).
      - payments.method: Arabic SQLite text is mapped to the Postgres
        enum (bank_transfer / vodafone_cash / usdt / other).
  * journal.card_text comes from pending.card_text when present; otherwise
    a minimal card is reconstructed from the numeric fields and marked
    as reconstructed in the text itself.

Usage (on Narmer, from D:\\Project\\Trade):
  system\\venv\\Scripts\\python.exe scripts\\migrate-sqlite-to-supabase-cloud.py --creds-file D:\\Project\\Trade\\.cloud-credentials --dry-run
  system\\venv\\Scripts\\python.exe scripts\\migrate-sqlite-to-supabase-cloud.py --creds-file D:\\Project\\Trade\\.cloud-credentials
Requires psycopg in the venv (already installed for the local migration):
  system\\venv\\Scripts\\pip.exe install "psycopg[binary]"
"""

import argparse
import getpass
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Postgres driver (psycopg v3 preferred, psycopg2 accepted; same call surface
# used below: connect(dsn), cursor(), execute(sql, params), commit/rollback).
# ---------------------------------------------------------------------------
try:
    import psycopg as _pg
    _PG_FLAVOUR = "psycopg3"
except ImportError:
    try:
        import psycopg2 as _pg
        _PG_FLAVOUR = "psycopg2"
    except ImportError:
        sys.exit(
            "ERROR: no Postgres driver. Install it into the Narmer venv:\n"
            "  D:\\Project\\Trade\\system\\venv\\Scripts\\pip.exe install \"psycopg[binary]\""
        )

ADMIN_ID = 2122313931  # Mohamed — the only admin; see recorded_by note above.

DIRECTION = {"بيع": "short", "شراء": "long"}
METHOD = {
    "تحويل بنكي": "bank_transfer",
    "فودافون كاش": "vodafone_cash",
    "usdt": "usdt",
    "USDT": "usdt",
    None: "other",
    "": "other",
}
SIGNAL_STATUS = {"open", "tp1", "tp2", "sl", "expired"}
REVIEW_STATUS = {"pending", "approved", "rejected", "published"}

AGENTS_L0 = {"R0", "N0", "R1", "R2"}
AGENTS_L1 = {"C1", "C2", "C3", "C4", "C5", "C6", "C7"}
AGENTS_L2 = {"S1", "S2", "S3a", "S3b", "S4a", "S4b", "S4c",
             "S5a", "S5b", "S5c", "S6", "S10", "S11", "S12", "S13"}
AGENTS_L3 = {"X1", "X2", "X3"}
AGENTS_L4 = {"M1", "M2", "M3", "E1", "E2", "J1"}
ALL_AGENTS = AGENTS_L0 | AGENTS_L1 | AGENTS_L2 | AGENTS_L3 | AGENTS_L4


def layer_of(agent):
    if agent in AGENTS_L0:
        return "L0-router"
    if agent in AGENTS_L1:
        return "L1-context"
    if agent in AGENTS_L2:
        return "L2-structure"
    if agent in AGENTS_L3:
        return "L3-execution"
    return "L4-judgement"


def parse_ts(value, where):
    """ISO timestamp from SQLite -> aware datetime (assumed UTC if naive)."""
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"ERROR: unparsable timestamp {value!r} at {where}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def fail(msg):
    sys.exit(f"ERROR: {msg}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--journal", default=r"D:\Project\Trade\system\data\journal.db")
    ap.add_argument("--subs", default=r"D:\Project\Trade\system\telegram_bot\subs.db")
    ap.add_argument("--weights", default=r"D:\Project\Trade\system\data\learned_weights.json")
    ap.add_argument("--dsn", default=os.environ.get("PG_DSN"))
    ap.add_argument("--creds-file", default=None,
                    help="600-perm file with SUPABASE_REF + SUPABASE_DB_PASSWORD")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate everything, then roll back (no writes)")
    args = ap.parse_args()

    for path in (args.journal, args.subs):
        if not os.path.exists(path):
            fail(f"source SQLite file not found: {path}")

    dsn = args.dsn
    if not dsn and args.creds_file:
        c = {}
        for line in open(args.creds_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                c[k.strip()] = v.strip().strip("'")
        ref = c["SUPABASE_REF"]
        dsn = (f"host=db.{ref}.supabase.co port=5432 dbname=postgres "
               f"user=postgres password={c['SUPABASE_DB_PASSWORD']}")
    if not dsn:
        pw = getpass.getpass("Postgres password for user postgres (never stored): ")
        dsn = f"host=127.0.0.1 port=5432 dbname=gold_council user=postgres password={pw}"

    j = sqlite3.connect(args.journal)
    j.row_factory = sqlite3.Row
    s = sqlite3.connect(args.subs)
    s.row_factory = sqlite3.Row

    # --- read sources ------------------------------------------------------
    j_signals = j.execute("SELECT * FROM signals ORDER BY ts").fetchall()
    pending = {r["signal_id"]: r for r in
               s.execute("SELECT * FROM pending").fetchall()}
    deliveries = {r["signal_id"]: r for r in
                  s.execute("SELECT * FROM deliveries").fetchall()}
    subs_rows = s.execute("SELECT * FROM subscribers").fetchall()
    pay_rows = s.execute("SELECT * FROM payments").fetchall()
    ss_rows = s.execute("SELECT * FROM subscriber_signals").fetchall()
    audit_rows = s.execute("SELECT * FROM admin_audit ORDER BY id").fetchall()
    login_rows = s.execute("SELECT * FROM login_attempts ORDER BY id").fetchall()
    upd_rows = s.execute("SELECT * FROM processed_updates").fetchall()

    # --- validate + prepare signals (daily_seq per UTC day, cap 3) ---------
    by_day = defaultdict(list)
    for r in j_signals:
        dt = parse_ts(r["ts"], f"journal.signals id={r['id']}")
        by_day[dt.date()].append((dt, r))
    prepared_signals = []  # (sqlite_row, day_utc, daily_seq)
    for day in sorted(by_day):
        rows = sorted(by_day[day], key=lambda t: t[0])
        if len(rows) > 3:
            fail(f"journal has {len(rows)} signals on {day} — exceeds the 3/day cap; "
                 "refusing to migrate (check the source data first)")
        for seq, (dt, r) in enumerate(rows, start=1):
            prepared_signals.append((r, day, seq))

    # --- validate votes JSON shape -----------------------------------------
    prepared_votes = defaultdict(list)  # sqlite signal id -> [(agent, ...)]
    for r in j_signals:
        raw = r["votes_json"]
        if not raw:
            print(f"WARN: journal.signals id={r['id']} has no votes_json "
                  "(migrating signal with zero votes)")
            continue
        try:
            votes = json.loads(raw)
        except json.JSONDecodeError:
            fail(f"journal.signals id={r['id']}: votes_json is not valid JSON")
        for agent, v in votes.items():
            if agent not in ALL_AGENTS:
                fail(f"journal.signals id={r['id']}: unknown agent {agent!r} "
                     "in votes_json (not one of the 35 agents)")
            sig = v.get("signal")
            conf = v.get("confidence")
            if sig not in (-1, 0, 1):
                fail(f"journal.signals id={r['id']} agent {agent}: "
                     f"vote {sig!r} is not -1/0/1")
            if not isinstance(conf, int) or not 0 <= conf <= 100:
                fail(f"journal.signals id={r['id']} agent {agent}: "
                     f"confidence {conf!r} is not an int 0-100")
            weight = float(v.get("weight_applied") or 0)
            if weight < 0:
                fail(f"journal.signals id={r['id']} agent {agent}: "
                     f"negative weight {weight}")
            degraded = bool(v.get("degraded")) or ("skipped" in v)
            reason = None
            if "skipped" in v:
                reason = f"skipped by {v['skipped']}"
            elif degraded:
                reason = v.get("detail") or None
            prepared_votes[r["id"]].append(
                (agent, layer_of(agent), sig, conf,
                 v.get("detail") or "", weight, degraded, reason))

    # --- validate subscribers / payments FKs --------------------------------
    sub_ids = {r["chat_id"] for r in subs_rows}
    for p in pay_rows:
        if p["subscriber_chat_id"] not in sub_ids:
            fail(f"payments id={p['id']} references unknown subscriber "
                 f"{p['subscriber_chat_id']} — refusing to migrate")
    for row in ss_rows:
        if row["subscriber_chat_id"] not in sub_ids:
            fail(f"subscriber_signals id={row['id']} references unknown "
                 f"subscriber {row['subscriber_chat_id']}")

    # --- connect + empty-target guard ---------------------------------------
    conn = _pg.connect(dsn)
    cur = conn.cursor()
    guarded = ["signals", "agent_votes", "settlements", "subscribers", "payments",
               "subscriber_signals", "admin_audit", "processed_updates",
               "learned_weights_history"]
    existing = {}
    for table in guarded:
        cur.execute(f"SELECT count(*) FROM public.{table}")
        existing[table] = cur.fetchone()[0]
    nonempty = {t: n for t, n in existing.items() if n > 0}
    if nonempty:
        fail("target is not empty (one-time migration refuses to re-run): "
             + ", ".join(f"{t}={n}" for t, n in sorted(nonempty.items())))

    # --- migrate ------------------------------------------------------------
    pg_signal_id = {}  # sqlite journal id -> postgres signals.id
    try:
        for r, day, seq in prepared_signals:
            direction = DIRECTION.get(r["direction"])
            if direction is None:
                fail(f"journal.signals id={r['id']}: unknown direction "
                     f"{r['direction']!r} (expected 'بيع' or 'شراء')")
            status = r["status"] or "open"
            if status not in SIGNAL_STATUS:
                fail(f"journal.signals id={r['id']}: unknown status {status!r}")
            p = pending.get(r["id"])
            d = deliveries.get(r["id"])
            if p is not None and p["card_text"]:
                card_text = p["card_text"]
                review_status = p["status"] or "pending"
                reviewed_at = parse_ts(p["reviewed_at"], f"pending {r['id']}")
                chart_path = p["chart_path"]
            else:
                dir_ar = "بيع" if direction == "short" else "شراء"
                card_text = (f"{dir_ar} XAUUSD — دخول {r['entry']}، وقف "
                             f"{r['stop']}، هدف1 {r['tp1']}، هدف2 {r['tp2']}، "
                             f"ثقة {r['confidence']}% (paper — مُعاد بناؤه من "
                             "السجل أثناء الترحيل، النص الأصلي غير محفوظ)")
                review_status = "pending"
                reviewed_at = None
                chart_path = None
            if review_status not in REVIEW_STATUS:
                fail(f"pending signal_id={r['id']}: unknown review status "
                     f"{review_status!r}")
            cur.execute(
                """INSERT INTO public.signals
                   (created_at, symbol, direction, entry, stop_loss, tp1, tp2,
                    confidence, mode, status, exit_price, pnl_r,
                    day_utc, daily_seq, chart_path, card_text,
                    review_status, reviewed_at, published_at,
                    channel_message_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (parse_ts(r["ts"], f"journal.signals id={r['id']}"),
                 r["symbol"], direction, r["entry"], r["stop"], r["tp1"],
                 r["tp2"], r["confidence"], r["mode"] or "paper", status,
                 r["exit_price"], r["pnl_r"], day, seq, chart_path,
                 card_text, review_status, reviewed_at,
                 parse_ts(d["published_at"], f"deliveries {r['id']}") if d else None,
                 d["channel_message_id"] if d else None))
            pg_signal_id[r["id"]] = cur.fetchone()[0]

        # --- settlements derived from closed signals ----------------------
        # SQLite records no settle timestamp: settled_at is the migration
        # time (documented approximation). Closed signals with a NULL
        # exit_price are skipped with a warning, never invented.
        settlements_n = 0
        for r, day, seq in prepared_signals:
            status = r["status"] or "open"
            if status not in ("tp1", "tp2", "sl", "expired"):
                continue
            if r["exit_price"] is None:
                print(f"WARN: journal.signals id={r['id']} is {status} with "
                      "no exit_price — skipping its settlement row")
                continue
            cur.execute(
                """INSERT INTO public.settlements
                   (signal_id, outcome, exit_price, pnl_r, settled_at,
                    settler)
                   VALUES (%s, %s, %s, %s, %s, 'settle.py')""",
                (pg_signal_id[r["id"]], status, r["exit_price"],
                 r["pnl_r"], datetime.now(timezone.utc)))
            settlements_n += 1

        votes_n = 0
        for sid, votes in prepared_votes.items():
            for (agent, layer, sig, conf, detail, weight, degraded,
                 reason) in votes:
                cur.execute(
                    """INSERT INTO public.agent_votes
                       (signal_id, agent, layer, vote, confidence, detail,
                        weight, degraded, degrade_reason)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (pg_signal_id[sid], agent, layer, sig, conf, detail,
                     weight, degraded, reason))
                votes_n += 1

        for r in subs_rows:
            cur.execute(
                """INSERT INTO public.subscribers
                   (telegram_id, username, name, status, activated_at,
                    expires_at, invite_link, warned)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (r["chat_id"], r["username"], r["name"],
                 r["status"] or "active",
                 parse_ts(r["activated_at"], f"subscribers {r['chat_id']}"),
                 parse_ts(r["expires_at"], f"subscribers {r['chat_id']}"),
                 r["invite_link"], bool(r["warned"])))

        method_mapped = defaultdict(int)
        for p in pay_rows:
            method = METHOD.get(p["method"], "other")
            method_mapped[(p["method"], method)] += 1
            cur.execute(
                """INSERT INTO public.payments
                   (subscriber_id, amount, currency, method, period_days,
                    paid_at, note, recorded_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (p["subscriber_chat_id"], p["amount"],
                 p["currency"] or "USD", method, p["period_days"],
                 parse_ts(p["paid_at"], f"payments {p['id']}"),
                 p["note"] or "", ADMIN_ID))

        for row in ss_rows:
            cur.execute(
                """INSERT INTO public.subscriber_signals
                   (subscriber_id, signal_id, entered_self)
                   VALUES (%s, %s, %s)""",
                (row["subscriber_chat_id"],
                 pg_signal_id[row["signal_id"]],
                 bool(row["entered_self"])))

        audit_n = 0
        for a in audit_rows:
            cur.execute(
                """INSERT INTO public.admin_audit
                   (ts, admin_chat_id, action, target, detail, ok)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (parse_ts(a["ts"], f"admin_audit {a['id']}"),
                 a["admin_chat_id"], a["action"], a["target"] or "",
                 a["detail"] or "", bool(a["ok"])))
            audit_n += 1
        for la in login_rows:
            action = "web:login" if la["ok"] else "web:login_failed"
            cur.execute(
                """INSERT INTO public.admin_audit
                   (ts, admin_chat_id, action, target, detail, ok)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (parse_ts(la["ts"], f"login_attempts {la['id']}"),
                 0, action, la["ip"] or "",
                 "dashboard login attempt", bool(la["ok"])))
            audit_n += 1

        for u in upd_rows:
            cur.execute(
                """INSERT INTO public.processed_updates
                   (update_id, processed_at) VALUES (%s, %s)""",
                (u["update_id"],
                 parse_ts(u["processed_at"], f"processed_updates {u['update_id']}")))

        # --- learned weights seed (E2 v2 walk-forward) ----------------------
        weights_n = 0
        if os.path.exists(args.weights):
            with open(args.weights, encoding="utf-8") as fh:
                wdoc = json.load(fh)
            pat = re.compile(r"([+-]?\d+(?:\.\d+)?)R\s*\(n=(\d+)\)")
            for agent, w in (wdoc.get("weights") or {}).items():
                if agent not in ALL_AGENTS:
                    fail(f"learned_weights.json: unknown agent {agent!r}")
                detail = (wdoc.get("detail") or {}).get(agent, "")
                m = pat.search(detail)
                r_exp = float(m.group(1)) if m else None
                sample_n = int(m.group(2)) if m else 0
                cur.execute(
                    """INSERT INTO public.learned_weights_history
                       (run_kind, agent, weight, r_expectancy, sample_n,
                        t_stat, notes)
                       VALUES ('walk-forward', %s, %s, %s, %s, NULL, %s)""",
                    (agent, float(w), r_exp, sample_n,
                     "Seeded from data/learned_weights.json (E2 v2, "
                     "walk-forward 2026-10-12). t_stat not recorded in the "
                     "source file — NULL, do not infer."))
                weights_n += 1
        else:
            print(f"WARN: weights file not found, skipping: {args.weights}")

        # --- verification: source vs target counts --------------------------
        checks = [
            ("signals", len(prepared_signals)),
            ("agent_votes", votes_n),
            ("settlements", settlements_n),
            ("subscribers", len(subs_rows)),
            ("payments", len(pay_rows)),
            ("subscriber_signals", len(ss_rows)),
            ("admin_audit", audit_n),
            ("processed_updates", len(upd_rows)),
            ("learned_weights_history", weights_n),
        ]
        ok = True
        for table, expected in checks:
            cur.execute(f"SELECT count(*) FROM public.{table}")
            got = cur.fetchone()[0]
            mark = "OK " if got == expected else "FAIL"
            if got != expected:
                ok = False
            print(f"  [{mark}] {table}: source={expected} target={got}")
        for (src, mapped) in sorted(method_mapped):
            print(f"  [info] payments method {src!r} -> {mapped!r} "
                  f"x{method_mapped[(src, mapped)]}")
        if not ok:
            fail("count mismatch — rolling back")
    except Exception:
        conn.rollback()
        raise

    if args.dry_run:
        conn.rollback()
        print("DRY RUN: all checks passed, rolled back (nothing written).")
    else:
        conn.commit()
        print("MIGRATION COMMITTED.")
    conn.close()
    print("Done. SQLite sources were not modified.")


if __name__ == "__main__":
    main()
