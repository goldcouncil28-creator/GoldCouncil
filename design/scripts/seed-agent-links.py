#!/usr/bin/env python3
"""Seed the Gold Council agent relationship graph into Supabase agent_links.

Idempotent: re-running updates existing edges (ON CONFLICT ... DO UPDATE).
Source of truth for the graph: design/agent-graph.md (derived from
system/pipeline.py, system/m1_arbiter.py, system/m2_risk.py,
system/patterns/{evaluator,optimizer}.py, agents/{r0,n0,r1,r2,m3,j1}.py
and design/arch.md).

Strengths are MANUAL design judgment (0..1), NOT measured values —
source='manual', sample_n=0 for every row. Measured per-agent performance
(E2 walk-forward R-expectancy) lives in learned_weights_history, not here.

Safety:
- Reads the DB password from ~/workspace/goals/goal/.cloud-credentials.
  NEVER prints, logs or pastes any secret.
- Asserts the target project ref is the Gold Council project
  (xxbtrtdjijrhmcbzmxxm) and refuses any other ref — in particular it
  will NEVER touch the Eye of Justice project (cbnxemyjzyzgrqaqrkhk).
- Direct Postgres only (host db.<ref>.supabase.co:5432, user postgres).

Usage:
    ~/workspace/goals/goal/system/venv/bin/python design/scripts/seed-agent-links.py
"""
import sys
from pathlib import Path

CREDS_FILE = Path.home() / "workspace" / "goals" / "goal" / ".cloud-credentials"
GOLD_COUNCIL_REF = "xxbtrtdjijrhmcbzmxxm"
FORBIDDEN_REF = "cbnxemyjzyzgrqaqrkhk"  # Eye of Justice — never touch

# (from_agent, to_agent, link_type, strength)
# strength = manual design judgment 0..1; see design/agent-graph.md for the
# reason behind each edge. 'settlements' is a data table, not an agent —
# it is the learning loop's data input into J1.
EDGES = [
    # ── L0 router sequence (feeds) — pipeline.py run_pipeline ──
    ("R1", "R0", "feeds", 0.9),   # symbol routing precedes regime classification
    ("R0", "N0", "feeds", 0.7),   # regime check precedes news check
    ("N0", "R2", "feeds", 0.7),   # news check precedes timeframe agreement

    # ── Gates (a gate can veto/block its target) ──
    ("R0", "M1", "gates", 1.0),   # allowed-list zeroes disallowed schools; shock = all zero
    ("N0", "M1", "gates", 0.9),   # news block aborts the whole pipeline before M1
    ("M3", "M1", "gates", 0.9),   # veto at 3+ structural attacks kills the verdict
    ("M2", "E1", "gates", 0.8),   # M2 returns None (invalid numbers) = veto; no card reaches E1

    # ── Context feeds into the judges ──
    ("R0", "E1", "feeds", 0.6),   # E1 scores regime fit (15/100)
    ("N0", "E1", "feeds", 0.6),   # E1 scores the news-free window (10/100)
    ("R0", "M3", "feeds", 0.5),   # M3 attacks a mixed regime
    ("R2", "M1", "feeds", 0.5),   # H1/H4 agreement is decision context (not an arbitrate() input yet)

    # ── L1 context agents -> M1 (feeds) ──
    ("C1", "M1", "feeds", 0.6),
    ("C2", "M1", "feeds", 0.6),
    ("C3", "M1", "feeds", 0.6),
    ("C4", "M1", "feeds", 0.6),
    ("C5", "M1", "feeds", 0.6),
    ("C6", "M1", "feeds", 0.6),
    ("C7", "M1", "feeds", 0.6),
    # ── L2 structure agents -> M1 (feeds) ──
    ("S1", "M1", "feeds", 0.8),
    ("S2", "M1", "feeds", 0.8),
    ("S3a", "M1", "feeds", 0.8),
    ("S3b", "M1", "feeds", 0.8),
    ("S4a", "M1", "feeds", 0.8),
    ("S4b", "M1", "feeds", 0.8),
    ("S4c", "M1", "feeds", 0.8),
    ("S5a", "M1", "feeds", 0.8),
    ("S5b", "M1", "feeds", 0.8),
    ("S5c", "M1", "feeds", 0.8),
    ("S6", "M1", "feeds", 0.8),
    ("S10", "M1", "feeds", 0.8),
    ("S11", "M1", "feeds", 0.8),
    ("S12", "M1", "feeds", 0.8),
    ("S13", "M1", "feeds", 0.8),
    # ── L3 order-flow proxies -> M1 (feeds) ──
    ("X1", "M1", "feeds", 0.7),
    ("X2", "M1", "feeds", 0.7),
    ("X3", "M1", "feeds", 0.7),

    # ── Review chain (feeds): M1 -> M3 -> M2 -> E1 ──
    ("M1", "M3", "feeds", 1.0),   # M3 challenges M1's verdict
    ("M3", "M2", "feeds", 0.9),   # challenged verdict (+challenge) flows to risk
    ("M2", "E1", "feeds", 1.0),   # E1 evaluates M2's card

    # ── S2 Fibonacci targets feed M2's TP2 ──
    ("S2", "M2", "feeds", 0.8),

    # ── Learning loop (feeds): settlements -> J1 -> E2 -> M1 ──
    ("settlements", "J1", "feeds", 0.9),  # J1 reads closed signals / settlements
    ("J1", "E2", "feeds", 0.9),           # per-direction win rates feed weight learning
    ("E2", "M1", "feeds", 1.0),           # learned weights are M1's weight input
    ("E2", "E1", "feeds", 0.5),           # E1 consensus excludes zero-weight agents

    # ── Same-family correlates (bidirectional; votes move together) ──
    # S4 structure schools: SMC / Wyckoff / Elliott
    ("S4a", "S4b", "correlates", 0.7), ("S4b", "S4a", "correlates", 0.7),
    ("S4a", "S4c", "correlates", 0.7), ("S4c", "S4a", "correlates", 0.7),
    ("S4b", "S4c", "correlates", 0.7), ("S4c", "S4b", "correlates", 0.7),
    # S5 indicator family: momentum / trend / volatility
    ("S5a", "S5b", "correlates", 0.7), ("S5b", "S5a", "correlates", 0.7),
    ("S5a", "S5c", "correlates", 0.7), ("S5c", "S5a", "correlates", 0.7),
    ("S5b", "S5c", "correlates", 0.7), ("S5c", "S5b", "correlates", 0.7),
    # X order-flow proxies: all three proxy the same unobservable order flow
    ("X1", "X2", "correlates", 0.8), ("X2", "X1", "correlates", 0.8),
    ("X1", "X3", "correlates", 0.8), ("X3", "X1", "correlates", 0.8),
    ("X2", "X3", "correlates", 0.8), ("X3", "X2", "correlates", 0.8),
    # C2/C3: shared LLM backend (3a2l) + shared abstention mode
    ("C2", "C3", "correlates", 0.8), ("C3", "C2", "correlates", 0.8),
    # S3a/S3b: harmonic vs classical patterns, same price data
    ("S3a", "S3b", "correlates", 0.6), ("S3b", "S3a", "correlates", 0.6),
    # C1/C6: shared DXY + oil inputs
    ("C1", "C6", "correlates", 0.7), ("C6", "C1", "correlates", 0.7),

    # ── Confirms (agreement raises the other's weight) ──
    ("S1", "S3b", "confirms", 0.7), ("S3b", "S1", "confirms", 0.7),  # double top/bottom
    ("S1", "S2", "confirms", 0.6), ("S2", "S1", "confirms", 0.6),    # fib levels on S/R

    # ── Contradicts (disagreement is informative) ──
    ("S5c", "S5b", "contradicts", 0.6),  # volatility expansion contradicts trend
]


def read_creds(path: Path) -> dict:
    creds = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        creds[key.strip()] = value
    return creds


def main() -> int:
    import psycopg

    creds = read_creds(CREDS_FILE)
    ref = creds.get("SUPABASE_REF", "")
    db_password = creds.get("SUPABASE_DB_PASSWORD", "")
    if ref == FORBIDDEN_REF:
        print("REFUSING: creds file points at the Eye of Justice project.", file=sys.stderr)
        return 2
    if ref != GOLD_COUNCIL_REF:
        print(f"REFUSING: unexpected Supabase ref (expected {GOLD_COUNCIL_REF}).", file=sys.stderr)
        return 2
    if not db_password:
        print("REFUSING: SUPABASE_DB_PASSWORD missing from creds file.", file=sys.stderr)
        return 2

    host = f"db.{GOLD_COUNCIL_REF}.supabase.co"
    dsn = f"host={host} port=5432 user=postgres dbname=postgres sslmode=require password={db_password}"
    inserted = updated = 0
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            for frm, to, link_type, strength in EDGES:
                cur.execute(
                    """
                    INSERT INTO public.agent_links
                        (from_agent, to_agent, link_type, strength, source, sample_n, updated_by)
                    VALUES (%s, %s, %s, %s, 'manual', 0, 'manual-seed')
                    ON CONFLICT (from_agent, to_agent, link_type) DO UPDATE SET
                        strength = EXCLUDED.strength,
                        source = EXCLUDED.source,
                        sample_n = EXCLUDED.sample_n,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = now()
                    RETURNING (xmax = 0) AS was_insert
                    """,
                    (frm, to, link_type, strength),
                )
                if cur.fetchone()[0]:
                    inserted += 1
                else:
                    updated += 1
        conn.commit()

        # ── Verify ──
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.agent_links")
            total = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM public.agent_links "
                "WHERE from_agent IN ('M1','M3','M2') AND to_agent IN ('M3','M2','E1') "
                "AND link_type = 'feeds'"
            )
            chain = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM public.agent_links "
                "WHERE (from_agent, to_agent) IN "
                "(('settlements','J1'), ('J1','E2'), ('E2','M1')) AND link_type = 'feeds'"
            )
            loop = cur.fetchone()[0]
            cur.execute(
                "SELECT link_type, count(*) FROM public.agent_links GROUP BY link_type ORDER BY link_type"
            )
            by_type = cur.fetchall()

    print(f"edges defined: {len(EDGES)}")
    print(f"inserted: {inserted}, updated (already present): {updated}")
    print(f"total rows in agent_links: {total}")
    print(f"review-chain feeds edges (M1->M3, M3->M2, M2->E1): {chain} (expect 3)")
    print(f"learning-loop feeds edges (settlements->J1, J1->E2, E2->M1): {loop} (expect 3)")
    print("by link_type:")
    for link_type, n in by_type:
        print(f"  {link_type}: {n}")
    if total != len(EDGES) or chain != 3 or loop != 3:
        print("VERIFICATION FAILED", file=sys.stderr)
        return 1
    print("OK — graph seeded and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
