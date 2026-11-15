-- Gold Council — migration 0003: bot_state + admin_rate (GitHub Actions hosting).
-- Applied to the Gold Council project xxbtrtdjijrhmcbzmxxm ONLY.
-- Never apply to the Eye of Justice project.
--
-- bot_state: key/value runtime state that used to live in files on the bot
-- host (bot_config.json mode/reviewed_count, telegram_bot/.offset).
-- On GitHub Actions every run starts from a clean checkout, so this state
-- must live in Postgres.
-- admin_rate: the 20-actions/minute admin rate-limit window. The original
-- schema has no counterpart (documented as ephemeral); on Actions there is
-- no SQLite at all, so it lives here.
CREATE TABLE IF NOT EXISTS bot_state (
  key text PRIMARY KEY,
  value text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bot_state (key, value) VALUES
  ('mode', 'review'),
  ('reviewed_count', '0'),
  ('poll_offset', '0')
ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS admin_rate (
  admin_chat_id bigint NOT NULL,
  ts timestamptz NOT NULL,
  PRIMARY KEY (admin_chat_id, ts)
);

CREATE INDEX IF NOT EXISTS admin_rate_ts_idx ON admin_rate (admin_chat_id, ts DESC);
