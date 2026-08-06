"""Quantify the review's #1 open question: what happens if the private guardrail
SCANS http.post.data for the SECRET_MARKER sentinel (P1M's kill switch)?

Scores (a) each primitive and (b) the shipping variants v7/v8 under the new
G_marker_scan (sentinel blocked, provenance NOT checked) and G_combined (both),
alongside G_value_prov (sentinel PASSES) and G_source_prov for contrast. Answers:
  - which primitives survive if the marker is scanned (expect: P1M dies; P4/P4B
    benign posts survive; P3 clean email survives; P6 real-secret dies),
  - how much each shipping notebook loses under that branch.

  python -m redteam.run_marker_scan [model] [budget_s]     # in aas_harness
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "submission")
import attack as ours  # type: ignore
from build_notebook import VARIANTS  # type: ignore

from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.guardrails_indep import (
    G_combined, G_marker_scan, G_source_prov, G_value_prov,
)
from redteam.harness import FIXTURES_DIR, score_candidates
from aicomp_sdk.attacks.contracts import AttackRunConfig
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal

GUARDS = [("Optimal(pub)", Optimal), ("value_prov", G_value_prov),
          ("source_prov", G_source_prov), ("MARKER_SCAN", G_marker_scan),
          ("COMBINED", G_combined)]
PRIMS = ["P1M", "P4", "P4B", "P5", "P3", "P6"]


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gemma"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 90.0
    K = 12

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)

        def emit(kind, n):
            return [ours.make_candidate(kind, i) for i in range(n)]

        # (a) per-primitive hit-rate | raw across the guardrail set
        print(f"\n### {model}: per-primitive under guardrail set (blind K={K}) ###", flush=True)
        hdr = "  " + "prim".ljust(6) + "".join(g.ljust(14) for g, _ in GUARDS)
        print(hdr, flush=True)
        for kind in PRIMS:
            msgs = emit(kind, K)
            cells = []
            for gname, G in GUARDS:
                rep = score_candidates(msgs, af, G, label=f"{kind}:{gname}")
                nc = max(1, len(msgs))
                hit = rep.n_fired / nc
                cells.append(f"{hit:.2f}|{rep.raw/nc:4.1f}".ljust(14))
            print("  " + kind.ljust(6) + "".join(cells), flush=True)

        # (b) shipping variants: norm under Optimal vs MARKER_SCAN vs COMBINED
        print(f"\n### {model}: shipping variants norm (fill @ {budget:.0f}s) ###", flush=True)
        for label in ("v7_multipost", "v8_hybrid_multipost"):
            ours._PLAN = list(VARIANTS[label][0])
            env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                             guardrail=Optimal(), max_tool_hops=8)
            cands = ours.AttackAlgorithm().run(
                env, AttackRunConfig(time_budget_s=budget, max_tool_hops=8))
            msgs = [c.user_messages for c in cands]
            out = []
            for gname, G in (("Optimal", Optimal), ("MARKER_SCAN", G_marker_scan),
                             ("COMBINED", G_combined)):
                rep = score_candidates(msgs, af, G, label=f"{label}:{gname}")
                out.append(f"{gname}={rep.normalized:6.2f}")
            print(f"  {label:22} ({len(cands)}c)  " + "  ".join(out), flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
