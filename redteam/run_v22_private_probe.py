"""Live behavioral-fire check for a v22 private-only primitive before spending a
submission slot. Imports the module, calls _msg(i) for i in range(K), replays
against the real Optimal-guarded env, and reports the module's own _fired() rate.

  docker compose run --rm aas_harness -m redteam.run_v22_private_probe <module> [K] [model]
  module: attack_v22_deleteonly | attack_v22_storewrite
"""
from __future__ import annotations

import importlib
import sys
import time

sys.path.insert(0, "submission")

from redteam.gguf_agent import build_gguf_server, agent_factory_for, unload
from redteam.harness import FIXTURES_DIR
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal


def main() -> None:
    modname = sys.argv[1] if len(sys.argv) > 1 else "attack_v22_deleteonly"
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    model = sys.argv[3] if len(sys.argv) > 3 else "gpt_oss"
    m = importlib.import_module(modname)

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                          guardrail=Optimal(), max_tool_hops=8)
        fires, lats = 0, []
        for i in range(K):
            env.reset()
            t0 = time.monotonic()
            try:
                env.interact(m._msg(i), max_tool_hops=8)
            except Exception as e:
                print(f"  [{i}] EXC {type(e).__name__}: {e}")
            lats.append(time.monotonic() - t0)
            tr = env.export_trace_dict()
            f = m.AttackAlgorithm._fired(tr)
            if f:
                fires += 1
            names = [e.get("name") for e in tr.get("tool_events", [])]
            oks = [e.get("ok") for e in tr.get("tool_events", [])]
            print(f"  [{i}] fired={f} events={list(zip(names, oks))}")
        print(f"\n### {modname} | {model} | K={K} | fires={fires}/{K} "
              f"avg_lat={sum(lats)/len(lats):.2f}s ###")
    finally:
        unload(server)


if __name__ == "__main__":
    main()
