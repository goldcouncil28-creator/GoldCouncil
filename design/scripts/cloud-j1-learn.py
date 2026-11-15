#!/usr/bin/env python3
"""Cloud J1 learning step for Gold Council (Supabase, VM/cloud only).

Reads the live journal from the Gold Council Supabase project and computes,
from REAL settled data only:

  * per-direction win rate / avg R from closed signals (J1's input), and
  * per-agent R-expectancy with the E2 v2 formula (see system/patterns/
    optimizer.py): each non-zero vote is scored as a trade in the agent's
    own voted direction against the real settlement pnl_r, confidence-
    weighted, then shrunk toward zero:  score * n / (n + 20).
    Weights are the shrunk scores normalised by the mean of the positive
    shrunk scores (positive only, like E2); non-positive -> 0.

Writes ONE row per voting agent into learned_weights_history with
run_kind='live'. History is append-only: a re-run never updates or deletes
existing rows. A re-run with no new settlements since the last live run is
skipped (guarded by a settlement fingerprint stored in the notes); after
future settlements it appends a fresh run.

Safety:
  * NEVER touches Narmer (no SSH, no local files). Supabase only.
  * NEVER touches the Eye of Justice project (ref cbnxemyjzyzgrqaqrkhk).
    The project ref is asserted before connecting.
  * The DB password is read from ~/workspace/goals/goal/.cloud-credentials
    and is never printed, logged or pasted anywhere.
  * Read-only until the single INSERT transaction at the end; the whole
    run commits atomically or not at all.

Usage:
  ~/workspace/goals/goal/system/venv/bin/python design/scripts/cloud-j1-learn.py [--dry-run] [--force]
"""
import argparse
import math
import os
import statistics
import sys
from pathlib import Path

CREDS_FILE = Path.home() / "workspace" / "goals" / "goal" / ".cloud-credentials"
EXPECTED_REF = "xxbtrtdjijrhmcbzmxxm"
DB_HOST = f"db.{EXPECTED_REF}.supabase.co"
DB_PORT = 5432
DB_USER = "postgres"
DB_NAME = "postgres"

SHRINK_K = 20  # E2 v2 shrinkage constant

DIR_VALUE = {"long": 1, "short": -1}


def load_creds(path: Path) -> dict:
    creds = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        creds[k.strip()] = v
    return creds


def t_stat(values):
    """One-sample t-statistic of a list of per-signal R outcomes.

    Returns None when undefined (n < 2, or zero variance).
    """
    n = len(values)
    if n < 2:
        return None
    mean = statistics.fmean(values)
    sd = statistics.stdev(values)  # sample std, n-1
    if sd == 0:
        return None
    return mean / (sd / math.sqrt(n))


def main() -> int:
    ap = argparse.ArgumentParser(description="Cloud J1 learning step (Supabase).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and print only; do not insert.")
    ap.add_argument("--force", action="store_true",
                    help="Insert even if no new settlements since the last live run.")
    ap.add_argument("--creds-file", default=str(CREDS_FILE))
    args = ap.parse_args()

    creds = load_creds(Path(args.creds_file))
    ref = creds.get("SUPABASE_REF", "")
    if ref != EXPECTED_REF:
        print(f"ABORT: SUPABASE_REF is not the Gold Council project "
              f"(got {ref!r}, expected {EXPECTED_REF!r}). Refusing to run.",
              file=sys.stderr)
        return 2
    password = creds.get("SUPABASE_DB_PASSWORD", "")
    if not password:
        print("ABORT: SUPABASE_DB_PASSWORD missing from creds file.",
              file=sys.stderr)
        return 2

    import psycopg

    with psycopg.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                         user=DB_USER, password=password,
                         sslmode="require", connect_timeout=30) as conn:
        with conn.cursor() as cur:
            # ---- read-only phase -------------------------------------
            cur.execute("""
                SELECT s.id, s.direction, s.status, st.outcome, st.pnl_r,
                       st.settled_at
                  FROM signals s
                  JOIN settlements st ON st.signal_id = s.id
                 ORDER BY s.id
            """)
            settled = cur.fetchall()  # (id, direction, status, outcome, pnl_r, settled_at)

            cur.execute("""
                SELECT v.agent, v.vote, v.confidence, s.direction, st.pnl_r
                  FROM agent_votes v
                  JOIN signals s ON s.id = v.signal_id
                  JOIN settlements st ON st.signal_id = s.id
                 ORDER BY v.agent, v.signal_id
            """)
            votes = cur.fetchall()  # (agent, vote, confidence, direction, pnl_r)

            cur.execute("""
                SELECT DISTINCT agent FROM agent_votes ORDER BY agent
            """)
            agents = [row[0] for row in cur.fetchall()]

            cur.execute("""
                SELECT run_at, notes FROM learned_weights_history
                 WHERE run_kind = 'live'
                 ORDER BY run_at DESC, id DESC LIMIT 1
            """)
            last_live = cur.fetchone()

        # ---- per-direction stats (closed signals only) --------------
        dir_stats = {}
        for (_sid, direction, _status, _outcome, pnl_r, _ts) in settled:
            d = dir_stats.setdefault(direction, {"n": 0, "wins": 0, "total_r": 0.0})
            d["n"] += 1
            d["total_r"] += float(pnl_r)
            if float(pnl_r) > 0:
                d["wins"] += 1
        for d in dir_stats.values():
            d["losses"] = d["n"] - d["wins"]
            d["win_rate"] = 100.0 * d["wins"] / d["n"] if d["n"] else 0.0
            d["avg_r"] = d["total_r"] / d["n"] if d["n"] else 0.0

        pnl_series = [float(row[4]) for row in settled]
        strategy_t = t_stat(pnl_series)
        n_settled = len(settled)
        max_settled_at = max((row[5] for row in settled), default=None)
        fingerprint = f"n_settled={n_settled} max_settled_at={max_settled_at}"

        # ---- per-agent R-expectancy (E2 v2, real settlements) --------
        # An agent's trade is its own voted direction. With the signal
        # direction it earns pnl_r; against it it earns -pnl_r.
        # Each outcome is confidence-weighted, like E2.
        by_agent = {a: [] for a in agents}
        for (agent, vote, confidence, direction, pnl_r) in votes:
            if vote == 0:
                continue  # abstention is not a trade (E2: col[col != 0])
            sig_dir = DIR_VALUE[direction]
            r = float(pnl_r) if vote == sig_dir else -float(pnl_r)
            by_agent[agent].append(r * (float(confidence) / 100.0))

        raw, shrunk = {}, {}
        for agent, contribs in by_agent.items():
            n = len(contribs)
            if n == 0:
                raw[agent] = 0.0
                shrunk[agent] = 0.0
            else:
                mean_r = sum(contribs) / n
                raw[agent] = mean_r
                shrunk[agent] = mean_r * (n / (n + SHRINK_K))

        positives = [v for v in shrunk.values() if v > 0]
        mean_pos = sum(positives) / len(positives) if positives else 0.0
        weights = {a: (round(shrunk[a] / mean_pos, 4) if shrunk[a] > 0 and mean_pos else 0.0)
                   for a in agents}

        dir_summary = "; ".join(
            f"{d}: {s['n']} settled, {s['wins']}W/{s['losses']}L, "
            f"win rate {s['win_rate']:.1f}%, avg {s['avg_r']:+.4f}R"
            for d, s in sorted(dir_stats.items())
        )
        run_note = (
            f"live E2 v2 (R-expectancy, shrinkage n/(n+{SHRINK_K}), "
            f"conf-weighted). {dir_summary}. "
            f"Strategy t-stat {strategy_t:+.2f} (n={n_settled}). "
            f"Sample tiny (n={n_settled}) - no edge proven; weights are "
            f"descriptive only, not a trading signal. [{fingerprint}]"
        )

        # ---- report to stdout (no secrets) ---------------------------
        print(f"Settled signals: {n_settled} (fingerprint: {fingerprint})")
        for d, s in sorted(dir_stats.items()):
            print(f"  {d}: {s['n']} settled, {s['wins']}W/{s['losses']}L, "
                  f"win rate {s['win_rate']:.1f}%, avg {s['avg_r']:+.4f}R, "
                  f"total {s['total_r']:+.4f}R")
        print(f"  strategy t-stat: {strategy_t:+.4f} (n={n_settled})")
        print("Per-agent shrunk R-expectancy (top 5 / bottom 5):")
        ranked = sorted(agents, key=lambda a: shrunk[a], reverse=True)
        for a in ranked[:5] + ranked[-5:]:
            n = len(by_agent[a])
            t = t_stat(by_agent[a])
            t_s = f"{t:+.2f}" if t is not None else "n/a"
            print(f"  {a}: n={n} raw {raw[a]:+.4f}R shrunk {shrunk[a]:+.4f}R "
                  f"weight {weights[a]:.4f} t={t_s}")

        if args.dry_run:
            print("DRY RUN - nothing inserted.")
            return 0

        # ---- re-run guard --------------------------------------------
        if last_live and not args.force:
            _run_at, last_notes = last_live
            if fingerprint in (last_notes or ""):
                print(f"No new settlements since last live run "
                      f"({last_live[0]}). Skipping insert "
                      f"(use --force to record anyway).")
                return 0

        # ---- write phase: one transaction, append-only ----------------
        run_at = None
        with psycopg.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
                             user=DB_USER, password=password,
                             sslmode="require", connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT now()")
                run_at = cur.fetchone()[0]
                rows = []
                for agent in agents:
                    contribs = by_agent[agent]
                    n = len(contribs)
                    t = t_stat(contribs)
                    note = (f"{run_note} Agent {agent}: n={n}, "
                            f"raw {raw[agent]:+.4f}R, "
                            f"shrunk {shrunk[agent]:+.4f}R.")
                    rows.append((run_at, "live", agent, weights[agent],
                                 round(shrunk[agent], 4), n,
                                 round(t, 4) if t is not None else None,
                                 note))
                cur.executemany("""
                    INSERT INTO learned_weights_history
                        (run_at, run_kind, agent, weight,
                         r_expectancy, sample_n, t_stat, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, rows)
            conn.commit()
        print(f"Inserted {len(rows)} live rows (run_at={run_at}). "
              f"History untouched otherwise.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
