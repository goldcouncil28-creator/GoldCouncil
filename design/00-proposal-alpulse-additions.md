# Gold Council — AlPulse additions proposal (DESIGN ONLY)

**Date:** 2026-11-11
**Status:** Design package — no build, no deploy, no Narmer access, no schema applied.
**Staging:** `~/workspace/goals/goal/design/` → later `D:\Project\Trade` on Narmer, only after Mohamed's explicit «نفذ» for build.
**Source material:** 12 inside-app AlPulse screenshots (`~/workspace/user/media_library/image/photo_2026-11-11_*.jpg`) + /start screenshot + onboarding drip, analysed 2026-11-11 22:17 EET.

## HARD RULES (Mohamed, 2026-11-11 22:22 EET — non-negotiable)

- **NO auto-trading ever.** Gold Council gives documented recommendations only, never executes trades.
- **No Pocket Option integration anywhere** — no account creation, no deposit link, no broker password storage, no broker-deposit referral.
- **No fake numbers, no unverified profit/user claims.** Paper labelled paper. Losers shown. Honest journal.
- **Signal cap 3/day — ceiling, not quota.** No invented signals to fill the cap.
- **Review mode first; auto only after ~30 reviewed signals.**
- **No build without a separate explicit «نفذ»** after this design is reviewed.

## What AlPulse actually is (verified from screenshots)

AI PULSE (`@AlPulse_app_bot`) is an **automated binary-options trading bot on Pocket Option, NOT a signals bot**. Its core flow:

1. Choose a currency pair → 2. Choose expiry → 3. Tap "Get signal" → 4. Check trend strength → 5. Take if strong / skip if weak.
2. Signals are **locked behind "راسل مديرك الشخصي"** (a human manager must activate them).
3. Auto-trading is **locked behind registration**, demo $10,000, "Smart Control" locked.
4. The welcome says the AI "finds, opens and closes trades itself on Pocket Option — no experience, charts or time needed" — a promise Gold Council will never make.

Claims seen in-app, **unverified, treat as marketing only**:
- "42,250 monthly users" in-bot (web directory said 14,314 — unstable across sources).
- "AI GPT5.4 | Trading" / CopyGPT AI SIGNALS — "GPT 5.4" is a marketing label, not a verified model name.
- "+15,000 in channel", "+$46.00" phone photo, "محمد من حلب ربح 904$ من 24 إشارة", "ياسمين من بريدة فاز بـ 18 إشارة على التوالي", plus rotating ticker names (ليلي XAG/USD, سارة EUR/CHF, هدى EUR/AUD, نور EUR/NZD OTC, USD/DZD OTC).
- None of these are verified results and none may be copied or reworded into Gold Council.

## AlPulse WebApp structure (from the 12 screenshots)

Bottom nav, 5 tabs:

| Tab | What it contains (AlPulse) |
|---|---|
| الملف الشخصي (Profile) | Dr Robot @Dr_Robot_Eg, Telegram ID 2122313931, stats all 0 (signals 0, streak 0, invited 0), "Pocket Option — متوقف — اضغط لربط حسابك", top-up via Pocket Option deposit, الإعدادات |
| الدعم (Support) | "تحدث مع شخص حقيقي" (Telegram DM), قناة المجتمع, FAQ (7 questions, collapsed), binary-options risk disclaimer ("no financial advice") |
| الإشارات + التداول الآلي (centre) | Two-toggle: الإشارات / التداول الآلي. Signals locked behind personal manager. Auto-trading locked behind registration, demo $10,000 |
| مساعد الذكاء الاصطناعي | "Alex" chat: "مرحبا Dr! أنا Alex … أتريد نظرة سريعة على كيفية الحصول على إشارة رابحة، أم تفضل أن تسأل شيئا أولا؟" — buttons "أرني كيف / لدي سؤال" |
| اكسب XP (Referral) | Invite link `https://t.me/AlPulse_app_bot?start=ref_2122313931`, invited 0, earned 0 EGP / $0. Tiers on the referred user's Pocket Option deposit: $15–$49 → 275 EGP ($5); $50–$99 → 550 EGP ($10); $100–$300 → 800 EGP ($15); +$300 → 1,100 EGP ($20). Rules: register via link + first deposit ≥ $15 + trade on Pocket Option; no self/multi accounts |

Other in-app elements:
- **Pocket Option signup modal inside the WebApp:** email field + auto-generated password "saved in your profile". (Security risk — rejected, see below.)
- **"How to get a signal" modal:** 6 steps in English (choose pair, choose expiry, tap "Get signal", check trend strength, take if strong, skip if weak).
- **Onboarding drip (from bot chat, no WebApp):** after /start with no interaction — ~21 min: free auto-trading reminder + "افتح التطبيق"; ~60 min: "+15,000 in channel" + "شاهد القناة وابدأ".
- **FAQ list (Support tab):** كيف أحصل على إشارة؟ / ماذا تعني قوة الاتجاه؟ / كيف يولد الذكاء الاصطناعي الإشارات؟ / لماذا علي التسجيل عبر رابطكم؟ / هل الإشارات مجانية حقا؟ / هل يمكنك التداول نيابة عني؟ / ماذا لو كان لدي حساب Pocket Option مسبقا؟

## Feature mapping: AlPulse vs Gold Council today

| # | AlPulse feature | Gold Council today | Verdict |
|---|---|---|---|
| 1 | Telegram WebApp (5 tabs) | No WebApp. Bot commands + /admin panel + FastAPI dashboard (127.0.0.1:8100, Telegram-only control chosen 2026-11-06) | **BORROW — item 1.** WebApp for signals / stats / profile. Must be read-only recommendations, never trading. |
| 2 | Profile stats: signals / streak / invited | `/stats` + `/history` exist (closed trades, win rate, per-subscriber journal). No streak, no invited count | **BORROW — item 2.** Progress tracking: streak, signals count, win rate. Extension of /stats. |
| 3 | Signals: binary options, direction + expiry, trend strength, locked behind manager | XAUUSD signals with entry / SL / TP1 / TP2 / confidence / H1 chart + analysis, review mode, 3/day cap, paper journal | **DO NOT COPY the model.** Ours is stronger (price, risk, documented journal). Borrow only the *presentation* idea: a clean per-signal card inside the WebApp. Never gate signals behind a manager upsell. |
| 4 | Auto-trading (demo $10,000, Smart Control) | None — by design | **REJECTED — hard rule.** No auto-trading ever. No demo-trading execution either. |
| 5 | AI assistant "Alex" chat | None. C2/C3 LLM stubs abstain without 3a2l; M3 narrative is internal only | **BORROW, phase 2 — item 7.** Smart assistant about *our* signals (explain a card, explain /stats, FAQ answers). Needs 3a2l LLM routing. Outline only in this package. |
| 6 | Referral / XP on broker deposits (EGP tiers) | None. Payment is manual via Mohamed; invite links are per-subscriber channel invites (member_limit=1) | **REJECTED as designed. BORROW the pattern — item 6.** Referral for Gold Council itself: invite → reward days on activation. No broker, no deposit, no cash. See `workflows/referral.json`. |
| 7 | Support: FAQ + human support + community channel | Discussion supergroup -1004446157966 exists. No in-bot FAQ. Support = Mohamed directly (@Dr_Robot_Eg) | **BORROW — item 3.** FAQ + in-bot support (link to discussion group + contact Mohamed). |
| 8 | Onboarding drip (2 messages) | No drip. /start welcome only | **BORROW — item 4.** Welcome drip: paper-mode reminder, /stats explainer, discussion-group invite. See `workflows/welcome-drip.json`. No profit promises, no fake numbers. |
| 9 | 1-min intro video | Landing page only (artifact `mjls-ldhhb-gold-council`) | **BORROW — item 5.** Script/outline only in this package. No video generation in design phase. |
| 10 | Pocket Option signup modal (email + auto password) | None | **REJECTED.** Broker account creation + password storage inside our product is a security risk and off-mission. |
| 11 | Rotating social-proof ticker (+$904, 18-in-a-row, +15,000) | Honest empty-state journal; documented backtests with non-significance caveat (t-stat +0.75) | **REJECTED.** No unverified social proof, ever. Our journal shows real closed trades only, losers included. |
| 12 | "GPT 5.4" ad / CopyGPT | None | **REJECTED.** Marketing label, not a verified model. We name real models / abstain when the LLM is unavailable. |
| 13 | Signals locked behind manager contact | Review mode: admin (Mohamed) approves each signal before publish; /pending queue | **Ours is different and stays.** Admin review is a quality gate, not an upsell gate. No change. |

## What Gold Council has that AlPulse does not (keep — do not dilute)

- Real entry / SL / TP1 / TP2 / confidence / R:R on every card, plus an H1 chart with the levels drawn.
- 35-agent analysis (R0, N0, R1, R2, C1–C7, S1–S13, X1–X3, M1, M2, M3, E1, E2, J1) with a recorded vote per agent — see `supabase/schema.sql` (`agent_votes`, `agent_links`, `evaluations`, `corrections`).
- Human review queue, idempotent poll dedup (`processed_updates`, last 2,000 update_ids), admin audit log, 20/min admin rate limit.
- Per-subscriber journal with self-entry ("دخلت"), /stats, /history, payments ledger, expiry + 3-day warning.
- Documented backtests with the non-significance caveat stated in public. Strategy has **no proven edge yet** (walk-forward OOS +$990.87, +9.9%, 45.1% win, +0.061R/trade, t-stat +0.75). Nothing in this package changes that fact or hides it.

## Approved 8-item scope (Mohamed, 2026-11-11 22:22 EET)

1. **Telegram WebApp** — signals / stats / profile. Read-only recommendations; no trading actions in the UI.
2. **Progress tracking** — streak, signals count, win rate. Extension of existing /stats. Source of truth: `progress` + `settlements` tables.
3. **FAQ + in-bot support** — link to discussion group -1004446157966 + contact Mohamed. FAQ content is drafted from Gold Council's real rules (paper, 3/day cap, review mode), not copied from AlPulse's binary-options FAQ.
4. **Welcome drip sequence** — paper-mode reminder, /stats explainer, discussion-group invite. Timed, stops on interaction.
5. **1-min intro video** — script/outline only (in §Phases below). No generation in design phase.
6. **Referral system for Gold Council itself** — invite → reward days, manual-payment compatible. NOT a broker. Anti-abuse built in.
7. **Smart assistant about our signals** — phase 2, needs 3a2l LLM routing. Outline only.
8. **Supabase + learning DB** — schema + workflow JSON + arch + Mermaid. Design first, build after a separate «نفذ».

## Phases (design → build, each needs its own «نفذ»)

- **Phase A — Design (this package).** Proposal + `schema.sql` + 3 workflow JSONs + `arch.md` + `D:\Project\Trade` structure. Staged on the VM at `~/workspace/goals/goal/design/`.
- **Phase B — Supabase + learning DB.** Create a NEW separate Gold Council Supabase project (never the Eye of Justice project `cbnxemyjzyzgrqaqrkhk`). Apply `schema.sql` via Management API / psql. Migrate SQLite (`subs.db`, `journal.db`) → Supabase, keeping SQLite as a local fallback until migration is verified. Build the E2 learning loop on `learned_weights_history` + `agent_votes` + `settlements`.
- **Phase C — WebApp (signals / stats / profile).** Static WebApp served from the existing FastAPI dashboard host or a new static host; Telegram `WebApp` button; auth via Telegram `initData` validation (no passwords). Read-only.
- **Phase D — Drip + FAQ + progress.** Welcome drip (`welcome-drip.json`), FAQ table + /faq command, progress tracking in /stats and WebApp.
- **Phase E — Referral.** `referral.json` implemented against `referrals` table; reward days applied on manual-payment activation by Mohamed.
- **Phase F — Smart assistant (phase 2).** 3a2l LLM routing for C2/C3 first; assistant answers only from our journal + signal cards + FAQ, with abstention when data is missing.
- **Phase G — Narmer move.** Copy the staged project to `D:\Project\Trade`, replace VM crons with Windows Scheduled Tasks, switch Narmer from on-demand to always-on — only on Mohamed's explicit decision (see `D-Project-Trade-structure.md`).

## Explicitly NOT copied (so there is no ambiguity later)

Auto-trading in any form; Pocket Option (account, deposit, link, password, referral tiers); binary-options signals (direction + expiry only); "no experience / no charts / no time" promises; "GPT 5.4"; "+15,000 in channel"; "+$46.00"; "$904 from 24 signals"; "18 signals in a row"; any rotating social-proof ticker; signals locked behind a manager upsell; storing broker passwords; any unverified user/profit count.

## Open questions for Mohamed (before Phase B)

1. New Supabase project: will he create it, or should B propose the project name and he creates it? Ref/URL + secret come via the secure vault card, never in chat. The 2026-11-06 key was never stored and must not be reused without its project ref.
2. Qdrant: reuse the existing (Eye of Justice) cluster with new Gold Council collections, or a new cluster? (Design in `arch.md` assumes new collections on the existing cluster, clearly namespaced.)
3. Redis: local on Narmer (Docker) or a cloud Redis? No Redis connector exists today.
4. Narmer: switch from on-demand (Tailscale/sshd Manual) to always-on for live execution? This reverses his 2026-10-24 protection-only order and needs an explicit decision.
5. Referral reward: how many days per activated referral? (Design default: 7 days, configurable — see `workflows/referral.json`.)
6. Intro video: who records the voiceover — Mohamed, or a script for a narrator? (Script outline is in §Phases / `arch.md`.)
