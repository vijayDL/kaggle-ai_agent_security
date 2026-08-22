"""Live behavioral-fire check for attack_v23_realsecret_iso.py (2-message read->post
candidate) before spending a submission slot.

  docker compose run --rm aas_harness -m redteam.run_v23_realsecret_probe [K] [model]
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, "submission")

import attack_v23_realsecret_iso as m

from redteam.gguf_agent import build_gguf_server, agent_factory_for, unload
from redteam.harness import FIXTURES_DIR
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal


def main() -> None:
    K = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    model = sys.argv[2] if len(sys.argv) > 2 else "gpt_oss"

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                          guardrail=Optimal(), max_tool_hops=8)
        fires, lats = 0, []
        for i in range(K):
            msgs = m._messages(i)
            env.reset()
            t0 = time.monotonic()
            for msg in msgs:
                env.interact(msg, max_tool_hops=8)
            lats.append(time.monotonic() - t0)
            tr = env.export_trace_dict()
            f = m.AttackAlgorithm._fired(tr)
            if f:
                fires += 1
            names = [(e.get("name"), e.get("ok")) for e in tr.get("tool_events", [])]
            print(f"  [{i}] fired={f} events={names}")
        print(f"\n### {model} | K={K} | fires={fires}/{K} avg_lat={sum(lats)/len(lats):.2f}s ###")
    finally:
        unload(server)


if __name__ == "__main__":
    main()
