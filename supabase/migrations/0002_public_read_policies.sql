-- 0002_public_read_policies.sql — Gold Council Supabase project ONLY.
-- Applied 2026-11-15 via psql (postgres user, direct connection).
-- Purpose: let the public website read the journal with the PUBLISHABLE
-- (anon) key. The schema (0001 / design/supabase/schema.sql) grants anon
-- NOTHING, so without these policies the site could not read even the
-- public FAQ. These policies match the schema's own stated intent:
-- "the journal is public by design ... only published signals are exposed
-- — pending/review rows stay service-only."
--
-- Scope (read-only, SELECT only):
--   anon SELECT signals     WHERE review_status = 'published'
--   anon SELECT settlements WHERE the signal is published
--   anon SELECT faq         WHERE is_active = true
-- No writes, no other tables, no subscriber/vote/payment data exposed.
--
-- Verified after applying (2026-11-15, REST probe):
--   anon faq = 7 rows, anon signals = 0, anon settlements = 0
--   (0 rows is correct: no published signals exist yet — the Narmer
--   migration has not run. The journal shows the honest empty state
--   until the first published signal lands.)
--   pg_policies confirms the three policies with the predicates below.

DO $$
BEGIN
  CREATE POLICY "anon_read_published_signals" ON public.signals
    FOR SELECT TO anon USING (review_status = 'published');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE POLICY "anon_read_published_settlements" ON public.settlements
    FOR SELECT TO anon USING (
      EXISTS (SELECT 1 FROM public.signals s
              WHERE s.id = settlements.signal_id
                AND s.review_status = 'published')
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  CREATE POLICY "anon_read_active_faq" ON public.faq
    FOR SELECT TO anon USING (is_active = true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
