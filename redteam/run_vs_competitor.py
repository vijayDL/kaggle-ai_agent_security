"""Head-to-head with multipost on BOTH sides: the public-90 competitor engine
(forced multipost) vs our v7 (P1M S2). Same fill budget, score the returned set
once under the public Optimal guardrail (what the LB measures), and check the
8-hop replay fits the budget (FATAL-overrun guard).

  python -m redteam.run_vs_competitor [model] [budget_s]   # in aas_harness
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "submission")
import attack as ours  # type: ignore
from build_notebook import VARIANTS  # type: ignore

import redteam.competitor_p1 as theirs
from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.harness import FIXTURES_DIR, score_candidates
from aicomp_sdk.attacks.contracts import AttackRunConfig
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)

        def run_engine(algo, label):
            env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                             guardrail=Optimal(), max_tool_hops=8)
            t = time.monotonic()
            cands = algo.run(env, AttackRunConfig(time_budget_s=budget, max_tool_hops=8))
            fill_s = time.monotonic() - t
            msgs = [c.user_messages for c in cands]
            t = time.monotonic()
            rep = score_candidates(msgs, af, Optimal, label=label)
            replay_s = time.monotonic() - t
            safe = "SAFE" if replay_s < budget else "OVERRUN"
            exfil = rep.predicate_counts.get("EXFILTRATION", 0)
            n = max(1, len(cands))
            print(f"  {label:26} fill={len(cands):4d}c/{fill_s:3.0f}s  "
                  f"posts/c={exfil/n:4.2f}  raw={rep.raw:6.0f} norm={rep.normalized:6.2f}  "
                  f"replay={replay_s:3.0f}s[{safe}]  raw/replay-s={rep.raw/replay_s:6.2f}",
                  flush=True)

        print(f"\n### {model} @ {budget:.0f}s — competitor(forced-multipost) vs ours(v7 S2) "
              f"[public Optimal] ###", flush=True)
        # Force the competitor's per-model split to ALWAYS classify slow -> always
        # multipost forge (its 12s threshold would skip it on the fast Blackwell).
        theirs.SPLIT_THRESHOLD_S = 0.0
        run_engine(theirs.AttackAlgorithm(), "COMPETITOR(forced-mp)")
        ours._PLAN = list(VARIANTS["v7_multipost"][0])
        run_engine(ours.AttackAlgorithm(), "OURS(v7 P1M S4)")
    finally:
        unload(server)


if __name__ == "__main__":
    main()
