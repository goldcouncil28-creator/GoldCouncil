# ADAPTATIONS — schema.sql for plain PostgreSQL 17 (local, Narmer)

Date: 2026-11-12. Status: **schema APPLIED 2026-11-12 ~03:33 EET** (see
"Applied" below). The password blocker is resolved — see "Blocker".

## Environment facts (verified 2026-11-12 ~01:41 EET)

- PostgreSQL 17, service `postgresql-x64-17`, data dir
  `C:\Users\ayc\pgsql-data` (NOT the default `C:\Program
  Files\PostgreSQL\17\data`, which is empty).
- Service runs as `NT AUTHORITY\NetworkService`.
- The service would NOT start: event log 2026-11-12 01:42 and 2026-10-22
  both show `postgres: could not access directory
  "C:/Users/ayc/pgsql-data": Permission denied`. The data dir ACL had
  SYSTEM / Administrators / NARMER\ayc only — no NetworkService entry.
- **Fix applied 2026-11-12 (build «نفذ» scope):**
  `icacls C:\Users\ayc\pgsql-data /grant
  "NT AUTHORITY\NetworkService:(OI)(CI)F" /T` — 1,786 files, 0 failed.
  After the fix the service started: `STATE: RUNNING`, 6 postgres.exe
  processes, single cluster, no orphan. `postmaster.pid` from 2026-10-24
  (PID 1140, dead) was stale and was handled by the server on start.
- `pg_hba.conf`: ALL entries are `password` auth (local + host
  127.0.0.1/32 + ::1/128, including replication). No trust/peer entry.
  No `pgpass.conf` exists at
  `C:\Users\ayc\AppData\Roaming\postgresql\pgpass.conf`.

## Blocker — postgres password (RESOLVED 2026-11-12 via trust window)

- `psql -U postgres -h 127.0.0.1` prompted for a password. The password
  was set at install (2026-10-18) and is not known to B. It was NOT
  pasted in chat, guessed, or reset.
- Mohamed approved the third option at 2026-11-12 03:30 EET («اعمل trust
  مؤقت لـ localhost»). Trust window: opened ~03:32 AM, closed ~03:34 AM
  (Narmer time, ~2 minutes). Procedure: backup pg_hba.conf (byte-verified
  with fc /b), prepend localhost-only trust for user postgres only
  (`host all postgres 127.0.0.1/32 trust`, `host all postgres ::1/128
  trust` — nothing wider), `pg_reload_conf()`, do the work, restore the
  backup (byte-verified), `pg_ctl reload`, verify. Backup file kept at
  `C:\Users\ayc\pgsql-data\pg_hba.conf.bak-20261112-0331`.
- Restore verified (all three checks passed): (a) restored file matches
  the backup byte-for-byte (fc: no differences); (b) passwordless psql
  now FAILS (`fe_sendauth: no password supplied`, exit 2) — trust is gone
  from the running server too; (c) service still RUNNING.

## Supabase-only syntax found in schema.sql (reviewed 2026-11-12)

`schema.sql` is 536 lines / 16 tables / RLS on all 16 / 24 policies.
Verified by grep (no server-side check was possible — no psql access).

1. **Roles `authenticated`, `service_role`, `anon` do not exist in
   plain Postgres.** Policies use `FOR ... TO authenticated` /
   `TO service_role`. On plain PG, `CREATE POLICY` fails with
   "role does not exist".
   Adaptation: before applying, run
   `CREATE ROLE authenticated NOLOGIN; CREATE ROLE service_role NOLOGIN;
   CREATE ROLE anon NOLOGIN;`
   (keeps the policy text unchanged; roles are placeholders until the
   WebApp auth exists).
2. **5 policies use `auth.jwt() ->> 'telegram_id'`** (lines ~490-502:
   `auth_read_own_subscriber`, `auth_read_own_progress`,
   `auth_read_own_subscriber_signals`, `auth_read_own_referrals`,
   `auth_read_own_drips`). The `auth` schema exists only in Supabase;
   on plain PG these fail with "schema auth does not exist".
   Adaptation: replace
   `((auth.jwt() ->> 'telegram_id'))::bigint`
   with
   `(nullif(current_setting('app.current_telegram_id', true), ''))::bigint`
   and have the app set `app.current_telegram_id` per session
   (`SET app.current_telegram_id = '<id>'`). Unset means NULL means
   no rows — the same safe default the design doc states.
   Do NOT relax these to "authenticated can read all".
3. **`service_role` bypasses RLS in Supabase but NOT in plain PG.**
   In plain PG the table owner bypasses RLS by default; other roles do
   not. Adaptation: run the apply + the bot/dashboard connections as
   the table owner (the `postgres` superuser or a dedicated
   `gold_council_app` owner role), OR `ALTER ROLE gold_council_app
   BYPASSRLS` — pick one and record it here when applied. Until the
   WebApp exists, all access is owner/app-role only.
4. **`gen_random_uuid()` is fine.** It is a core function since PG 13;
   no `pgcrypto` extension is needed on PG 17, despite the comment
   in `schema.sql` (line ~29) mentioning pgcrypto.
5. **No trading hooks.** grep found no `execute_trade`, `place_order`,
   or Pocket Option references in the schema. Clean.

## Applied — 2026-11-12 ~03:33 EET (trust window, as postgres superuser)

- `schema-local.sql` created from `schema.sql` (source UNCHANGED) =
  schema.sql + CREATE ROLE authenticated/service_role/anon NOLOGIN +
  the 5 `auth.jwt()` policies replaced with
  `(nullif(current_setting('app.current_telegram_id', true), ''))::bigint`.
  Copies: `design/supabase/schema-local.sql` on the VM and on Narmer.
- Owner approach chosen: apply + all access as the postgres superuser
  (table owner, bypasses RLS by default). No dedicated app role created
  yet; no BYPASSRLS grant needed.
- Apply: `psql -d gold_council -v ON_ERROR_STOP=1 -f schema-local.sql`
  exit 0, no errors. Verified: **16 tables** in public (exact expected
  names), **RLS enabled on all 16**, **24 policies**, **faq active = 7**.
- `psycopg[binary]` 3.3.8 installed in the Narmer venv (import verified).
- Migration (`scripts/migrate-sqlite-to-supabase.py`, --dry-run first,
  then committed): signals **6**, agent_votes **150** (6 signals × 25
  agents), subscribers **0**, payments **0**, subscriber_signals **0**,
  admin_audit **204** (203 + 1 login_attempts row), processed_updates
  **0**, learned_weights_history **25**. All counts matched source.
  Spot-check: entries 4059.96 (2026-11-06) and 4044.24 (2026-11-11),
  30 degraded votes, 5 positive weights — matches the known history.
  SQLite sources were not modified.

## What was NOT done (still open)

- No `pg_hba.conf` change remains (restored + verified), no password
  reset, no password read from any config file (the LiteLLM proxy's DB
  credential was NOT opened).
- No Docker, no Supabase CLI, no Redis, no Qdrant installed.
