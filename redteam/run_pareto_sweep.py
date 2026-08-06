"""Pareto sweep for the P1M multipost engine: find the (N, replay-fraction) that
maximizes public score WITHOUT losing the FATAL-overrun safety margin.

Two axes:
  N              = posts per candidate (_P1_MULTIPOST_N). More posts/cand amortize
                   the wrap-up hop, but each candidate costs more hops (and >7 hits
                   the 8-hop replay cap, so posts/cand saturates).
  frac           = _REPLAY_SAFE_FRAC_CHEAP, how much of the replay budget the fill
                   targets. Higher = more candidates = more score, less margin.

Objective: maximize `norm` subject to replay < budget (margin). We score under the
PUBLIC guardrail only and use its replay time as the safety proxy, since P1M private
replay == public (measured priv/pub = 1.00x: the sentinel passes value-provenance,
posts succeed identically). A config is Pareto-optimal if no other config beats it on
BOTH norm and margin.

  python -m redteam.run_pareto_sweep [model] [budget_s]     # in aas_harness
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "submission")
import attack as ours  # type: ignore

from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.harness import FIXTURES_DIR, score_candidates
from aicomp_sdk.attacks.contracts import AttackRunConfig
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal

N_GRID = [2, 4, 6, 8]
FRAC_GRID = [0.75, 0.85]


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0
    ours._PLAN = ["P1M"]

    server = build_gguf_server(model)
    rows = []
    try:
        af = agent_factory_for(server)
        print(f"### {model} Pareto sweep (budget={budget:.0f}s, public Optimal, "
              f"N×frac = {N_GRID}×{FRAC_GRID}) ###", flush=True)
        print(f"  {'N':>2} {'frac':>4}  {'cands':>5} {'posts/c':>7} {'norm':>6} "
              f"{'replay':>6} {'margin':>7}", flush=True)
        for n in N_GRID:
            for frac in FRAC_GRID:
                ours._P1_MULTIPOST_N = n
                ours._REPLAY_SAFE_FRAC_CHEAP = frac
                env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                                 guardrail=Optimal(), max_tool_hops=8)
                cands = ours.AttackAlgorithm().run(
                    env, AttackRunConfig(time_budget_s=budget, max_tool_hops=8))
                msgs = [c.user_messages for c in cands]
                t = time.monotonic()
                rep = score_candidates(msgs, af, Optimal, label=f"N{n}f{frac}")
                replay_s = time.monotonic() - t
                margin = budget - replay_s
                nc = max(1, len(cands))
                exfil = rep.predicate_counts.get("EXFILTRATION", 0)
                rows.append((n, frac, len(cands), exfil / nc, rep.normalized,
                             replay_s, margin))
                flag = "" if margin > 0 else "  <-OVERRUN"
                print(f"  {n:>2} {frac:>4} {len(cands):>6} {exfil/nc:>7.2f} "
                      f"{rep.normalized:>6.2f} {replay_s:>5.0f}s {margin:>+6.0f}s{flag}",
                      flush=True)

        # Pareto frontier: keep rows not dominated on BOTH norm and margin.
        def dominated(r):
            return any(o is not r and o[4] >= r[4] and o[6] >= r[6]
                       and (o[4] > r[4] or o[6] > r[6]) for o in rows)
        front = [r for r in rows if not dominated(r)]
        front.sort(key=lambda r: -r[4])
        print(f"\n  PARETO FRONTIER ({model}) — norm vs safety-margin:", flush=True)
        for n, frac, c, pc, norm, rs, mg in front:
            print(f"    N={n} frac={frac}  norm={norm:.2f}  margin={mg:+.0f}s  "
                  f"({c}c, {pc:.2f} posts/c)", flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
