"""Gold Council — bot-server HTTP API.

Thin FastAPI wrapper around the REAL Gold Council pipeline so the n8n
Cloud workflows can drive the bot without SSH. This file contains NO
signal logic: every endpoint calls the existing functions in
``pipeline`` / ``journal`` / ``telegram_bot.{cycle,review,settle,expiry}``
/ ``patterns.optimizer`` (E2) / ``agents.j1_journal`` (J1).

Endpoints (match the imported n8n workflows exactly):
    GET  /healthz
    POST /api/v1/cycle/run            {"mode": "paper"}
    POST /api/v1/signals/{id}/publish {"approved_by": <telegram id>}
    POST /api/v1/settle/run           {}
    POST /api/v1/expiry/run           {}
    POST /api/v1/learn/run            {}

Data directory
--------------
All SQLite state lives under one directory, ``GC_DATA_DIR``
(default: ``<system>/data``). The server rebinds the existing modules'
path globals to that directory at startup, so the same code runs on the
future VPS with its own journal:
    journal.db            (signals + daily_count)
    subs.db               (subscribers / pending / deliveries / audit)
    bot_config.json       (channel, admins, mode — token_file inside it)
    .bot-token            (bot token, 600 — referenced by bot_config.json)
    learned_weights.json  (E2 output, read by the cycle)
    xauusd_h1.parquet     (Dukascopy cache) + dxy_*.parquet
    charts/               (rendered signal charts)
    audit/                (JSONL audit log)

No Narmer path is hard-coded anywhere in this package.

Safety
------
* ``GC_BOT_API_KEY`` — shared secret, sent as ``X-Api-Key`` on every
  ``/api/v1/*`` call. Required in live mode.
* ``GC_BOT_TEST_MODE=1`` — test mode: auth is skipped, but NO Telegram
  call is ever made and NO state is ever mutated. Endpoints return a
  clear ``test_mode`` / ``not_configured`` response instead of executing.
  Use this for every verification run on a machine that must stay silent.
* ``mode`` is paper-only. Anything other than ``"paper"`` is rejected:
  this system issues documented recommendations only — it never executes
  trades (standing rule).
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

SYSTEM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SYSTEM_DIR))

# --- existing modules (imported, not reimplemented) -------------------------
import audit as audit_log                       # noqa: E402
import journal                                   # noqa: E402
from agents import j1_journal                    # noqa: E402
from telegram_bot import api as bot_api          # noqa: E402
from telegram_bot import charts as bot_charts    # noqa: E402
from telegram_bot import config as bot_config    # noqa: E402
from telegram_bot import expiry as bot_expiry    # noqa: E402
from telegram_bot import review as bot_review    # noqa: E402
from telegram_bot import settle as bot_settle    # noqa: E402
from telegram_bot import store as bot_store      # noqa: E402

TEST_MODE = os.environ.get("GC_BOT_TEST_MODE", "0") == "1"
API_KEY = os.environ.get("GC_BOT_API_KEY", "")
DATA_DIR = Path(os.environ.get("GC_DATA_DIR", str(SYSTEM_DIR / "data")))

if not TEST_MODE and not API_KEY:
    raise RuntimeError(
        "GC_BOT_API_KEY is not set. Set it, or run with GC_BOT_TEST_MODE=1 "
        "for a silent, non-mutating test server.")

LEARN_STATUS: dict = {"e2": {"status": "never_run"}}


# --- data-dir binding --------------------------------------------------------
def bind_data_dir(data_dir: Path) -> None:
    """Point every existing module's SQLite/cache path at ``data_dir``.

    All of these are module-level globals read at call time, so rebinding
    them here is enough — no existing file is modified.
    """
    import data_loader

    journal.DB = data_dir / "journal.db"
    j1_journal.DB = data_dir / "journal.db"
    bot_settle.JOURNAL_DB = data_dir / "journal.db"
    bot_store.DB = data_dir / "subs.db"
    bot_config.CONFIG_FILE = data_dir / "bot_config.json"
    data_loader.DATA = data_dir
    data_loader.CACHE = data_dir / "xauusd_h1.parquet"
    audit_log.BASE = data_dir / "audit"


bind_data_dir(DATA_DIR)


# --- Telegram API ------------------------------------------------------------
class NullApi:
    """Records Telegram calls instead of making them. Test mode only.

    Same method set as the FakeApi used by the project's own tests.
    """

    def __init__(self):
        self.sent = []
        self.bans = []
        self.revokes = []
        self._mid = 100

    def send_message(self, chat_id, text, reply_markup=None):
        self._mid += 1
        self.sent.append((chat_id, text))
        return {"message_id": self._mid, "chat": {"id": chat_id}}

    def send_photo(self, chat_id, photo_path, caption, reply_markup=None):
        self._mid += 1
        self.sent.append((chat_id, f"[photo] {caption[:40]}"))
        return {"message_id": self._mid, "chat": {"id": chat_id}}

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.sent.append((chat_id, f"[edit {message_id}] {text[:40]}"))
        return True

    def edit_message_caption(self, chat_id, message_id, caption, reply_markup=None):
        self.sent.append((chat_id, f"[edit-cap {message_id}] {caption[:40]}"))
        return True

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


def _api(cfg):
    """Real BotApi in live mode, NullApi in test mode (never sends)."""
    if TEST_MODE:
        return NullApi()
    return bot_api.BotApi(cfg.token)


def _cfg():
    return bot_config.Config.load()


# --- helpers -----------------------------------------------------------------
def _require_key(x_api_key: str | None):
    if TEST_MODE:
        return
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing X-Api-Key")


def _ro_count(db_path: Path, sql: str, args=()):
    """Read-only count that never creates the file if it is missing."""
    if not db_path.exists():
        return None
    try:
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = c.execute(sql, args).fetchone()
        c.close()
        return row[0] if row else 0
    except Exception:
        return None


def _open_signals() -> int:
    n = _ro_count(journal.DB, "SELECT COUNT(*) FROM signals WHERE status='open'")
    return n if n is not None else 0


def _pending_row(signal_id: int):
    """Pending row for a signal, or None. Never creates subs.db."""
    if not bot_store.DB.exists():
        return None
    try:
        c = sqlite3.connect(f"file:{bot_store.DB}?mode=ro", uri=True)
        row = c.execute(
            "SELECT status FROM pending WHERE signal_id=?", (signal_id,)).fetchone()
        c.close()
        return row
    except Exception:
        return None


def _expiry_snapshot():
    """(active, due_to_expire, due_to_warn) — read-only, no mutation."""
    if not bot_store.DB.exists():
        return 0, 0, 0
    try:
        c = sqlite3.connect(f"file:{bot_store.DB}?mode=ro", uri=True)
        now = datetime.now(timezone.utc).isoformat()
        active = c.execute(
            "SELECT COUNT(*) FROM subscribers WHERE status='active'").fetchone()[0]
        due_exp = c.execute(
            "SELECT COUNT(*) FROM subscribers WHERE status='active' "
            "AND expires_at IS NOT NULL AND expires_at <= ?", (now,)).fetchone()[0]
        due_warn = c.execute(
            "SELECT COUNT(*) FROM subscribers WHERE status='active' AND warned=0 "
            "AND expires_at IS NOT NULL AND expires_at > ? "
            "AND expires_at <= datetime(?, '+3 days')",
            (now, now)).fetchone()[0]
        c.close()
        return active, due_exp, due_warn
    except Exception:
        return 0, 0, 0


# --- app ---------------------------------------------------------------------
app = FastAPI(title="Gold Council bot-server", version="1.0.0")


@app.get("/healthz")
def healthz():
    cfg = _cfg()
    return {
        "status": "ok",
        "mode": "test" if TEST_MODE else "live",
        "data_dir": str(DATA_DIR),
        "data_dir_exists": DATA_DIR.exists(),
        "configured": bool(cfg.configured),
        "journal_signals": _ro_count(
            journal.DB, "SELECT COUNT(*) FROM signals"),
        "open_signals": _ro_count(
            journal.DB, "SELECT COUNT(*) FROM signals WHERE status='open'"),
        "pending_review": _ro_count(
            bot_store.DB, "SELECT COUNT(*) FROM pending WHERE status='pending'"),
        "learn": LEARN_STATUS,
    }


@app.post("/api/v1/cycle/run")
def cycle_run(body: dict, x_api_key: str | None = Header(default=None)):
    """Hourly cycle — mirrors telegram_bot/cycle.py step for step:
    pipeline -> journal (+review queue) -> settle -> expiry."""
    _require_key(x_api_key)
    mode = (body or {}).get("mode", "paper")
    if mode != "paper":
        raise HTTPException(status_code=400,
                            detail="mode must be 'paper' (paper-only system)")

    cfg = _cfg()
    if not cfg.configured:
        # Same behaviour as cycle.main(): quiet exit, no sends, no pipeline.
        return {"outcome": "not_configured",
                "detail": "bot token / channel / admins not configured — skipping",
                "settled": 0, "expired": 0}
    if TEST_MODE:
        return {"outcome": "test_mode",
                "detail": "test mode: pipeline not executed (no sends, no writes)",
                "settled": 0, "expired": 0}

    from data_loader import load_dxy_proxy, load_oil, load_xauusd_h1
    from pipeline import build_ctx, run_pipeline

    api = _api(cfg)
    weights_path = DATA_DIR / "learned_weights.json"
    weights = (json.loads(weights_path.read_text())["weights"]
               if weights_path.exists() else None)
    try:
        df = load_xauusd_h1()
        try:
            dxy = load_dxy_proxy()
        except Exception:
            dxy = None
        oil = load_oil()
        res = run_pipeline(df, build_ctx(df, dxy, oil), weights)
    except Exception as e:
        return JSONResponse(status_code=502, content={
            "outcome": "pipeline_error",
            "detail": f"{type(e).__name__}: {e}"})

    outcome = res["status"]
    resp = {"outcome": outcome,
            "detail": res.get("detail", ""),
            "settled": 0, "expired": 0}
    if outcome == "signal":
        card = res["card"]
        sid = journal.log_signal(card, res["verdict"].votes, mode="paper")
        if sid == -1:
            resp.update(outcome="cap_reached", signal_id=None,
                        detail="daily cap (3/day) reached")
        elif sid == -2:
            resp.update(outcome="no_signal", signal_id=None,
                        reason="duplicate",
                        detail="duplicate of an open setup — skipped")
        else:
            chart = None
            try:
                chart_path = DATA_DIR / "charts" / f"signal_{card.symbol}_{sid}.png"
                chart_path.parent.mkdir(parents=True, exist_ok=True)
                chart = bot_charts.render_signal_chart(df, card, path=chart_path)
            except Exception as e:
                resp["chart_error"] = f"{type(e).__name__}: {e}"
            queued = bot_review.queue(api, cfg, sid, card.text(), chart)
            resp.update(signal_id=sid, queued=queued,
                        entry=card.entry, stop=card.stop,
                        tp1=card.tp1, tp2=card.tp2,
                        direction=card.direction,
                        confidence=card.confidence)
    elif outcome == "no_signal":
        resp["n_votes"] = res.get("n_votes")

    # Steps 2 + 3, exactly like cycle.main() (best-effort, never break the run).
    try:
        resp["settled"] = bot_settle.settle(api, cfg)
    except Exception as e:
        resp["settle_error"] = f"{type(e).__name__}: {e}"
    try:
        before = _expiry_snapshot()
        bot_expiry.sweep(api, cfg)
        after = _expiry_snapshot()
        resp["expired"] = before[0] - after[0]
    except Exception as e:
        resp["expiry_error"] = f"{type(e).__name__}: {e}"
    return resp


@app.post("/api/v1/signals/{signal_id}/publish")
def publish_signal(signal_id: int, body: dict,
                   x_api_key: str | None = Header(default=None)):
    """Publish an approved signal — wraps review.approve() + publisher.publish()."""
    _require_key(x_api_key)
    approved_by = (body or {}).get("approved_by")

    row = _pending_row(signal_id)
    if not row:
        raise HTTPException(status_code=404, detail="signal not in review queue")
    if row[0] not in ("pending", "approved"):
        return JSONResponse(status_code=409, content={
            "published": False, "signal_id": signal_id,
            "reason": f"already {row[0]}"})
    if TEST_MODE:
        return {"published": False, "signal_id": signal_id, "test_mode": True,
                "detail": "test mode: publish not executed (no Telegram send)"}

    cfg = _cfg()
    if not cfg.configured:
        return JSONResponse(status_code=503, content={
            "published": False, "signal_id": signal_id,
            "reason": "not_configured"})
    api = _api(cfg)
    ok = bot_review.approve(api, cfg, signal_id)
    if not ok:
        return JSONResponse(status_code=409, content={
            "published": False, "signal_id": signal_id,
            "reason": "approve failed"})
    mid = _ro_count(bot_store.DB,
                    "SELECT channel_message_id FROM deliveries WHERE signal_id=?",
                    (signal_id,))
    try:  # best-effort local audit of who approved (never breaks the publish)
        with bot_store.conn() as c:
            c.execute(
                "INSERT INTO admin_audit(ts, admin_chat_id, action, target, detail, ok) "
                "VALUES(?,?,?,?,?,1)",
                (datetime.now(timezone.utc).isoformat(),
                 int(approved_by) if isinstance(approved_by, int) else 0,
                 f"api:approve:{signal_id}", str(signal_id),
                 f"approved_by={approved_by}"))
    except Exception:
        pass
    return {"published": True, "signal_id": signal_id, "message_id": mid}


@app.post("/api/v1/settle/run")
def settle_run(body: dict, x_api_key: str | None = Header(default=None)):
    """Settle open signals — wraps telegram_bot.settle.settle()."""
    _require_key(x_api_key)
    if not journal.DB.exists():
        return {"settled": 0, "open_signals": 0, "note": "no journal yet"}
    open_n = _open_signals()
    if open_n == 0:
        return {"settled": 0, "open_signals": 0}
    if TEST_MODE:
        return {"settled": 0, "open_signals": open_n, "test_mode": True,
                "note": "test mode: settle not executed "
                        "(no Dukascopy fetch, no Telegram edit)"}
    cfg = _cfg()
    if not cfg.configured:
        return JSONResponse(status_code=503, content={
            "settled": 0, "open_signals": open_n, "reason": "not_configured"})
    try:
        closed = bot_settle.settle(_api(cfg), cfg)
    except Exception as e:
        return JSONResponse(status_code=502, content={
            "settled": 0, "open_signals": open_n,
            "detail": f"{type(e).__name__}: {e}"})
    return {"settled": closed, "open_signals": open_n}


@app.post("/api/v1/expiry/run")
def expiry_run(body: dict, x_api_key: str | None = Header(default=None)):
    """Subscription expiry sweep — wraps telegram_bot.expiry.sweep()."""
    _require_key(x_api_key)
    if not bot_store.DB.exists():
        return {"expired": 0, "warned": 0, "active": 0, "note": "no store yet"}
    active, due_exp, due_warn = _expiry_snapshot()
    if TEST_MODE:
        return {"expired": 0, "warned": 0, "active": active,
                "due_to_expire": due_exp, "due_to_warn": due_warn,
                "test_mode": True,
                "note": "test mode: sweep not executed (no Telegram send, no writes)"}
    cfg = _cfg()
    if not cfg.configured:
        return JSONResponse(status_code=503, content={
            "expired": 0, "warned": 0, "active": active,
            "reason": "not_configured"})
    before = _expiry_snapshot()
    warned_before = _ro_count(bot_store.DB,
                              "SELECT COUNT(*) FROM subscribers WHERE warned=1") or 0
    try:
        bot_expiry.sweep(_api(cfg), cfg)
    except Exception as e:
        return JSONResponse(status_code=502, content={
            "expired": 0, "warned": 0, "active": active,
            "detail": f"{type(e).__name__}: {e}"})
    after = _expiry_snapshot()
    warned_after = _ro_count(bot_store.DB,
                             "SELECT COUNT(*) FROM subscribers WHERE warned=1") or 0
    return {"expired": before[0] - after[0],
            "warned": warned_after - warned_before,
            "active": after[0], "due_to_expire": due_exp}


def _run_e2_learn():
    """E2 walk-forward learn (background job). Reuses backtest.py's learn step:
    compute_agent_signals (cached parquet) -> learn_weights (in-sample 60%)
    -> learned_weights.json. J1 stats are read live by /learn/run itself."""
    from agents._common import atr as atr_fn
    from data_loader import load_dxy_proxy, load_oil, load_xauusd_h1
    from patterns.optimizer import learn_weights
    from signals import compute_agent_signals

    LEARN_STATUS["e2"] = {"status": "running",
                          "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        df = load_xauusd_h1()
        try:
            dxy = load_dxy_proxy()
        except Exception:
            dxy = None
        oil = load_oil()
        h4 = df.resample("4h", origin="start").agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}).dropna()
        agent_sig = compute_agent_signals(df, dxy, oil, h4, workers=1)
        n = int(len(df) * 0.6)
        split_ts = df.index[n]
        sig_in = agent_sig[agent_sig.index < split_ts]
        e2 = learn_weights(sig_in, df, atr_fn(df))
        weights_path = DATA_DIR / "learned_weights.json"
        weights_path.write_text(json.dumps(e2, ensure_ascii=False, indent=1),
                                encoding="utf-8")
        result = {"status": "done",
                  "finished_at": datetime.now(timezone.utc).isoformat(),
                  "weights": e2["weights"], "detail": e2["detail"]}
        (DATA_DIR / "learn_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        LEARN_STATUS["e2"] = result
    except Exception as e:
        LEARN_STATUS["e2"] = {"status": "failed",
                              "finished_at": datetime.now(timezone.utc).isoformat(),
                              "detail": f"{type(e).__name__}: {e}"}


@app.post("/api/v1/learn/run")
def learn_run(background_tasks: BackgroundTasks, body: dict,
              x_api_key: str | None = Header(default=None)):
    """Learn — J1 synchronously (win rate per direction, read-only) +
    E2 walk-forward as a background job (slow; n8n times out at 120s)."""
    _require_key(x_api_key)
    j1 = j1_journal.analyze()
    if TEST_MODE:
        return {"j1": j1,
                "e2": {"status": "skipped",
                       "reason": "test_mode — run backtest.py for a full E2 learn"},
                "test_mode": True}
    background_tasks.add_task(_run_e2_learn)
    return {"j1": j1,
            "e2": {"status": "started",
                   "note": "E2 walk-forward running in background; "
                           "result in <data_dir>/learn_result.json"}}
