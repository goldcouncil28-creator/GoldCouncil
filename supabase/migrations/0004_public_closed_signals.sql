-- 0004_public_closed_signals.sql — Gold Council Supabase project ONLY.
-- Applied 2026-11-16 via psycopg (postgres user, direct connection).
-- Purpose: the public website journal must show the REAL paper record,
-- not only published signals. Until now the journal was 0/0/0 because no
-- signal was ever published (12 rejected + 1 expired-pending), even
-- though 12 real paper signals settled (6W/6L over 5 distinct setups).
-- Mohamed's decision 2026-11-16 («نفذ الصح والافضل»): show ALL closed
-- paper signals, labeled paper — an empty journal looks dead, the real
-- record (wins AND losses) is the credibility. The paper-phase label on
-- the site stays; nothing here claims real money.
--
-- Scope (read-only, SELECT only, ADDITIVE — 0002 policies are KEPT):
--   anon SELECT signals     WHERE status IN ('tp1','tp2','sl','expired')
--   anon SELECT settlements WHERE the signal is closed (same list)
-- Open/pending signals stay service-only (no live setup is exposed
-- before it settles). No writes, no other tables, no subscriber/vote/
-- payment data exposed. A closed signal row includes votes_json (the
-- 25 agents' votes) — that is the public transparency the journal is
-- for; agent_votes table itself stays service-only.
--
-- Expected after applying (anon REST probe):
--   anon signals (status closed) = 13 rows (12 settled + 1 expired)
--   anon settlements = 12 rows (expired has no settlement by design)
--   distinct setups = 5 → journal shows 5 closed, 2 wins, 2 losses,
--   win rate 50.0%, avg +0.25R.

DO $$
BEGIN
  CREATE POLICY "anon_read_closed_signals" ON public.signals
    FOR SELECT TO anon USING (status IN ('tp1', 'tp2', 'sl', 'expired'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE POLICY "anon_read_closed_settlements" ON public.settlements
    FOR SELECT TO anon USING (
      EXISTS (SELECT 1 FROM public.signals s
              WHERE s.id = settlements.signal_id
                AND s.status IN ('tp1', 'tp2', 'sl', 'expired'))
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
