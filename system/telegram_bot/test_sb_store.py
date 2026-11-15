"""Tests for the Gold Council Supabase store (`telegram_bot/sb_store.py`).

Fake-connection tests only: `sb_store._conn` is monkeypatched to return a
`FakeConn` that records every executed SQL statement + params and returns
canned rows. No real Postgres, no network, no BotApi, no real journal.db /
subs.db, no real secrets (placeholder strings only).

Run with the VM venv (stdlib unittest, no pytest needed):
    ~/workspace/goals/goal/system/venv/bin/python -m unittest telegram_bot.test_sb_store -v
or as a script:
    ~/workspace/goals/goal/system/venv/bin/python telegram_bot/test_sb_store.py

Covers design doc `design/github-actions-hosting.md` §4 store rules:
- log_signal: daily cap (-1), dedup (-2), happy-path inserts (signals row,
  agent_votes with layer mapping, evaluations, corrections), unknown agents
  skipped, direction mapping (Arabic -> long/short, unknown refused).
- close_signal: no settlements row on time-only expiry (exit_price None);
  settlements row (settler 'settle.py', ON CONFLICT DO NOTHING) with a price.
- Dry run: reads still evaluated, zero writes.
- bot_state get/set, rate_check_and_record, poll offset get/set.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from m2_risk import SignalCard  # noqa: E402
from telegram_bot import sb_store  # noqa: E402


# ---------------------------------------------------------------- fake DB

class FakeCursor:
    """Records execute() calls; fetchone/fetchall pop canned rows."""

    def __init__(self, conn):
        self.conn = conn
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        return self

    def fetchone(self):
        if self.conn.fetchone_results:
            return self.conn.fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self.conn.fetchall_results:
            return self.conn.fetchall_results.pop(0)
        return []


class FakeConn:
    """Stands in for a psycopg connection: context manager + cursor() +
    execute() (sb_store uses both `conn.cursor()` and `conn.execute()`)."""

    def __init__(self):
        self.executed = []          # [(sql, params), ...] in call order
        self.fetchone_results = []  # queue of dicts/None for fetchone()
        self.fetchall_results = []  # queue of lists for fetchall()
        self._cursor = FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor

    def execute(self, sql, params=None):
        self._cursor.execute(sql, params)
        return self._cursor


# ---------------------------------------------------------------- helpers

def make_card(direction="شراء"):
    return SignalCard(symbol="XAUUSD", direction=direction, entry=4030.0,
                      stop=4020.0, tp1=4045.0, tp2=4060.0, confidence=78,
                      risk_reward=2.0, risk_usd=100.0, size_oz=0.25,
                      analysis="test")


def make_votes():
    """One vote per layer + one unknown agent (must be skipped, not fatal)."""
    def v(signal, confidence=80, weight=1.0):
        return {"signal": signal, "confidence": confidence,
                "detail": "d", "weight_applied": weight}
    return {
        "R0": v(1), "C1": v(1), "S1": v(-1), "X1": v(1), "M1": v(1),
        "ZZ9": v(1),  # unknown agent -> skipped
    }


def norm(sql):
    return " ".join(sql.split())


class SbStoreTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeConn()
        self._orig_conn = sb_store._conn
        self._orig_dry = sb_store.DRY_RUN
        sb_store._conn = lambda: self.fake
        sb_store.DRY_RUN = False

    def tearDown(self):
        sb_store._conn = self._orig_conn
        sb_store.DRY_RUN = self._orig_dry

    # -- query helpers over the recorded statements -------------------
    def sqls(self):
        return [norm(s) for s, _ in self.fake.executed]

    def stmts(self, needle):
        """[(sql, params)] whose SQL contains `needle` (whitespace-normalised)."""
        return [(norm(s), p) for s, p in self.fake.executed if needle in norm(s)]

    def writes(self):
        return [(s, p) for s, p in self.fake.executed
                if norm(s).startswith(("INSERT", "UPDATE", "DELETE"))]

    # ============================================================ log_signal

    def test_log_signal_daily_cap_returns_minus_1(self):
        self.fake.fetchone_results = [{"n": 3}]
        sid = sb_store.log_signal(make_card(), make_votes())
        self.assertEqual(sid, -1)
        # Cap evaluated from the COUNT read; nothing inserted.
        self.assertEqual(len(self.fake.executed), 1)
        self.assertIn("COUNT(*)", self.sqls()[0])
        self.assertEqual(self.writes(), [])

    def test_log_signal_duplicate_setup_returns_minus_2(self):
        self.fake.fetchone_results = [{"n": 0}, {"id": 7}]
        sid = sb_store.log_signal(make_card(), make_votes())
        self.assertEqual(sid, -2)
        self.assertEqual(len(self.fake.executed), 2)  # COUNT + dedup SELECT
        self.assertEqual(self.writes(), [])
        dedup_sql, dedup_params = self.fake.executed[1]
        self.assertIn("status='open' OR review_status='pending'", norm(dedup_sql))
        self.assertEqual(dedup_params[1], "long")  # direction mapped in dedup

    def test_log_signal_happy_path(self):
        # COUNT n=1 -> daily_seq 2; dedup finds nothing; INSERT returns id 42.
        self.fake.fetchone_results = [{"n": 1}, None, {"id": 42}]
        e1 = {"score": 80, "checks": ["edge ok", "risk ok"]}
        m3 = {"attacks": ["attack one", "attack two"], "veto": True}
        r0 = {"regime": "trend", "atr": 12.5}
        sid = sb_store.log_signal(make_card(), make_votes(), e1=e1, m3=m3,
                                  r0=r0, chart_path=Path("/tmp/x.png"))
        self.assertEqual(sid, 42)

        # --- signals row ---
        sig = self.stmts("INSERT INTO signals")
        self.assertEqual(len(sig), 1)
        sig_sql, sig_params = sig[0]
        self.assertIn("review_status", sig_sql)
        self.assertIn("'pending'", sig_sql)
        # (symbol, direction, entry, stop, tp1, tp2, confidence, e1_score,
        #  mode, day, daily_seq, card_text, chart_path, regime, atr)
        self.assertEqual(sig_params[0], "XAUUSD")
        self.assertEqual(sig_params[1], "long")            # شراء -> long
        self.assertEqual(sig_params[2], 4030.0)
        self.assertEqual(sig_params[3], 4020.0)
        self.assertEqual(sig_params[4], 4045.0)
        self.assertEqual(sig_params[5], 4060.0)
        self.assertEqual(sig_params[6], 78)
        self.assertEqual(sig_params[7], 80)                # e1_score
        self.assertEqual(sig_params[8], "paper")
        self.assertEqual(sig_params[10], 2)                # daily_seq = n + 1
        self.assertIn("شراء XAUUSD", sig_params[11])      # card_text
        self.assertEqual(sig_params[12], "/tmp/x.png")     # chart_path
        self.assertEqual(sig_params[13], "trend")          # regime
        self.assertEqual(sig_params[14], 12.5)             # atr

        # --- agent_votes rows: layer mapping + unknown agent skipped ---
        votes = self.stmts("INSERT INTO agent_votes")
        self.assertEqual(len(votes), 5)  # 6 votes given, ZZ9 skipped
        by_agent = {p[1]: p for _, p in votes}
        self.assertEqual(set(by_agent), {"R0", "C1", "S1", "X1", "M1"})
        # (signal_id, agent, layer, vote, confidence, detail, weight,
        #  degraded, degrade_reason)
        self.assertEqual(by_agent["R0"][2], "L0-router")
        self.assertEqual(by_agent["C1"][2], "L1-context")
        self.assertEqual(by_agent["S1"][2], "L2-structure")
        self.assertEqual(by_agent["X1"][2], "L3-execution")
        self.assertEqual(by_agent["M1"][2], "L4-judgement")
        for params in by_agent.values():
            self.assertEqual(params[0], 42)  # signal_id
        self.assertEqual(by_agent["S1"][3], -1)  # vote value carried through

        # --- evaluations row: passed = score >= 70 ---
        ev = self.stmts("INSERT INTO evaluations")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0][1], (42, 80, True, "edge ok; risk ok"))

        # --- corrections row: attacks count + veto ---
        corr = self.stmts("INSERT INTO corrections")
        self.assertEqual(len(corr), 1)
        self.assertEqual(corr[0][1], (42, 2, True, "attack one; attack two"))

    def test_log_signal_evaluations_failed_below_70(self):
        self.fake.fetchone_results = [{"n": 0}, None, {"id": 43}]
        sid = sb_store.log_signal(make_card(), {"R0": {"signal": 1, "confidence": 50,
                                                       "weight_applied": 1.0}},
                                  e1={"score": 65, "checks": ["weak"]})
        self.assertEqual(sid, 43)
        ev = self.stmts("INSERT INTO evaluations")
        self.assertEqual(ev[0][1], (43, 65, False, "weak"))

    def test_log_signal_no_e1_no_m3_writes_no_extra_rows(self):
        self.fake.fetchone_results = [{"n": 0}, None, {"id": 44}]
        sid = sb_store.log_signal(make_card(), {"R0": {"signal": 1, "confidence": 50,
                                                       "weight_applied": 1.0}})
        self.assertEqual(sid, 44)
        self.assertEqual(self.stmts("INSERT INTO evaluations"), [])
        self.assertEqual(self.stmts("INSERT INTO corrections"), [])

    def test_log_signal_unknown_direction_refused(self):
        sid = sb_store.log_signal(make_card(direction="؟؟؟"), make_votes())
        self.assertEqual(sid, -2)
        self.assertEqual(self.fake.executed, [])  # refused before any DB call

    def test_log_signal_sell_maps_to_short(self):
        self.fake.fetchone_results = [{"n": 0}, None, {"id": 45}]
        sid = sb_store.log_signal(make_card(direction="بيع"), {})
        self.assertEqual(sid, 45)
        sig = self.stmts("INSERT INTO signals")
        self.assertEqual(sig[0][1][1], "short")  # بيع -> short

    def test_log_signal_invalid_regime_becomes_null(self):
        self.fake.fetchone_results = [{"n": 0}, None, {"id": 46}]
        sb_store.log_signal(make_card(), {}, r0={"regime": "sideways", "atr": 9.0})
        sig = self.stmts("INSERT INTO signals")
        self.assertIsNone(sig[0][1][13])  # regime not in trend/range/shock
        self.assertEqual(sig[0][1][14], 9.0)

    # ============================================================ close_signal

    def test_close_signal_expiry_no_settlements_row(self):
        ok = sb_store.close_signal(42, "expired", None, None)
        self.assertTrue(ok)
        self.assertEqual(len(self.fake.executed), 1)
        sql, params = self.fake.executed[0]
        self.assertIn("UPDATE signals SET status=", norm(sql))
        self.assertEqual(params, ("expired", None, None, 42))
        self.assertEqual(self.stmts("INSERT INTO settlements"), [])

    def test_close_signal_with_price_writes_settlements(self):
        ok = sb_store.close_signal(42, "tp2", 4060.0, 3.0)
        self.assertTrue(ok)
        self.assertEqual(len(self.fake.executed), 2)
        upd_sql, upd_params = self.fake.executed[0]
        self.assertIn("UPDATE signals SET status=", norm(upd_sql))
        self.assertEqual(upd_params, ("tp2", 4060.0, 3.0, 42))
        st = self.stmts("INSERT INTO settlements")
        self.assertEqual(len(st), 1)
        st_sql, st_params = st[0]
        self.assertIn("'settle.py'", st_sql)
        self.assertIn("ON CONFLICT (signal_id) DO NOTHING", st_sql)
        self.assertEqual(st_params, (42, "tp2", 4060.0, 3.0))

    # ============================================================ direction map

    def test_dir_en_mapping(self):
        self.assertEqual(sb_store.DIR_EN["شراء"], "long")
        self.assertEqual(sb_store.DIR_EN["بيع"], "short")

    # ============================================================ dry run

    def test_dry_run_no_writes_but_reads_evaluated(self):
        sb_store.DRY_RUN = True
        # log_signal: cap/dedup reads still run, no INSERT.
        self.fake.fetchone_results = [{"n": 0}, None]
        sid = sb_store.log_signal(make_card(), make_votes(),
                                  e1={"score": 80}, m3={"attacks": ["a"]})
        self.assertEqual(sid, 1)  # fake dry-run id
        self.assertEqual(len(self.fake.executed), 2)  # COUNT + dedup only
        self.assertEqual(self.writes(), [])

        # The remaining dry-run writes are no-ops with zero statements.
        self.assertTrue(sb_store.close_signal(42, "tp1", 4045.0, 1.5))
        self.assertTrue(sb_store.set_review_status(42, "approved"))
        self.assertTrue(sb_store.publish_signal(42, 123))
        self.assertEqual(self.writes(), [])
        self.assertEqual(len(self.fake.executed), 2)

    def test_dry_run_cap_still_returns_minus_1(self):
        sb_store.DRY_RUN = True
        self.fake.fetchone_results = [{"n": 3}]
        self.assertEqual(sb_store.log_signal(make_card(), make_votes()), -1)
        self.assertEqual(self.writes(), [])

    # ============================================================ bot_state

    def test_get_bot_state_selects_bot_state(self):
        self.fake.fetchone_results = [{"value": "123"}]
        self.assertEqual(sb_store.get_bot_state("poll_offset", "0"), "123")
        sql, params = self.fake.executed[0]
        self.assertIn("SELECT value FROM bot_state", norm(sql))
        self.assertEqual(params, ("poll_offset",))

    def test_get_bot_state_missing_key_returns_default(self):
        self.fake.fetchone_results = [None]
        self.assertEqual(sb_store.get_bot_state("mode", "review"), "review")

    def test_set_bot_state_upserts(self):
        sb_store.set_bot_state("mode", "auto")
        self.assertEqual(len(self.fake.executed), 1)
        sql, params = self.fake.executed[0]
        self.assertIn("INSERT INTO bot_state", norm(sql))
        self.assertIn("ON CONFLICT (key) DO UPDATE", norm(sql))
        self.assertEqual(params, ("mode", "auto"))

    # ============================================================ rate limit

    def test_rate_check_and_record_under_limit(self):
        self.fake.fetchone_results = [{"n": 5}]
        self.assertTrue(sb_store.rate_check_and_record(111))
        self.assertEqual(len(self.fake.executed), 3)
        sql0, _ = self.fake.executed[0]
        self.assertIn("DELETE FROM admin_rate", norm(sql0))
        self.assertIn("60 seconds", norm(sql0))  # prune 60s window
        sql1, params1 = self.fake.executed[1]
        self.assertIn("SELECT COUNT(*) AS n FROM admin_rate", norm(sql1))
        self.assertEqual(params1, (111,))
        sql2, params2 = self.fake.executed[2]
        self.assertIn("INSERT INTO admin_rate", norm(sql2))
        self.assertEqual(params2, (111,))

    def test_rate_check_and_record_over_limit_no_insert(self):
        self.fake.fetchone_results = [{"n": 20}]
        self.assertFalse(sb_store.rate_check_and_record(111))
        self.assertEqual(len(self.fake.executed), 2)  # prune + COUNT only
        self.assertEqual(self.stmts("INSERT INTO admin_rate"), [])

    # ============================================================ offset

    def test_get_offset_reads_bot_state(self):
        self.fake.fetchone_results = [{"value": "42"}]
        self.assertEqual(sb_store.get_offset(), 42)
        _, params = self.fake.executed[0]
        self.assertEqual(params, ("poll_offset",))

    def test_get_offset_missing_or_bad_value_is_zero(self):
        self.fake.fetchone_results = [None]
        self.assertEqual(sb_store.get_offset(), 0)
        self.fake.fetchone_results = [{"value": "not-a-number"}]
        self.assertEqual(sb_store.get_offset(), 0)

    def test_set_offset_writes_bot_state(self):
        sb_store.set_offset(99)
        self.assertEqual(len(self.fake.executed), 1)
        sql, params = self.fake.executed[0]
        self.assertIn("INSERT INTO bot_state", norm(sql))
        self.assertEqual(params, ("poll_offset", "99"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
