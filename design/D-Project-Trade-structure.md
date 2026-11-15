# D:\Project\Trade — folder layout for Narmer (DESIGN ONLY)

**Date:** 2026-11-11 | **Status:** design — no files have been placed on Narmer. Nothing in this document touches Narmer, SSH, or Tailscale.
**Staging on the VM:** `~/workspace/goals/goal/design/` (this package). Copy to `D:\Project\Trade` only after Mohamed's explicit «نفذ» for Phase G, with Narmer reachable (he starts Tailscale + sshd himself, admin PowerShell).

## The layout (exact — create exactly this tree on Narmer)

```
D:\Project\Trade\
│   README.md                  ← copy of design/README.md (this package)
│   .env.example               ← placeholder names ONLY, no secrets, no values
│   requirements.txt           ← pinned deps (from system/venv: backtrader, pandas,
│                                  numpy, matplotlib, FastAPI, uvicorn,
│                                  python-multipart, argon2-cffi, pyotp, httpx)
│   start-bot.bat              ← starts poll loop + cycle + dashboard (see below)
│   stop-bot.bat               ← stops all three cleanly
│
├───app\
│   ├───agents\                ← copy of system/agents/ (35 agents, unchanged)
│   ├───patterns\              ← copy of system/patterns/ (runner, evaluator, optimizer)
│   ├───telegram_bot\          ← copy of system/telegram_bot/ (poll, cycle, review,
│   │                              publisher, settle, expiry, store, cards, charts,
│   │                              commands, api, config, clear_queue)
│   ├───dashboard\             ← copy of system/dashboard/ (FastAPI app, run.sh → run.bat)
│   ├───webapp\                ← Phase C only: static WebApp (signals/stats/profile)
│   │       index.html
│   │       app.js
│   │       style.css
│   └───*.py                  ← journal.py, pipeline.py, signals.py, backtest.py,
│                                  data_loader.py, m1_arbiter.py, m2_risk.py,
│                                  audit.py, run_signals.py (copies, unchanged)
│
├───data\
│   ├───journal.db             ← SQLite fallback (copied from VM at move time)
│   ├───subs.db                ← SQLite fallback (copied from VM at move time)
│   ├───*.parquet              ← Dukascopy H1 + DXY proxy caches
│   ├───learned_weights.json   ← E2 weights (seeded into Supabase in Phase B)
│   └───audit\                 ← JSONL audit logs
│
├───design\                    ← copy of this whole design package (read-only reference)
│       00-proposal-alpulse-additions.md
│       arch.md
│       D-Project-Trade-structure.md
│       README.md
│   ├───supabase\
│   │       schema.sql
│   └───workflows\
│           signal-cycle.json
│           welcome-drip.json
│           referral.json
│
├───docs\
│       multi-agent-trading-design.md   ← copy of the v4 design doc
│       video-script-1min.md            ← Phase D: full 1-min script (outline in arch.md §7)
│       faq-content.md                  ← FAQ source text (mirrors supabase.faq seed)
│       runbook.md                      ← daily ops: review queue, settle check, expiry check
│
├───scripts\
│       migrate-sqlite-to-supabase.py   ← Phase B only (to be written then)
│       check-health.ps1                ← poll + cycle + dashboard + Supabase ping
│       backup-sqlite.ps1               ← daily copy of data/*.db to backups\
│
├───backups\                   ← created by backup-sqlite.ps1 (never in git, never synced)
│
└───logs\
        poll.log
        cycle.log
        dashboard.log
```

## What each top-level folder holds (one line each)

| Folder | Holds | Never holds |
|---|---|---|
| `app\` | The running Python code (bot + engine + dashboard + WebApp) | Secrets, .db files, logs |
| `data\` | SQLite fallback DBs, parquet caches, weights, audit JSONL | Secrets |
| `design\` | This design package, read-only reference | Live code, secrets |
| `docs\` | Design doc, video script, FAQ source, runbook | Secrets |
| `scripts\` | Migration + health + backup scripts | Secrets |
| `backups\` | Daily SQLite copies | Anything synced to cloud |
| `logs\` | poll/cycle/dashboard logs | Secrets |

## Secrets — where they live on Narmer (and where they never live)

- **Bot token:** `app\telegram_bot\.bot-token` (file, 600-equivalent: NTFS permissions for Mohamed's user only). Never in chat, never in a .bat, never in git.
- **Dashboard admin password hash:** `app\dashboard\.admin-password` (Argon2id hash, created by `set_password.py` from a file Mohamed supplies, plaintext deleted after).
- **TOTP secret (optional):** `app\dashboard\.totp-secret`, same handling.
- **Supabase URL + secret key:** Windows environment variables on Narmer (set once, admin PowerShell, `setx`), or a `.env` file with NTFS permissions for Mohamed only — **never** committed, never pasted in chat, never in `D:\Project\Trade\.env.example` (that file holds names only).
- **Qdrant API key:** same handling as Supabase (env var).
- **Redis password (if local Redis uses one):** env var.
- **`.env.example`** lists the *names* only: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, `TELEGRAM_BOT_TOKEN_FILE`, `ADMIN_TELEGRAM_ID`, `CHANNEL_ID`, `DISCUSSION_GROUP_ID`.

## Setup notes (Narmer, Windows)

1. **Python 3.12** (same major as the VM venv). Create a venv: `py -3.12 -m venv D:\Project\Trade\venv`. Never use system pip for project deps (Debian lesson on the VM; on Windows the equivalent rule is: venv only, never `--break-system-packages` / global installs).
2. Install: `D:\Project\Trade\venv\Scripts\pip install -r requirements.txt`.
3. Copy `app\`, `data\` (SQLite fallbacks), `design\`, `docs\` from the staged package. Verify `python -m py_compile` passes on the copied tree before starting anything.
4. Set the environment variables (Supabase, Qdrant, Redis) — see "Secrets" above.
5. **No Docker is required for Phase G.** Docker Desktop is needed only if Redis is chosen as local-on-Narmer (open decision below). If Redis stays cloud, Narmer needs no Docker.
6. **No Supabase self-hosting on Narmer.** Supabase stays cloud (its system-of-record Postgres). Local-on-Narmer means the *code* runs on Narmer; the database is the Supabase cloud project. Self-hosted Supabase was already assessed as too heavy for an 8GB Celeron-class box — if Narmer is stronger, that assessment can be revisited, but it is NOT the plan in this design.

## Scheduled Tasks (replacing the VM crons)

The VM runs three crons; Narmer runs three Windows Scheduled Tasks, same intervals, same scripts. Each task runs the venv Python explicitly and appends to `logs\`.

| VM cron | Narmer Scheduled Task | Command (in `D:\Project\Trade`) | Trigger |
|---|---|---|---|
| `trading-bot-poll` (2 min) | `GoldCouncil-Poll` | `venv\Scripts\python.exe app\telegram_bot\poll.py` | Every 2 minutes, indefinitely |
| `trading-bot-cycle` (1 h) | `GoldCouncil-Cycle` | `venv\Scripts\python.exe app\telegram_bot\cycle.py` | Hourly, on the hour |
| `trading-dashboard-watchdog` (15 min) | `GoldCouncil-Watchdog` | `powershell -File scripts\check-health.ps1` (restarts dashboard if down) | Every 15 minutes |

- Tasks run as Mohamed's user, "Run whether user is logged on or not" **only if he chooses that** — otherwise "Run only when user is logged on". This is his decision; the design does not set it silently.
- Each task must have "If the task is already running, do not start a new instance" (the Redis `gc:lock:cycle` key is the second layer for the cycle).
- `start-bot.bat` / `stop-bot.bat` are for manual start/stop only; the Scheduled Tasks are the live mechanism.

## Narmer always-on — the decision this design needs from Mohamed

Narmer is currently **on-demand mode** (his 2026-10-24 order): protection only automatic, Tailscale + sshd Manual, everything else manual/disabled, a manual start is session-only and does not survive a reboot. Live execution on Narmer **conflicts** with that mode:

- For the bot to poll every 2 min and cycle hourly, Narmer must stay on, and the three Scheduled Tasks must survive reboots.
- Tailscale + sshd stay Manual **unless he explicitly switches them** — the design does NOT change them. Remote access to Narmer for placing files still needs him to start Tailscale + sshd himself (admin PowerShell: `Start-Service Tailscale; Start-Service sshd`), exactly as before.
- Before the VM crons are switched off, run **one week of uptime observation** on Narmer (tasks running, dashboard up, no missed cycles). The VM stays live during that week as the fallback. Only after a clean week does the cutover happen, and only on his explicit «نفذ».

## Open decisions list (must be answered before Phase B / Phase G)

1. **New Supabase project ref/URL + secret** — via secure vault card, never in chat. (2026-11-06 key never stored; do not reuse without its project ref.)
2. **Qdrant: reuse existing cluster with new `gc_*` collections, or a new cluster?** Design assumes namespaced collections on the existing cluster; a new cluster is equally fine.
3. **Redis: local on Narmer (Docker Desktop) or cloud Redis?** No Redis connector exists today.
4. **Narmer always-on switch** — reverses the 2026-10-24 on-demand order. Explicit decision required.
5. **Referral reward days** — design default 7 days (0–30 configurable). Mohamed sets the final number.
6. **Intro video voiceover** — Mohamed or a narrator?
7. **WebApp hosting** — serve static WebApp from the FastAPI dashboard host, or a separate static host?
8. **Cutover week** — when does the 1-week Narmer uptime observation start?
