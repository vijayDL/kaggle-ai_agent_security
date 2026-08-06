"""Focused, CHEAP multipost decision benchmark: single-post P1 vs P1M multipost.

The full head-to-head (run_compare) re-scores every FILLED candidate at 8 hops x2
guardrails — the replay dominates and blows any short wall-clock. Here we emit a
FIXED small sample (blind-emit K) per engine and score once under the public
guardrail, isolating the two numbers that decide multipost:

  raw/candidate         -> multipost should be ~N x single-post (N posts/cand)
  raw per replay-second -> the replay-BOUND throughput; the grader replays at 8
                           hops in a fresh budget, so this is what the returned
                           set's score is actually limited by.

Multipost wins iff its raw-per-replay-second beats single-post's (it amortizes
the one unscored wrap-up hop across N scored posts). Prints incrementally.

  python -m redteam.run_multipost [model] [K]     # in aas_harness
"""

from __future__ import annotations

import sys
import time

sys.path.insert(0, "submission")
import attack as ours  # type: ignore

from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.harness import FIXTURES_DIR, score_candidates  # noqa: F401 (FIXTURES via score)
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    K = int(sys.argv[2]) if len(sys.argv) > 2 else 24

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)

        def bench(plan, label):
            ours._PLAN = list(plan)
            algo = ours.AttackAlgorithm(config={"n_candidates": K})
            cands = algo.run(None, None)            # blind-emit exactly K
            msgs = [c.user_messages for c in cands]
            t = time.monotonic()
            rep = score_candidates(msgs, af, Optimal, label=label)
            dt = time.monotonic() - t
            n = max(1, len(cands))
            print(
                f"  {label:16} K={len(cands):3d} fired={rep.n_fired}/{rep.n} "
                f"raw={rep.raw:6.0f} raw/cand={rep.raw/n:5.1f} "
                f"replay={dt:5.0f}s ({dt/n:4.2f}s/cand) "
                f"raw/replay-s={rep.raw/dt:5.2f}  preds=({rep.predicate_counts})",
                flush=True,
            )
            return rep.raw / dt

        print(f"### {model} multipost decision bench (K={K}, 8-hop replay, public) ###",
              flush=True)
        s = bench(["P1"], "single-P1")
        m = bench(["P1M"], f"multipost-N{ours._P1_MULTIPOST_N}")
        verdict = "MULTIPOST WINS" if m > s else "single-post wins"
        print(f"\n  => raw/replay-s: multipost {m:.2f} vs single {s:.2f}  ==> {verdict} "
              f"({m/s:.2f}x)", flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
