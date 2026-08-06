"""Fill-safety check for a variant: does a REAL fill (with replay-safe sizing)
return a set whose 8-hop public replay fits the SAME budget the grader replays in?
A returned set whose replay exceeds budget would FATAL-overrun on Kaggle.

  python -m redteam.run_fillsafe [variant] [model] [budget_s]   # in aas_harness
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "submission")
import attack as ours  # type: ignore
from build_notebook import VARIANTS  # type: ignore

from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.guardrails_indep import G_value_prov
from redteam.harness import FIXTURES_DIR, score_candidates
from aicomp_sdk.attacks.contracts import AttackRunConfig
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal


def main() -> None:
    variant = sys.argv[1] if len(sys.argv) > 1 else "v7_multipost"
    model = sys.argv[2] if len(sys.argv) > 2 else "gpt_oss"
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0
    ours._PLAN = list(VARIANTS[variant][0])

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                         guardrail=Optimal(), max_tool_hops=8)
        t = time.monotonic()
        cands = ours.AttackAlgorithm().run(
            env, AttackRunConfig(time_budget_s=budget, max_tool_hops=8))
        fill_s = time.monotonic() - t

        msgs = [c.user_messages for c in cands]
        t = time.monotonic()
        rep = score_candidates(msgs, af, Optimal, label=variant)
        replay_s = time.monotonic() - t

        # Private-replay cost: the grader also replays under the private guardrail. If a
        # data-scanning private guardrail DENIES the posts and the model then wanders,
        # private replay could exceed public -> our public-calibrated sizing would
        # FATAL-overrun. G_value_prov models exactly that (blocks payloads carrying the
        # secret value; the sentinel PASSES, so posts succeed here -> lower bound). We
        # ALSO time it to compare replay wall-clock, which is what the sizing budgets.
        t = time.monotonic()
        rep_priv = score_candidates(msgs, af, G_value_prov, label=variant + "_priv")
        replay_priv_s = time.monotonic() - t

        margin = budget - max(replay_s, replay_priv_s)
        verdict = "SAFE" if max(replay_s, replay_priv_s) < budget else "OVERRUN(FATAL)"
        ratio = replay_priv_s / replay_s if replay_s else 0.0
        print(f"\n### {variant} @ {model} fill-safety (budget={budget:.0f}s) ###")
        print(f"  filled       : {len(cands)} cands in {fill_s:.0f}s")
        print(f"  replay PUBLIC : {replay_s:.0f}s  raw={rep.raw:.0f} norm={rep.normalized:.2f} "
              f"preds={rep.predicate_counts}")
        print(f"  replay PRIVATE: {replay_priv_s:.0f}s (G_value_prov)  raw={rep_priv.raw:.0f} "
              f"norm={rep_priv.normalized:.2f}  priv/pub time={ratio:.2f}x")
        print(f"  VERDICT      : worst replay {max(replay_s, replay_priv_s):.0f}s vs budget "
              f"{budget:.0f}s -> {verdict} margin={margin:+.0f}s")
    finally:
        unload(server)


if __name__ == "__main__":
    main()
