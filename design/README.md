# Gold Council — Design Package (Phase A)

**Date:** 2026-11-11 | **Status:** DESIGN ONLY — no build, no deploy, no Narmer access, no schema applied.
**Staging:** `~/workspace/goals/goal/design/` → later `D:\Project\Trade` on Narmer, only after Mohamed's explicit «نفذ» for build.

## What this package is

The design for the 8 approved AlPulse-inspired additions to Gold Council (approved by Mohamed 2026-11-11 22:22 EET), plus the Supabase + learning-DB design he requested. It stages everything that will later be built on Narmer — on the VM only, as files, with nothing executed.

## Hard rules (from Mohamed — they bind the whole package)

- **NO auto-trading ever.** Gold Council gives documented recommendations only, never executes trades.
- **No Pocket Option integration anywhere.** No account creation, deposit, broker password, or broker referral.
- **No fake numbers, no unverified profit/user claims.** Paper labelled paper. Losers shown.
- **Signal cap 3/day (ceiling, not quota).** Review mode first; auto only after ~30 reviewed signals.

## Files in this package

| File | What it is |
|---|---|
| `00-proposal-alpulse-additions.md` | Full AlPulse-vs-Gold-Council feature mapping (borrowable vs rejected, with reasons), the 8-item scope, phases, and what is explicitly NOT copied. |
| `supabase/schema.sql` | PostgreSQL schema for a NEW separate Gold Council Supabase project (never the Eye of Justice project `cbnxemyjzyzgrqaqrkhk`). 16 tables, RLS on every table, indexes, FKs, CHECKs, FAQ seed. **Not applied.** |
| `workflows/signal-cycle.json` | Hourly signal cycle as JSON: data → 35 agents → M1 → M3 → M2 → E1 gate → journal (3/day cap) → chart → review queue → publish → settle → expiry → offline learning. Each step names the existing Python module. |
| `workflows/welcome-drip.json` | Onboarding drip: 4 steps (welcome → paper-mode reminder at +30m → /stats explainer at +24h → discussion-group invite at +48h). Stops on interaction. |
| `workflows/referral.json` | Gold Council referral: invite link → activation via manual payment → reward days (default 7). Anti-abuse built in. No broker, no cash. |
| `arch.md` | Architecture with Mermaid diagrams (system, agent voting graph, SQLite→Supabase data flow, DB ERD), Qdrant collections design, Redis key design, WebApp outline, 1-min video script outline, phase-2 assistant outline. |
| `D-Project-Trade-structure.md` | Exact `D:\Project\Trade` folder layout for Narmer, secrets handling, Python 3.12 venv setup, the 3 Windows Scheduled Tasks replacing the VM crons, and the open decisions list. |
| `README.md` | This file. |

## The 8 approved items (summary)

1. Telegram WebApp — signals / stats / profile (read-only, no trading actions).
2. Progress tracking — streak, signals count, win rate (extension of /stats).
3. FAQ + in-bot support (discussion group -1004446157966 + Mohamed).
4. Welcome drip sequence (paper-mode reminder, /stats explainer, discussion-group invite).
5. 1-min intro video — script/outline only, no video generated.
6. Referral system for Gold Council itself — invite → reward days, manual-payment compatible.
7. Smart assistant about our signals — phase 2, needs 3a2l LLM routing (outline only).
8. Supabase + learning DB — schema + workflow JSON + arch + Mermaid (this package).

## How to review it

1. Read `00-proposal-alpulse-additions.md` first (the decisions), then `arch.md` (the pictures), then `supabase/schema.sql` (the data).
2. The open questions are at the end of `00-proposal-alpulse-additions.md` and in `D-Project-Trade-structure.md` (open decisions list) — Supabase project, Qdrant reuse, Redis local-vs-cloud, Narmer always-on, referral days, video voiceover, WebApp hosting, cutover week.
3. Nothing here is applied anywhere. The schema has not touched Supabase or Qdrant. No code has been written for the WebApp. No video exists.

## What happens next (each step needs its own «نفذ»)

- **Phase B** — Supabase + learning DB: create the new project, apply `schema.sql`, migrate SQLite with verification, dual-write for a week.
- **Phase C** — WebApp (signals / stats / profile).
- **Phase D** — Drip + FAQ + progress.
- **Phase E** — Referral.
- **Phase F** — Smart assistant (phase 2).
- **Phase G** — Narmer move to `D:\Project\Trade`, Scheduled Tasks, 1-week uptime observation, then cutover.

## Honest state (unchanged by this package)

The machine works end-to-end; the strategy has **no proven edge yet** (latest walk-forward OOS +$990.87, +9.9%, 45.1% win, +0.061R/trade, t-stat +0.75). This design makes the *measurement* of the strategy better (per-agent votes, evaluations, corrections, settlements, learned weights with t-stats). It does not create an edge, and it says so in the proposal, the schema comments, and the architecture doc.

## Build notes — 2026-11-12 (Mohamed's «نفذ» 01:40 EET: whole project LOCAL on Narmer)

- **Local path (his order overrides the design's cloud-Supabase assumption):** local PostgreSQL 17 on Narmer is the SQL database; no Docker/Supabase CLI/Redis on the device (deferred). Qdrant/Redis deferred; Redis is cache-only, Postgres is the truth.
- **Phase B BLOCKED on the postgres superuser password** (pg_hba.conf password-auth everywhere, no pgpass). Postgres service itself was repaired (NetworkService ACL on `C:\Users\ayc\pgsql-data`) and is RUNNING. `gold_council` DB not created, schema not applied, no migration. Plain-PG adaptations recorded in `supabase/ADAPTATIONS.md`.
- **Phase C DONE:** system copied to `D:\Project\Trade\system\` (86 files, no secrets), venv Python 3.15.2 + 41 packages, dry-run smoke test exit 0 (fresh Dukascopy data; nothing logged/published). n8n 2.47.3 process alive + listening on 5678 but HTTP timed out on re-check — fragile session-0 launch.
- **Layout deviation:** the actual Narmer build uses `system\` + `system\venv`, NOT the `app\` + root `venv` layout in `D-Project-Trade-structure.md`. `scripts/create-tasks.ps1` uses the actual paths.
- **Shadow mode:** no Telegram polling/cycles from Narmer while the VM bot is live. `scripts/create-tasks.ps1` creates all tasks DISABLED; enabling them is cutover-only, on a separate «نفذ» after the 1-week observation.
- **Overnight build 2026-11-12 ~03:37–04:00 EET (Phases C–F + G prep, all in D:\Project\Trade):** WebApp static files in `system/webapp/` (6 files, data snapshot from the real journal: 0 published, 7 total, 0 closed, 7 pending review, FAQ 7); D+E implemented in the Narmer bot copy (`db.py`, `faq.py`, `drip.py`, `referral.py`, `progress.py`, `test_drip_referral.py` 46/46 on Narmer, plus surgical edits to `store.py`/`config.py`/`commands.py`/`poll.py`); F assistant skeleton (`assistant.py`, `knowledge.py`, `test_assistant.py` 20/20, `HOOK.md` — `/ask` hook NOT inserted yet, cutover work). **Live-DB verification 2026-11-12 ~03:51–03:54 EET (ONE short trust window, ~3 min, localhost-only, postgres user only):** D/E Postgres paths verified live against a scratch DB (`gold_council_verify`, dropped afterwards) — **38/38 checks passed**. Found + fixed one real bug: `referral.py` `_audit` used a literal `1` for the boolean `ok` column (works on SQLite, rejected by Postgres `DatatypeMismatch`); fixed to a bound `True` parameter; D+E suite re-run on Narmer 46/46 after the fix. `gold_council` itself was read-only during verification (counts re-confirmed: signals 6, agent_votes 150, admin_audit 204, learned_weights 25, faq 7). Window restore verified (file byte-identical, wrong-password psql FATAL, service RUNNING). **Phase G prep:** 4 Scheduled Tasks created, all Disabled (`GoldCouncil-Poll`/`Cycle`/`N8N`/`Watchdog`); `create-tasks.ps1` fixed twice during the run (`TimeSpan::MaxValue` rejected by Task Scheduler; `-Daily` + repetition is an ambiguous parameter set) and is now idempotent.
