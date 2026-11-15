# Gold Council — GitHub Actions hosting (design + build record)

**Status:** approved by Mohamed 2026-11-15 (tapped «نفذ على GitHub Actions»);
«نخلص كل حاجة واي عقبة نتخطاها… مانقفش». Oracle VPS is **dropped**
(signup would not complete). This build is the Actions replacement.

## 1. Decisions (locked)

| Decision | Value | Why |
|---|---|---|
| Bot host | GitHub Actions, repo `goldcouncil28-creator/GoldCouncil` (public, `main`) | Public repo = unlimited free Actions minutes; cron-native; code already there |
| GitLab | Rejected | SaaS free tier = 400 CI min/month; a 5-min poller alone needs ~8,600 runs/month |
| Oracle VPS | Dropped | Signup failing; no server to maintain |
| n8n Cloud workflows | **KEPT, stay INACTIVE** | They wait for an always-on server Mohamed will bring later; not deleted, disabled, or altered |
| Web dashboard + bot-server API | **KEPT, not deployed** | Same reason; control stays on Telegram `/admin` (his 2026-11-06 choice) |
| Narmer | **Stays OFF** | Nothing runs on his PC anymore; rollback never re-enables Narmer |
| State | Supabase (Gold Council project `xxbtrtdjijrhmcbzmxxm`) via direct psycopg as `postgres` | RLS is bypassed by the owner connection; no new policies needed |
| SQLite | Default locally / on the VM; `GC_STORE=supabase` switches the runtime | Local and VM behaviour unchanged unless the env var is set |

## 2. Architecture

```
GitHub Actions (ubuntu-latest, Python 3.12)
  poll.yml   — cron every 5 min ─┐
  cycle.yml  — cron hourly :07   ├─► checkout repo → pip install (requirements-actions.txt)
                                 ├─► actions/cache restores system/data/*.parquet
                                 ├─► python -m telegram_bot.poll   (single pass)
                                 └─► python -m telegram_bot.cycle  (pipeline → queue → settle → expiry)
                                        │ psycopg direct (SUPABASE_DB_*)
                                        ▼
                                   Supabase postgres (16 tables + bot_state + admin_rate)
                                        │ urllib (stdlib)
                                        ▼
                                   Telegram api.telegram.org (@GoldCouncil_bot)
```

- Every run starts from a clean checkout. **No state lives on the runner.**
  The only cross-run state is Supabase (+ the `data/` cache, best-effort).
- `poll.py` and `cycle.py` were already single-pass cron jobs — no redesign,
  only the storage layer changes underneath them.
- The 3 n8n Cloud workflows are **not** triggered by anything in this build.
  Actions cron replaces their scheduling role for the bot itself.

## 3. Jobs

| Workflow | Schedule | Command | Notes |
|---|---|---|---|
| `.github/workflows/poll.yml` | `*/5 * * * *` | `python -m telegram_bot.poll` | Single `getUpdates` pass; offset from `bot_state.poll_offset`; idempotent via `processed_updates` |
| `.github/workflows/cycle.yml` | `7 * * * *` | `python -m telegram_bot.cycle` | Minute :07 avoids exact-minute collision with a poll run; pipeline + queue + settle + expiry sweep |
| Both | `workflow_dispatch` with `dry_run` input | Same commands, `GC_DRY_RUN=1` | Dry run stubs Telegram sends (BotApi no-op) for the first live test |

- Jobs are short and idempotent; each logs counts like the existing scripts
  (`poll: N updates processed, M duplicates skipped`, `bot: queued signal #…`,
  `bot: settled N signals`).
- `actions/cache` caches `system/data/*.parquet` (key: `gc-market-data-v1`,
  restore-keys fallback). Without it every cycle run re-downloads ~36k H1 bars.

## 4. Store layer — `telegram_bot/sb_store.py` + `telegram_bot/backend.py`

### 4.1 Backend interface

One interface, two implementations. `backend.py:get_backend()` returns the
SQLite implementation (`store` + `journal`, unchanged behaviour) or the
Supabase implementation (`sb_store`) when `GC_STORE=supabase`.
Call sites (`poll`, `cycle`, `review`, `publisher`, `settle`, `expiry`,
`commands`, `agents/j1_journal`) call `backend.<fn>` — never raw SQL, never
`store.conn()` directly, when running under Supabase.

Functions (Supabase side; SQLite side mirrors them):

| Function | Supabase behaviour |
|---|---|
| `log_signal(card, votes, e1, m3, r0, chart_path, mode='paper') -> int` | See §4.2. Returns new id, `-1` cap, `-2` duplicate |
| `list_open_signals()` | `signals WHERE status='open'` as dicts (direction `long`/`short`) |
| `close_signal(id, status, exit_price, pnl_r)` | UPDATE signals + INSERT settlements (skipped when `exit_price IS NULL`) |
| `get_signal(id)` / `stats()` | Row lookup / wins-losses aggregates |
| `journal_stats_by_direction()` | For J1: `{direction: {trades, win_rate}}` from closed signals |
| `queue_pending(id, card_text, chart_path)` | UPDATE signals review fields (`review_status='pending'`) |
| `get_pending(id)` / `list_pending()` / `count_pending()` | Read review queue from `signals` |
| `set_review_status(id, status, reviewed_by)` | UPDATE `review_status`, `reviewed_at`, `reviewed_by` |
| `publish_signal(id, channel_message_id)` | `review_status='published'`, `published_at`, `channel_message_id` + `subscriber_signals` rows for active subs |
| `get_subscriber(id)` / `upsert_subscriber(...)` / `set_subscriber_status(id, status)` / `list_subscribers()` / `list_active_subscribers()` / `list_active_for_sweep()` / `set_warned(id)` | `subscribers` table (`telegram_id` PK) |
| `user_signal_stats(chat_id)` / `recent_published(limit)` / `has_subscriber_signal(chat_id, sid)` / `mark_entered(chat_id, sid)` | `subscriber_signals` JOIN `signals` |
| `get_delivery(id)` | `signals.channel_message_id` (+ `published_at`) |
| `published_today()` | COUNT signals with `published_at` today (UTC) |
| `is_processed(uid)` / `mark_processed(uid)` | `processed_updates` (+ prune to last 2,000) |
| `audit(admin_id, action, target, detail, ok)` / `recent_audit(limit)` | `admin_audit` |
| `rate_check_and_record(admin_id) -> bool` | `admin_rate` table (new, §4.4): prune 60s window, 20/min |
| `get_bot_state(key, default)` / `set_bot_state(key, value)` | `bot_state` table (new, §4.4) |

### 4.2 `log_signal` — the exact rules

1. `day_utc` = today (UTC); `n = COUNT(signals WHERE day_utc = today)`.
   `n >= 3` → return `-1` (cap, not quota — never invent a signal).
2. **Dedup guard (Narmer fix, backported):** same
   `(symbol, direction, entry, stop_loss, tp1, tp2)` with `status='open'`
   OR `review_status='pending'` → return `-2`, no insert, no cap consumed.
   Direction is stored `long`/`short` (SQLite held Arabic `شراء`/`بيع`).
3. `daily_seq = n + 1` (`UNIQUE(day_utc, daily_seq)` enforces the cap at the DB too).
4. One transaction inserts: the `signals` row (`card_text` NOT NULL,
   `chart_path`, `review_status='pending'`, `e1_score`, `regime` only if in
   `trend/range/shock`, `atr`), the `agent_votes` rows (25; `layer` derived
   from the agent name; `weight` from `weight_applied`; `degraded`/`degrade_reason`
   per the migration script), one `evaluations` row (`evaluator='E1'`,
   `score`, `passed = score >= 70`, `reasons` from `checks`) when E1 data is
   present, one `corrections` row (`attacks`, `veto`, `attack_text`) when M3
   data is present. Any bad agent name / CHECK violation rolls everything back.
5. `entry/stop_loss/tp1/tp2` are `numeric(12,2)` — prices round to 2dp on insert.

### 4.3 Settle semantics (Narmer fix, not the VM copy)

- **TP2 is checked before TP1** (the VM copy checks TP1 first and shadows TP2).
- Time-only expiry after 8h: `status='expired'`, `exit_price=NULL`, `pnl_r=NULL`
  — the close price is **never invented**.
- A close with `exit_price IS NULL` writes **no** `settlements` row
  (`settlements.exit_price/pnl_r` are NOT NULL); the signal row alone records it.
- Per-row `try/except`: one bad signal never aborts the whole settle pass.
- `_announce` edits the channel message using `signals.channel_message_id`
  + `card_text` (the `deliveries` table does not exist in Supabase).

### 4.4 New tables (migration `supabase/migrations/0003_bot_state_admin_rate.sql`)

```sql
CREATE TABLE IF NOT EXISTS bot_state (
  key text PRIMARY KEY,
  value text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO bot_state(key, value) VALUES ('mode','review'), ('reviewed_count','0'), ('poll_offset','0')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS admin_rate (
  admin_chat_id bigint NOT NULL,
  ts timestamptz NOT NULL,
  PRIMARY KEY (admin_chat_id, ts)
);
CREATE INDEX IF NOT EXISTS admin_rate_ts_idx ON admin_rate (admin_chat_id, ts DESC);
```

- `bot_state` replaces `bot_config.json` writes for `mode` and `reviewed_count`
  (and holds `poll_offset`, replacing the `.offset` file). `bot_config.json`
  in the repo keeps `channel_id`/`admin_ids` (config, not secrets) and stays
  the source for those two values.
- `admin_rate` replaces the SQLite rate-limit table (the schema has no
  counterpart; it was documented as ephemeral, but on Actions there is no
  SQLite at all, so it must live in Supabase).

### 4.5 Config changes (`telegram_bot/config.py`)

- `TELEGRAM_BOT_TOKEN` env var overrides the token file (the file never
  exists on a runner). Channel/admin still come from `bot_config.json`.
- When `GC_STORE=supabase`, `mode` and `reviewed_count` are read from
  `bot_state` at load and `cfg.set()` for those two keys writes to `bot_state`
  (never to `bot_config.json` — the checkout is ephemeral and must not be
  dirtied). All other keys keep file behaviour.
- `GC_DRY_RUN=1`: `BotApi` becomes a no-op (logs the call, returns a fake
  `message_id`) — used for the first Actions test only.
- `configured` still requires token + channel + admin; unconfigured jobs exit 0
  silently (the existing config-gate).

### 4.6 What the SQLite path keeps

- `store.py` / `journal.py` keep working exactly as before (plus the dedup
  guard backported into `journal.log_signal`, the approved Narmer fix).
- `run_signals.py`, `backtest.py`, the dashboard and `bot_server` keep using
  SQLite — they are not part of Actions v1 and are not touched.
- `agents/j1_journal.py`: reads `journal.db` today; under Supabase it reads
  via `backend.journal_stats_by_direction()` (same shape, `stats: {}` when empty).

## 5. Data / fetch on a cold runner

- Loaders default to `2026-04-12 → now` (~5,200 H1 bars XAUUSD + 6 DXY pairs
  + oil attempts ≈ 36k bars, 7–9 Dukascopy fetches, minutes on first run).
  No cache file is *required* — everything is downloadable.
- `actions/cache` restores `system/data/*.parquet`; the loader's 6h freshness
  rule means an hourly run is a cache hit (slice only). First run after a
  cache miss re-downloads the full window — acceptable once.
- `learned_weights.json` is **not** read by the hourly cycle
  (`cycle.py` passes no `weights`; M1 uses defaults) — it is **not** copied
  to the repo for v1. Using the cloud-learned live weights is a separate,
  later decision (it would change live behaviour).
- `data/calendar_cache.json` is committed (N0/C4 fallback); `cot_cache.json`
  is absent — C5 degrades gracefully on first run.
- `settle.py` re-fetches 3 days of H1 per cycle (`"xauusd"` instrument string;
  the Narmer copy proved the fetch works).

## 6. Secrets (Mohamed adds these in the GitHub UI)

Repo → Settings → Secrets and variables → Actions → New repository secret.
The PAT in the vault **cannot** add secrets (verified 403), so this step is his.

| Secret name | Value source (never in chat) | Used by |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | The `@GoldCouncil_bot` token (same value as `system/telegram_bot/.bot-token` on the VM) | poll + cycle (Telegram API) |
| `SUPABASE_DB_HOST` | `db.xxbtrtdjijrhmcbzmxxm.supabase.co` | psycopg direct |
| `SUPABASE_DB_PASSWORD` | Supabase database password (in the vault creds file) | psycopg direct |
| `SUPABASE_DB_USER` | `postgres` (optional; default is `postgres`) | psycopg direct |

- `SUPABASE_URL` / publishable key are **not** needed by the bot jobs
  (direct Postgres, not REST). `ZAI_API_KEY` is **not** needed for v1
  (no `/ask` — see §9).
- The workflows fail closed without secrets: `Config` is unconfigured
  → exit 0, no Telegram call, no Supabase write.

## 7. Failure modes

| Failure | Behaviour |
|---|---|
| Secrets missing | Config-gate: job exits 0, logs `not configured, skipping` |
| Dukascopy down / slow | `load_*` raises → cycle catches, continues with `dxy=None`/`oil=None`; pipeline agents degrade, never fabricate. Settle fetch failure → `settle` returns 0, next cycle retries |
| Telegram flake (`getUpdates` / send) | `BotApi` retries 3×; poll run returns 1 (job fails, next 5-min run retries). `processed_updates` + `poll_offset` make re-runs idempotent — no double-send of the same update |
| Two runs overlap | Poll runs take seconds; cycle at :07 avoids poll minutes. Supabase unique constraints (`day_utc+daily_seq`, `processed_updates` PK) reject double-writes |
| Supabase down | psycopg raises → job fails, next scheduled run retries; nothing is half-sent to Telegram *before* the DB commit in the cycle path (log → queue → send order: signal row commits first, admin card second; a send failure leaves the row `pending`, visible in `/pending`) |
| Runner cold start / cache miss | Full Dukascopy download (minutes); job timeout is 10 min per step — watch the first runs |
| `daily_seq` race | Single writer (cycle only) + unique constraint; a violation aborts that cycle's insert only |
| Clock skew / cron delay | GitHub cron can lag minutes; harmless (jobs are idempotent, cap is per UTC day) |

## 8. Rollback

- Disable the two workflows (repo → Actions → workflow → Disable) or push
  them to `workflow_dispatch`-only. That is the whole rollback.
- **Narmer is never re-enabled.** The VM SQLite DBs remain archive-only.
- Supabase rows written by Actions are real data (same tables, same rules);
  nothing needs deleting on rollback.

## 9. v2 — Narmer-only features (NOT in this build)

Built on Narmer only; the VM copy lacks them. Rebuild from the design docs
(`design/00-proposal-alpulse-additions.md`, `design/workflows/*.json`,
`design/docs/faq-content.md`, `design/docs/video-script-1min.md`) as a
separate phase — do not claim them as shipped:

- Welcome drip (4 steps) + `/faq`, `/invite`, `/support` commands
- Referral system (`start=ref_<id>`, badges, +7d default)
- `/ask` smart assistant (needs an LLM endpoint — the z.ai key is a candidate)
- Community: results journal posts (`result_posts` — no Supabase table),
  auto welcome, `/postfaq`, Friday summary, Sunday poll (`polls` — no table)
- WebApp (already live on Cloudflare Pages; BotFather URL registration pending)
- Web dashboard distinct stats (`distinct_stats()` vs row-based `stats()`)
- Live use of cloud-learned weights in the cycle (currently defaults)

## 10. First-run procedure (Mohamed's call)

1. He adds the 4 secrets (§6).
2. Actions → `poll` → Run workflow → `dry_run: true` → check the log:
   `poll: 0 updates processed…` and no Telegram call (dry-run stub).
   Same for `cycle` (dry run: the pipeline runs end-to-end and logs what it
   *would* do, but `GC_DRY_RUN=1` forces the store into no-write mode —
   `log_signal` returns a fake id and skips the insert, review/publish/settle
   writes are no-ops).
3. He confirms → Run workflow → `dry_run: false` for `poll` first
   (it only reads updates), then `cycle`. Watch the first cycle log:
   `bot: queued signal #N` or `bot: no signal (…)`, `bot: settled N signals`.
4. After the first live cycle, verify in Supabase: the new `signals` row,
   its 25 `agent_votes`, `review_status='pending'`, and the admin review
   card in Telegram.

## 11. Files

- NEW `design/github-actions-hosting.md` (this file)
- NEW `system/telegram_bot/sb_store.py`, `system/telegram_bot/backend.py`
- NEW `system/telegram_bot/test_sb_store.py` (fake-cursor tests)
- NEW `repo-git/system/../.github/workflows/poll.yml`, `cycle.yml`
- NEW `system/requirements-actions.txt` (pinned: pandas, numpy, matplotlib, dukascopy-python, psycopg[binary], pyarrow)
- NEW `design/supabase/migrations/0003_bot_state_admin_rate.sql` (applied to the live project as part of this build)
- EDIT `system/journal.py` (dedup guard backport), `system/telegram_bot/{config,poll,cycle,review,publisher,settle,expiry,commands}.py` (backend wiring), `system/agents/j1_journal.py` (Supabase stats branch)
- UNCHANGED: `bot_server/`, `dashboard/`, `run_signals.py`, `backtest.py`, n8n workflows, the site, Narmer, EOJ.
