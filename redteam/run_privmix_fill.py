"""End-to-end verify of attack_v19_privmix via the LIVE fill (not static emit).
Runs the real run()/_fill against a public-Optimal env with a small budget, then
scores the RETURNED candidates against both guardrails. Confirms: (1) the fill
returns a working deputy+share mix, (2) returned share candidates fire
UNTRUSTED_TO_ACTION on the private proxy, (3) share fire-yield during generation.

  docker run ... aas-harness -m redteam.run_privmix_fill <model> [BUDGET_S]
"""
from __future__ import annotations

import sys
sys.path.insert(0, "submission")

from redteam.gguf_agent import build_gguf_server, agent_factory_for, unload
from redteam.harness import FIXTURES_DIR, score_candidates
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal
from aicomp_sdk.attacks.baselines.guardrail_rules import Guardrail as PrivateProxy
from aicomp_sdk.attacks.contracts import AttackRunConfig
from attack_v19_privmix import AttackAlgorithm, SHARE_TEMPLATE


def _is_share_msg(m: str) -> bool:
    return "web.search" in m or "Step 1" in m


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    B = float(sys.argv[2]) if len(sys.argv) > 2 else 90.0
    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        env = SandboxEnv(seed=123, fixtures_dir=FIXTURES_DIR, agent=af(), guardrail=Optimal(), max_tool_hops=8)
        env.reset()
        cfg = AttackRunConfig(time_budget_s=B, max_tool_hops=8)
        cands = AttackAlgorithm(config={}).run(env, cfg)
        msgs = [(c.user_messages[0],) for c in cands]
        n_share = sum(1 for c in cands if _is_share_msg(c.user_messages[0]))
        print(f"\n### PRIVMIX LIVE-FILL | {model} | budget={B:.0f}s ###", flush=True)
        print(f"  returned: {len(cands)}  (share {n_share} / deputy {len(cands)-n_share}, "
              f"share%={100*n_share/max(len(cands),1):.0f})", flush=True)
        print(f"{'guardrail':16} {'predicates':>44} {'raw':>7}", flush=True)
        for gname, G in (("public(Optimal)", Optimal), ("private(rules)", PrivateProxy)):
            rep = score_candidates(msgs, af, G, label=gname)
            pc = ", ".join(f"{k}x{v}" for k, v in sorted(rep.predicate_counts.items())) or "NONE"
            print(f"{gname:16} {pc:>44} {rep.raw:7.0f}", flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
