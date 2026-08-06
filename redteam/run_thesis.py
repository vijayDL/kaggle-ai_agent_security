"""Step 2+3: real-model parity check, then the public-vs-private thesis.

  1. Parity: run ONE P1 candidate against the live Gemma-4 vLLM endpoint under the
     public guardrail and show the trace fired an http.post.
  2. Thesis: replay N P1 candidates under BOTH guardrails; expect the SECRET_MARKER
     primitive to score on public but ~0 on the private (guardrail_rules) proxy.

Run:  .venv/bin/python -m redteam.run_thesis  [N]
"""

from __future__ import annotations

import sys

from redteam.harness import FIXTURES_DIR, score_both_guardrails, score_candidates
from redteam.primitives import p1_secret_marker
from redteam.vllm_agent import build_gemma_vllm_agent
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print(f"fixtures: {FIXTURES_DIR}")

    def agent_factory():
        return build_gemma_vllm_agent()

    # --- 1. Parity check: one candidate, public guardrail, inspect the trace ---
    print("\n=== PARITY CHECK (1 candidate, public guardrail) ===")
    one = p1_secret_marker(1)
    print(f"user message: {one[0][0]!r}")
    rep = score_candidates(one, agent_factory, OptimalGuardrail, label="parity")
    f = rep.findings[0]
    print(f"fired={f.fired}  predicates={f.predicate_names()}  raw={f.raw:.0f}")
    for e in f.tool_events:
        print(f"  tool_event: name={e['name']} ok={e['ok']} "
              f"args={e['args']} source={e['source']} err={e.get('error')}")
    if not f.fired:
        print("  !! http.post did NOT fire — check endpoint/tool-calling before trusting scores")

    # --- 2. Thesis: N candidates under both guardrails -------------------------
    print(f"\n=== THESIS ({n} P1 candidates, both guardrails) ===")
    reports = score_both_guardrails(p1_secret_marker(n), agent_factory, model_label="gemma")
    print(reports["public"].summary())
    print(reports["private"].summary())
    pub, prv = reports["public"].normalized, reports["private"].normalized
    print(f"\nPublic normalized={pub:.3f}  Private normalized={prv:.3f}")
    if prv < pub * 0.25:
        print("=> THESIS CONFIRMED: SECRET_MARKER overfits the public guardrail; "
              "private ~collapses. Diversified portfolio (P2/P3) needed for the prize.")
    else:
        print("=> Thesis NOT confirmed on this proxy — inspect guardrail_rules behavior.")


if __name__ == "__main__":
    main()
