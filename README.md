# Gold Council — Website

Public website for **Gold Council** (مجلس الذهب), Mohamed's paid Telegram
signals bot for XAUUSD. Arabic RTL, dark theme. No auto-trading, ever — the
bot gives documented recommendations only, never executes trades.

Founded by **[Mohamed Nagy](https://github.com/SeniorMohamed)** — Founder, Designer & Principal Developer.

## Live data — Supabase (read-only)

The site reads its numbers **live from Supabase** at page load (REST API,
publishable/anon key). There are no baked-in figures:

- `site/index.html` — public landing: journal stats + results table + FAQ.
- `site/webapp/` — Telegram WebApp (5 tabs: signals, profile, support,
  assistant, referral). Open it from inside `@GoldCouncil_bot`.
- `site/assets/supabase.js` — shared read-only client + the honest
  distinct-setup stats (`distinctStats`): signals are grouped by the full
  setup (symbol + direction + entry + stop + TP1 + TP2) and each distinct
  setup is counted **once** — never row counts.

**Current state (verified 2026-11-15):** Supabase has **0 signals, 0
settlements, 0 subscribers, 7 FAQ rows**. The site therefore honestly shows
"no settled signals yet" (paper phase) instead of invented figures. The
journal fills in automatically once the Narmer migration lands published
signals. The strategy has **no proven edge yet** (latest walk-forward
t-stat +0.75) — the site says so in the journal section.

### What the anon key can (and cannot) read

`supabase/migrations/0002_public_read_policies.sql` grants anon `SELECT`
only on **published** signals, their settlements, and **active** FAQ.
Pending/review rows, votes, subscribers, payments and referrals stay
service-only. The publishable key in `site/assets/supabase.js` is a
**public** client key by design; the service_role key is never in this repo.

## Structure

```
site/            # the website (landing + WebApp) — Cloudflare Pages output dir
design/          # design docs: architecture, migration plan, schema, workflows
system/          # the Python bot: 35 agents, pipeline, Telegram bot, dashboard, bot-server API
supabase/
  migrations/    # 0002 public-read policies (applied 2026-11-15)
wrangler.toml    # Cloudflare Pages config
```

## Local preview

```sh
cd site && python3 -m http.server 8080
# open http://127.0.0.1:8080/  (landing)
# open http://127.0.0.1:8080/webapp/  (WebApp)
```

## Deploy to Cloudflare Pages (one step, once the token + domain arrive)

```sh
wrangler pages deploy site --project-name gold-council
```

Then attach the custom domain **GoldCouncil.dev** in the Cloudflare dashboard
(Pages project → Custom domains). **Still needed — not in this repo:**
the Cloudflare API token. (Domain decided 2026-11-15: GoldCouncil.dev.)

## Honesty rules (non-negotiable)

- No fake data, ever. Paper is labelled paper; losers are shown.
- Journal stats count **distinct setups**, never rows.
- With 0 rows the site shows the empty state — never invented figures.
- No trading buttons, no broker links, no buy/sell/deposit actions anywhere.
