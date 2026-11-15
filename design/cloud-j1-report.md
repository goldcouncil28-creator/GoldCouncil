# Cloud J1 learning report — live run #1 (Supabase)

**Run:** `run_kind='live'`, `run_at` 2026-11-15 21:11:30 UTC (23:11:30 EET), 25 rows
(one per voting agent) in `learned_weights_history`.
**Script:** `design/scripts/cloud-j1-learn.py`
(`--dry-run` to preview, `--force` to record a run even with no new settlements;
a plain re-run is skipped when no new settlements exist since the last live run).
**Source:** Gold Council Supabase project only (ref `xxbtrtdjijrhmcbzmxxm`).
No Narmer access, no Eye of Justice data, no invented data.

## Data the run learned from

- **Signals:** 13 rows (pg ids 14–26). **All 13 are SELL (short).**
- **Settled:** 12 (ids 14–25). **Signal 26 (journal #13) is `expired` with no
  settlement row and is excluded** — an expired signal has no result to learn from.
- **Settlements:** 6× TP1 wins (+1.499R ×3, +1.500R ×3) and 6× SL losses (−1.000R ×6).
- **Votes:** 325 rows (25 agents × 13 signals). On settled signals only 63
  non-zero votes: 57 with the signal, 6 against, 262 abstentions (vote 0).
  13 of the 25 agents abstained on **all** 12 settled signals (the whole C-layer
  C1–C7 — degraded, awaiting the 3a2l proxy — plus S2, S3a, S6, S10, S11, X1).

## Per-direction results (J1's headline input)

| Direction | Settled | Wins | Losses | Win rate | Avg R | Total R |
|-----------|--------:|-----:|-------:|---------:|------:|--------:|
| short     | 12 | 6 | 6 | **50.0%** | **+0.2498R** | +2.997R |
| long      | 0 | 0 | 0 | — (no long signals yet) | — | — |

**Strategy t-stat: +0.66 (n = 12). Not significant.** The walk-forward verdict
(t-stat +0.75) is unchanged in substance: **no proven edge.**

## Per-agent R-expectancy (E2 v2, real settlements)

Method: an agent's trade is its own voted direction. With the signal direction
it earns the settlement `pnl_r`; against it, `−pnl_r`. Each outcome is
confidence-weighted (like E2), averaged over its non-zero votes (`raw`), then
shrunk: `shrunk = raw × n / (n + 20)`. Weights are the shrunk scores normalised
by the mean of the positive shrunk scores (positive only; the rest get 0).
`t_stat` is the one-sample t of the agent's per-signal R outcomes; `n/a`
(NULL) means undefined — fewer than 2 votes, or zero variance (all identical
outcomes).

| Agent | n | Raw R | Shrunk R | Weight | t-stat |
|-------|---:|------:|---------:|-------:|-------:|
| S4a | 3 | +1.0493 | **+0.1369** | 1.8816 | n/a |
| X2 | 6 | +0.3250 | **+0.0750** | 1.0311 | +0.71 |
| X3 | 6 | +0.3250 | **+0.0750** | 1.0311 | +0.71 |
| S3b | 12 | +0.1698 | **+0.0637** | 0.8755 | +0.66 |
| S5b | 6 | +0.2175 | **+0.0502** | 0.6900 | +0.45 |
| S13 | 6 | +0.1547 | **+0.0357** | 0.4908 | +0.45 |
| S1 | 6 | −0.1500 | −0.0346 | 0.0000 | −0.45 |
| S5a | 3 | −0.5400 | −0.0704 | 0.0000 | n/a |
| S5c | 3 | −0.6000 | −0.0783 | 0.0000 | n/a |
| S4c | 3 | −0.6200 | −0.0809 | 0.0000 | n/a |
| S4b | 3 | −0.6500 | −0.0848 | 0.0000 | n/a |
| S12 | 3 | −0.6500 | −0.0848 | 0.0000 | n/a |
| C1, C2, C3, C4, C5, C6, C7, S2, S3a, S6, S10, S11, X1 | 0 | 0.0000 | 0.0000 | 0.0000 | n/a |

**Top 3 by shrunk R-expectancy:** S4a (+0.1369R, n=3), X2 (+0.0750R, n=6),
X3 (+0.0750R, n=6).
**Bottom 3:** S12 (−0.0848R, n=3), S4b (−0.0848R, n=3), S4c (−0.0809R, n=3).

## Honest caveats — read before using any number here

1. **The sample is tiny (12 settled signals).** Nothing here is statistically
   significant: the best agent t-stat is +0.71, the strategy t-stat +0.66.
2. **S4a's lead rests on 3 votes** — three wins at ~70% confidence. The
   shrinkage already cut its raw +1.049R down to +0.137R, and it still cannot
   be trusted at n=3. Do not raise S4a's weight on this.
3. **The live ranking contradicts the walk-forward ranking, as noise does:**
   walk-forward (hundreds of samples) had X3/S5b/S5c positive and S4a negative
   (−0.060R, n=585); this live run has S4a on top and S5c negative (n=3).
   The walk-forward weights remain the ones to trust until the live sample grows.
4. **X2 and X3 have identical numbers** (same 6 votes, same confidences).
   They are correlated L3 execution agents — a candidate `correlates` edge for
   `agent_links` so M1 does not double-count them (design: schema §3).
5. **S3b is the only agent with a full live sample (n=12)** — it voted on every
   settled signal, all with the signal direction, shrunk +0.0637R, t=+0.66.
6. **These weights are descriptive, not a trading signal.** They describe 12
   paper signals. No auto-trading, no live use, no weight change in the bot
   follows from this run.

## Verification (independent, via psql)

- `learned_weights_history`: 50 rows total — 25 walk-forward (seeded) + 25 live.
  **The 25 walk-forward rows are byte-identical to the pre-run snapshot**
  (X3 1.672/0.096/622, S5b 1.23/0.071/521, S5c 0.902/0.052/616,
  S4b 0.672/0.039/165, X2 0.524/0.030/363, rest 0) — untouched.
- **Per-direction recomputed by hand in SQL:** short 12, 6W, 50.0%,
  avg +0.2498R — matches the script.
- **Agent R-expectancy recomputed by hand in SQL** (independent aggregation):
  S4a raw 1.0493 / shrunk 0.1369; X2 0.3250 / 0.0750; X3 0.3250 / 0.0750;
  S3b 0.1698 / 0.0637; S5b 0.2175 / 0.0502; S4b −0.6500 / −0.0848;
  S12 −0.6500 / −0.0848 — all match the stored live rows exactly.
- **Other tables unchanged:** signals 13, agent_votes 325, settlements 12.
- **Re-run guard verified:** running the script a second time detected no new
  settlements and skipped the insert (no duplicate run rows).
- Each live row's `notes` carries the method, the per-direction summary, the
  strategy t-stat, the "sample tiny — no edge proven" caveat, the settlement
  fingerprint (`n_settled=12 max_settled_at=2026-11-15 16:06:07.452748+00:00`),
  and the agent's own n/raw/shrunk.

## Next run

Re-run `cloud-j1-learn.py` after future signals settle (it appends a new live
run; history is never overwritten). The numbers only start to mean something
after dozens of settled signals — and only for the agents that actually vote.
