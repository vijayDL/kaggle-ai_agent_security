"""Head-to-head: the public 90-notebook engine vs our v3, through the grader-exact
harness on a real GGUF. Both are pure SECRET_MARKER — the delta is fill efficiency.
Reports candidates filled, and the Optimal (public) score of the returned set, plus a
G_value_prov spot check (both should survive it — sentinel passes value-provenance).

Run inside aas_harness:  python -m redteam.run_compare [model] [budget_s]
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "submission")
import attack as ours  # type: ignore
from build_notebook import VARIANTS  # type: ignore

import redteam.competitor_p1 as theirs
from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.guardrails_indep import G_value_prov
from redteam.harness import FIXTURES_DIR, score_candidates
from aicomp_sdk.attacks.contracts import AttackRunConfig
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)

        def run_ours(plan_label, label):
            ours._PLAN = list(VARIANTS[plan_label][0])
            run_engine(ours.AttackAlgorithm(), label)

        def run_engine(algo, label):
            env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                             guardrail=Optimal(), max_tool_hops=8)
            t = time.monotonic()
            cands = algo.run(env, AttackRunConfig(time_budget_s=budget, max_tool_hops=8))
            fill_s = time.monotonic() - t
            msgs = [c.user_messages for c in cands]
            pub = score_candidates(msgs, af, Optimal, label=label)
            prv = score_candidates(msgs, af, G_value_prov, label=label)
            print(f"  {label:20} {len(cands):4d} cands in {fill_s:5.0f}s fill | "
                  f"public fired={pub.n_fired}/{pub.n} raw={pub.raw:5.0f} norm={pub.normalized:5.2f} | "
                  f"value_prov norm={prv.normalized:5.2f}")

        print(f"\n### {model} @ {budget:.0f}s budget — pure-P1 fill efficiency head-to-head ###")
        run_engine(theirs.AttackAlgorithm(), "COMPETITOR(as-is)")
        # FAIR: force the competitor's forge ON (its 12s latency threshold is tuned for
        # the hosted T4; on our faster GPU gpt_oss may be <12s -> it skips the forge).
        # Threshold 0 -> always classified slow -> always forges, isolating 1-hop vs 8-hop.
        theirs.SPLIT_THRESHOLD_S = 0.0
        run_engine(theirs.AttackAlgorithm(), "COMPETITOR(forced-forge)")
        run_ours("v3_pure_p1", "OURS(v3 forge+1hop)")
        run_ours("v7_multipost", f"OURS(v7 multipost N={ours._P1_MULTIPOST_N})")
    finally:
        unload(server)


if __name__ == "__main__":
    main()
