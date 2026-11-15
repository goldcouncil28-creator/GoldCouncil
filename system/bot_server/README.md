# Gold Council — bot-server HTTP API

Thin FastAPI wrapper around the **real** Gold Council pipeline, built so the
three n8n Cloud workflows can drive the bot over HTTP instead of SSH.
It contains **no signal logic**: every endpoint calls the existing functions
(`pipeline.run_pipeline`, `journal.log_signal`, `telegram_bot.review/`
`settle`/`expiry`, E2 `patterns.optimizer.learn_weights`, J1
`agents.j1_journal.analyze`). The hourly-cycle orchestration mirrors
`telegram_bot/cycle.py` step for step.

## Endpoints (exactly what the imported n8n workflows call)

| Method | Path | Body (from workflow) | Calls |
|---|---|---|---|
| GET | `/healthz` | — | read-only status (no auth) |
| POST | `/api/v1/cycle/run` | `{"mode": "paper"}` | `run_pipeline` → `journal.log_signal` → `review.queue` → `settle.settle` → `expiry.sweep` |
| POST | `/api/v1/signals/{id}/publish` | `{"approved_by": <tg id>}` | `review.approve()` → `publisher.publish()` |
| POST | `/api/v1/settle/run` | `{}` | `settle.settle()` |
| POST | `/api/v1/expiry/run` | `{}` | `expiry.sweep()` |
| POST | `/api/v1/learn/run` | `{}` | J1 `j1_journal.analyze()` (sync) + E2 walk-forward (background job) |

Response shapes match what the workflows assume:

- **cycle**: `{"outcome": "signal"|"no_signal"|"blocked_by_news"|"blocked_by_shock"|"cap_reached"|"not_configured"|"test_mode"|"pipeline_error", "signal_id"?, "detail"?, "reason"?, "settled", "expired"}` — the Switch node in the Signal Cycle workflow routes on `outcome`. A duplicate setup is reported as `no_signal` with `"reason": "duplicate"` (nothing new queued).
- **publish**: `{"published": true, "signal_id", "message_id"}` — or `404` (not in queue), `409` (already published/rejected), `503` (not configured).
- **settle**: `{"settled": <n>, "open_signals": <n>}`.
- **expiry**: `{"expired": <n>, "warned": <n>, "active": <n>}`.
- **learn**: `{"j1": {...win rate per direction...}, "e2": {"status": "started"|"skipped"|"done"|"failed", ...}}` — E2 runs in the background (a full walk-forward takes longer than n8n's 120 s HTTP timeout); its result is written to `<data_dir>/learn_result.json` and `learned_weights.json`.

## Running on the VPS

```bash
# 1. Clone the repo and create the venv (one venv for the whole system)
git clone git@github.com:goldcouncil28-creator/GoldCouncil.git
cd GoldCouncil
python3 -m venv .venv && .venv/bin/pip install -r system/bot_server/requirements.txt

# 2. Data directory — all SQLite state lives here (never in the repo):
#    journal.db, subs.db, bot_config.json, .bot-token,
#    learned_weights.json, *.parquet caches, charts/, audit/
mkdir -p /var/lib/gold-council

# 3. Put the bot config + token in the data dir (bot_config.json must set
#    "token_file" to the token path, "channel_id", "admin_ids", "mode": "review").
#    Token file permissions 600. Never commit these files.

# 4. Start (single worker — SQLite + in-memory learn status)
GC_DATA_DIR=/var/lib/gold-council \
GC_BOT_API_KEY='<long random secret>' \
.venv/bin/uvicorn bot_server.app:app --host 127.0.0.1 --port 8101 --workers 1
# (run from the system/ directory, or set PYTHONPATH to it)
```

Put a reverse proxy (Caddy/Nginx with TLS) in front if n8n Cloud must reach
it over the public internet; never expose uvicorn directly.

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `GC_DATA_DIR` | no (default `<system>/data`) | Directory holding `journal.db`, `subs.db`, `bot_config.json`, `.bot-token`, `learned_weights.json`, parquet caches. The VPS uses its own directory — no Narmer path is hard-coded. |
| `GC_BOT_API_KEY` | **yes in live mode** | Shared secret. The workflows send it as the `X-Api-Key` header (`$env.GC_BOT_API_KEY` in n8n). Missing/invalid → `401`. |
| `GC_BOT_TEST_MODE=1` | no | Silent test server: auth skipped, **no Telegram call is ever made and no state is ever mutated**. Every endpoint returns a clear `test_mode` / `not_configured` response instead of executing. Use for all verification runs. |
| `GC_SUPABASE_URL`, `GC_SUPABASE_SECRET` | not consumed by v1 | Used by the n8n Cloud Supabase credentials (workflow audit rows) and by the future J1 dual-write. The bot server itself talks only to its local SQLite journal in v1. |

## ⚠️ Activation order — read before touching n8n

The three workflows are imported into n8n Cloud **INACTIVE** and must stay
that way until **all** of this is true:

1. The VPS is live, the bot server is up behind it (`/healthz` = ok,
   `configured: true`), and `GC_DATA_DIR` holds the migrated journal.
2. The n8n Cloud credentials exist: `Gold Council Telegram Bot` and
   `Gold Council Supabase`, plus the env vars `GC_BOT_API_URL` and
   `GC_BOT_API_KEY` on the n8n instance.
3. **The Narmer equivalents are disabled first** — the 6 GoldCouncil
   Scheduled Tasks (Poll / Cycle / N8N / Watchdog / Weekly / PollWeekly).
   Otherwise every activation double-runs: the cycle would log duplicate
   signals, the drip would double-send, the referral flow would
   double-grant days.

Only then activate, one workflow at a time, and watch the first cycle.

## Paper-only

`mode` must be `"paper"` — anything else is rejected with `400`. This system
issues documented recommendations only; it never executes trades.

## Test / dry-run (VM)

```bash
cd ~/workspace/goals/goal/system
# silent test server, empty data dir — no journal, no config, no sends:
GC_DATA_DIR=/tmp/gc-test-empty GC_BOT_TEST_MODE=1 \
  venv/bin/uvicorn bot_server.app:app --host 127.0.0.1 --port 8101 --workers 1
curl localhost:8101/healthz
curl -X POST localhost:8101/api/v1/cycle/run -H 'Content-Type: application/json' -d '{"mode":"paper"}'
curl -X POST localhost:8101/api/v1/settle/run -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:8101/api/v1/expiry/run -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:8101/api/v1/learn/run -H 'Content-Type: application/json' -d '{}'
curl -X POST localhost:8101/api/v1/signals/999/publish -H 'Content-Type: application/json' -d '{"approved_by": 2122313931}'
```

Expected: `/healthz` → `{"status":"ok","mode":"test",...}`; cycle →
`not_configured`; settle/expiry/learn → zero counts + `test_mode` notes;
publish of a missing id → `404`. Nothing is sent to Telegram and no
journal file is created by these calls. (A seeded data dir with a fake
journal + pending row exercises the test-mode refusal paths; see the
verification notes in the build report.)
