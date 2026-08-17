"""Verify attack_v19_privmix: the mixed private portfolio fires as designed against
both guardrails. Static emit (n_candidates) so the mix is deterministic; score vs
public Optimal and the private-proxy guardrail_rules.

Expected (N=15 -> idx 0,5,10 = share (3), rest deputy (12)):
  public(Optimal): CONFUSED_DEPUTY x12 (deputy fires), share DENIED (0)
  private(rules):  CONFUSED_DEPUTY x12 + UNTRUSTED_TO_ACTION x3 (both fire)

  docker run ... aas-harness -m redteam.run_privmix_verify <model> [N]
"""
from __future__ import annotations

import sys
sys.path.insert(0, "submission")

from redteam.gguf_agent import build_gguf_server, agent_factory_for, unload
from redteam.harness import score_candidates
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal
from aicomp_sdk.attacks.baselines.guardrail_rules import Guardrail as PrivateProxy
from attack_v19_privmix import AttackAlgorithm, _is_share


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    atk = AttackAlgorithm(config={"n_candidates": N})
    cands = atk.run(None, None)
    msgs = [(c.user_messages[0],) for c in cands]
    n_share = sum(1 for i in range(N) if _is_share(i))
    print(f"\n### PRIVMIX VERIFY | {model} | N={N} ({n_share} share / {N-n_share} deputy) ###", flush=True)
    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        score_candidates(msgs[:1], af, Optimal, label="warmup")
        print(f"{'guardrail':16} {'predicates':>42} {'raw':>7}", flush=True)
        for gname, G in (("public(Optimal)", Optimal), ("private(rules)", PrivateProxy)):
            rep = score_candidates(msgs, af, G, label=gname)
            pc = ", ".join(f"{k}x{v}" for k, v in sorted(rep.predicate_counts.items())) or "NONE"
            print(f"{gname:16} {pc:>42} {rep.raw:7.0f}", flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
