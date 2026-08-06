"""Does shortening P1M's URLs buy throughput? Our P1M offsets to band 2,000,000 for
cross-primitive collision-avoidance -> 16-char URLs. But PURE v7 has no other primitive,
so it can use band 0 -> 12-char URLs, saving ~2 tokens/post in both the prompt AND every
generated http.post call. Fill v7 at a fixed budget with LONG vs SHORT urls; compare
candidate count and norm (throughput). Same phrasing, same N, only the band differs.

  python -m redteam.run_urllen [model] [budget_s]     # in aas_harness
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


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0
    ours._PLAN = ["P1M"]

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)

        def run(band, tag):
            ours._BAND_P1M = band
            sample = ours.make_candidate("P1M", 0)[0]
            urls_len = len(ours._url(band))
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
            print(f"  {tag:14} url_len={urls_len:2d} msg_chars={len(sample):4d}  "
                  f"fill={len(cands):4d}c/{fill_s:3.0f}s  norm={rep.normalized:6.2f}  "
                  f"replay={replay_s:3.0f}s raw/replay-s={rep.raw/replay_s:6.2f}", flush=True)
            return rep.normalized

        print(f"\n### {model} P1M URL-length throughput (budget={budget:.0f}s) ###", flush=True)
        long_norm = run(2_000_000, "LONG(band2M)")
        short_norm = run(0, "SHORT(band0)")
        d = 100 * (short_norm - long_norm) / long_norm if long_norm else 0
        print(f"\n  SHORT vs LONG: norm {short_norm:.2f} vs {long_norm:.2f}  =>  {d:+.1f}%",
              flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
