#!/usr/bin/env python3
"""Live-DB verification for Gold Council Phases D/E Postgres paths.

Runs ONCE inside a short trust window on Narmer. Two databases:
  * gold_council (PG_DSN_GOLD) — READ ONLY: count checks + faq read.
    Nothing is written here. Expected counts are the Phase B migration
    results (signals 6, agent_votes 150, admin_audit 204, ...).
  * gold_council_verify (PG_DSN_VERIFY) — scratch DB created for this
    run from schema-local.sql and DROPPED afterwards. All D/E write
    paths run here against fake Telegram ids 999999001/999999002
    (never real users) with a FakeApi that records messages and never
    touches the network.

The DSNs contain NO password (trust auth inside the window) and are
never printed. Exit 0 only when every check passes; exit 1 otherwise.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.insert(0, r"D:\Project\Trade\system")

REFERRER = 999999001
REFERRED = 999999002

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise AssertionError(name)


class FakeApi:
    def __init__(self):
        self.sent = []  # (chat_id, text)

    def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))
        return {"ok": True}


def main():
    gold_dsn = os.environ.get("PG_DSN_GOLD")
    verify_dsn = os.environ.get("PG_DSN_VERIFY")
    if not gold_dsn or not verify_dsn:
        print("ERROR: PG_DSN_GOLD and PG_DSN_VERIFY must both be set")
        return 1
    import psycopg

    # --- Part A: gold_council read-only -----------------------------------
    print("== gold_council (read-only) ==")
    expected = {
        "signals": 6, "agent_votes": 150, "subscribers": 0, "payments": 0,
        "subscriber_signals": 0, "admin_audit": 204, "processed_updates": 0,
        "learned_weights_history": 25, "faq": 7, "welcome_drips": 0,
        "referrals": 0, "progress": 0,
    }
    with psycopg.connect(gold_dsn) as conn:
        with conn.cursor() as cur:
            for table, exp in expected.items():
                cur.execute(f"SELECT count(*) FROM public.{table}")
                got = cur.fetchone()[0]
                check(f"gold_council.{table} == {exp}", got == exp, f"got {got}")
            cur.execute("SELECT count(*) FROM public.faq WHERE is_active = true")
            check("gold_council.faq active == 7", cur.fetchone()[0] == 7)

    # --- Part B: scratch DB write paths ------------------------------------
    print("== gold_council_verify (D/E write paths) ==")
    os.environ["PG_DSN"] = verify_dsn
    from telegram_bot import db, drip, faq, progress, referral

    check("backend() == postgres", db.backend() == "postgres")
    faqs = faq.get_faq()
    check("faq.get_faq() returns 7", len(faqs) == 7, f"got {len(faqs)}")
    check("faq Q1 matches seed",
          faqs[0][0].startswith("هل التوصيات تداول حقيقي"))

    api = FakeApi()
    cfg = SimpleNamespace(referral_reward_days=7)

    # Drip: on_start schedules 4 rows, sends step 1.
    fresh = drip.on_start(api, cfg, REFERRER)
    check("drip.on_start fresh", fresh is True)
    check("drip step-1 sent via api",
          len(api.sent) == 1 and api.sent[0][0] == REFERRER)
    with psycopg.connect(verify_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT step, status FROM public.welcome_drips "
                        "WHERE subscriber_id=%s ORDER BY step", (REFERRER,))
            rows = cur.fetchall()
            check("welcome_drips has 4 rows", len(rows) == 4, f"got {len(rows)}")
            check("drip step statuses",
                  rows == [(1, "sent"), (2, "scheduled"),
                           (3, "scheduled"), (4, "scheduled")],
                  str(rows))
            cur.execute("SELECT status, drip_stage FROM public.subscribers "
                        "WHERE telegram_id=%s", (REFERRER,))
            check("subscriber paused + drip_stage 1",
                  cur.fetchone() == ("paused", 1))

    # Referral: click, self-referral, grant.
    r = referral.record_click(REFERRER, REFERRED, cfg)
    check("referral.record_click invited",
          r.get("status") == "invited", str(r))
    r2 = referral.record_click(REFERRER, REFERRER, cfg)
    check("self-referral rejected", r2.get("status") == "rejected"
          and r2.get("reason") == "self_referral", str(r2))
    check("invite link format",
          referral.invite_link(REFERRER)
          == "https://t.me/GoldCouncil_bot?start=ref_999999001")
    invited, earned = referral.referral_stats(REFERRER)
    check("referral_stats invited=1 earned=0",
          (invited, earned) == (1, 0), f"got {(invited, earned)}")

    # Activate the referrer (manual-payment simulation) so the grant
    # has a subscriber row to extend, then grant.
    with psycopg.connect(verify_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE public.subscribers SET status='active', "
                        "expires_at=%s WHERE telegram_id=%s",
                        (datetime.now(timezone.utc) + timedelta(days=30),
                         REFERRER))
        conn.commit()
    before = datetime.now(timezone.utc)
    g = referral.grant_on_activation(api, cfg, REFERRED, admin_id=2122313931)
    check("grant_on_activation rewarded",
          g and g.get("status") == "rewarded" and g.get("days") == 7, str(g))
    with psycopg.connect(verify_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM public.referrals "
                        "WHERE referred_id=%s", (REFERRED,))
            check("referrals row rewarded",
                  cur.fetchone() == ("rewarded",))
            cur.execute("SELECT expires_at FROM public.subscribers "
                        "WHERE telegram_id=%s", (REFERRER,))
            exp = cur.fetchone()[0]
            check("referrer expiry extended ~37d",
                  exp is not None and
                  timedelta(days=36) < (exp - before) < timedelta(days=38),
                  f"expiry delta {(exp - before) if exp else None}")
            cur.execute("SELECT COUNT(*) FROM public.admin_audit "
                        "WHERE action='referral:reward'")
            check("audit row referral:reward == 1",
                  cur.fetchone()[0] == 1)
    invited, earned = referral.referral_stats(REFERRER)
    # NOTE: referral_stats counts status IN (invited, activated, rewarded)
    # as "invited" — the referred user still counts as brought in after
    # the reward. So invited stays 1, earned becomes 7. (My first version
    # of this check wrongly expected invited=0.)
    check("referral_stats after grant invited=1 earned=7",
          (invited, earned) == (1, 7), f"got {(invited, earned)}")

    # Progress: zero-signal recompute upserts a zero row.
    res = progress.recompute(REFERRER)
    check("progress.recompute zeros",
          res == {"signals_seen": 0, "signals_entered": 0, "wins": 0,
                  "losses": 0, "win_rate": 0.0, "current_streak": 0,
                  "best_streak": 0}, str(res))
    with psycopg.connect(verify_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT signals_seen FROM public.progress "
                        "WHERE subscriber_id=%s", (REFERRER,))
            check("progress row upserted", cur.fetchone() == (0,))

    # Drip run_due: force step 2 due, send it; kicked subscriber skipped.
    with psycopg.connect(verify_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE public.welcome_drips SET scheduled_for=%s "
                        "WHERE subscriber_id=%s AND step=2",
                        (datetime.now(timezone.utc) - timedelta(minutes=1),
                         REFERRER))
        conn.commit()
    n_sent = len(api.sent)
    sent = drip.run_due(api, cfg)
    check("run_due sent 1", sent == 1, f"sent={sent}")
    check("run_due message is step-2 body",
          len(api.sent) == n_sent + 1
          and api.sent[-1][1].startswith("تذكير سريع"))
    with psycopg.connect(verify_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM public.welcome_drips "
                        "WHERE subscriber_id=%s AND step=2", (REFERRER,))
            check("step 2 marked sent", cur.fetchone() == ("sent",))
            cur.execute("UPDATE public.subscribers SET status='kicked' "
                        "WHERE telegram_id=%s", (REFERRER,))
            cur.execute("UPDATE public.welcome_drips SET scheduled_for=%s, "
                        "status='scheduled' WHERE subscriber_id=%s AND step=3",
                        (datetime.now(timezone.utc) - timedelta(minutes=1),
                         REFERRER))
        conn.commit()
    sent = drip.run_due(api, cfg)
    check("run_due skips kicked (0 sent)", sent == 0, f"sent={sent}")
    with psycopg.connect(verify_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM public.welcome_drips "
                        "WHERE subscriber_id=%s AND step=3", (REFERRER,))
            check("step 3 marked skipped", cur.fetchone() == ("skipped",))

    # Step-4 body: placeholder present, no invented link.
    check("step-4 has TBD placeholder, no t.me link",
          "TBD" in drip.STEP_BODIES[4]
          and "t.me" not in drip.STEP_BODIES[4])

    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed.")
    if failed:
        print("FAILED:", [c[0] for c in failed])
        return 1
    print("ALL DB CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
