"""Pre-submission fill+safety check for the 3 multi-turn variants. Applies each
variant's engine knobs, fills at a fixed budget, and reports norm + whether the replay
fits the budget (FATAL-overrun guard) — especially for the AGGRESSIVE v11 (frac 0.92).

  python -m redteam.run_cfgcheck [model] [budget_s]     # in aas_harness
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

# (label, knob overrides) — mirrors build_notebook _ENGINE_OVERRIDE
CONFIGS = [
    ("v10 mt+OK    ", dict(_P1M_MULTITURN=1, _P1_MULTIPOST_N=6, _P1M_MT_DROP_OK=0,
                           _REPLAY_SAFE_FRAC_CHEAP=0.85, _FILL_FRAC=0.92, _SLOWEST_MULT=1.5)),
    ("v12 mt+noOK  ", dict(_P1M_MULTITURN=1, _P1_MULTIPOST_N=6, _P1M_MT_DROP_OK=1,
                           _REPLAY_SAFE_FRAC_CHEAP=0.85, _FILL_FRAC=0.92, _SLOWEST_MULT=1.5)),
    ("v11 mt+noOK+aggr", dict(_P1M_MULTITURN=1, _P1_MULTIPOST_N=6, _P1M_MT_DROP_OK=1,
                              _REPLAY_SAFE_FRAC_CHEAP=0.92, _FILL_FRAC=0.95, _SLOWEST_MULT=1.35)),
]


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 150.0
    ours._PLAN = ["P1M"]

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        print(f"\n### {model} 3-variant fill+safety @ {budget:.0f}s ###", flush=True)
        for tag, knobs in CONFIGS:
            for k, v in knobs.items():
                setattr(ours, k, v)
            env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                             guardrail=Optimal(), max_tool_hops=8)
            t = time.monotonic()
            cands = ours.AttackAlgorithm().run(
                env, AttackRunConfig(time_budget_s=budget, max_tool_hops=8))
            fill_s = time.monotonic() - t
            msgs = [c.user_messages for c in cands]
            t = time.monotonic()
            rep = score_candidates(msgs, af, Optimal, label=tag)
            replay_s = time.monotonic() - t
            safe = "SAFE" if replay_s < budget else "OVERRUN(FATAL)"
            print(f"  {tag:18} fill={len(cands):4d}c/{fill_s:3.0f}s posts={rep.predicate_counts.get('EXFILTRATION',0):5d} "
                  f"norm={rep.normalized:6.2f} replay={replay_s:3.0f}s[{safe}]", flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
