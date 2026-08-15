"""Local-vs-Kaggle correlation check. Run each LABELED variant's actual engine
against the live local env for a fixed wall-budget, score the returned candidates
under the public Optimal guardrail, and report local raw/count. Comparing this
across variants (per model) against their KNOWN real Kaggle scores tells us whether
the local harness RANKS variants like the real board does.

  docker compose run --rm aas_harness -m redteam.run_corr_check <model> [budget_s]
    model = gpt_oss | gemma

Local latency is 3-12x inflated (absolute), so only the RANKING across variants is
meaningful. Combine both models' outputs offline and Spearman-correlate vs real.
"""
from __future__ import annotations

import sys, time, importlib.util, os
from types import SimpleNamespace

sys.path.insert(0, "submission")

from redteam.gguf_agent import build_gguf_server, agent_factory_for, unload
from redteam.harness import FIXTURES_DIR, score_candidates
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal

# variant label -> engine source file (all share the proven chassis)
VARIANTS = {
    "plain_v17edge":  "submission/attack_v17_edge.py",
    "no_ok":          "submission/attack_v18_no_ok.py",
    "terse_ok":       "submission/attack_v18_terse_ok.py",
    "gemma_forge":    "submission/attack_v18_gemma_forge.py",
    "multipost_n5":   "submission/attack_v18_multipost_n5.py",
    "multipost_n7":   "submission/attack_v18_multipost_n7.py",
}

# known real Kaggle scores (same-day-control normalized in comments); for offline correlation
REAL = {
    "plain_v17edge": 88.9, "no_ok": 80.235, "terse_ok": 88.380,
    "gemma_forge": 82.890, "multipost_n5": 89.915, "multipost_n7": 72.855,
}


def load_algo(path: str):
    spec = importlib.util.spec_from_file_location(f"eng_{os.path.basename(path)[:-3]}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    algo = m.AttackAlgorithm()
    # Force the fill to use the FULL wall budget (neutralize the replay-cost early-stop),
    # so candidate count reflects true per-candidate throughput, not the sizing heuristic.
    algo.config = {"replay_budget_s": 1e7, "replay_safe_frac": 0.99, "fill_budget_frac": 0.99}
    return algo


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt_oss"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        # a fresh env per run() call (the engine drives env.reset/interact itself)
        from aicomp_sdk.core.env.sandbox import SandboxEnv
        cfg = SimpleNamespace(time_budget_s=budget, max_tool_hops=8)

        print(f"\n### LOCAL corr check | model={model} budget={budget:.0f}s | public Optimal ###", flush=True)
        print(f"{'variant':16} {'cands':>6} {'raw/c':>7} {'local_raw':>9} {'real_kaggle':>12}", flush=True)
        for label, path in VARIANTS.items():
            try:
                env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR,
                                 agent=af(), guardrail=Optimal(), max_tool_hops=8)
                algo = load_algo(path)
                t0 = time.monotonic()
                cands = algo.run(env, cfg)  # the engine's own live fill loop (fixed budget)
                fill_s = time.monotonic() - t0
                # raw/candidate can differ (multipost fires N EXFIL/cand): sample-score a few.
                # AttackCandidate -> its .user_messages tuple (what score_candidates expects).
                sample = [c.user_messages for c in list(cands)[:20]]
                raw_per = 0.0
                try:
                    if sample:
                        rep = score_candidates(sample, af, Optimal, label=label, max_tool_hops=8)
                        raw_per = rep.raw / len(sample)
                except Exception as se:
                    raw_per = -1.0  # scoring failed; count still valid
                    print(f"    [score err {label}: {type(se).__name__}: {str(se)[:60]}]", flush=True)
                local_raw = raw_per * len(cands)
                print(f"{label:16} {len(cands):6d} {raw_per:6.1f}/c {local_raw:9.0f} {REAL[label]:12.1f}  (fill {fill_s:.0f}s)", flush=True)
            except Exception as e:
                print(f"{label:16}  ERROR: {type(e).__name__}: {str(e)[:80]}", flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
