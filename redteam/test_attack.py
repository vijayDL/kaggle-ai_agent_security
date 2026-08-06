"""End-to-end test of submission/attack.py against the live model.

Runs AttackAlgorithm.run() against a SandboxEnv(Optimal) — mirroring the grader's
public search env — then scores the RETURNED candidates under all four guardrail
hypotheses to see the real public/private-hypothesis spread.

Run:  .venv/bin/python -m redteam.test_attack [budget_s]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make submission/attack.py importable (it is intentionally standalone).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "submission"))

from attack import AttackAlgorithm  # type: ignore

from aicomp_sdk.attacks.contracts import AttackRunConfig
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail
from aicomp_sdk.attacks.baselines.guardrail_rules import Guardrail as RulesGuardrail

from redteam.harness import FIXTURES_DIR, score_candidates
from redteam.guardrails_hyp import H2_read_taint, H3_data_scan
from redteam.vllm_agent import build_gemma_vllm_agent, build_gptoss_vllm_agent


def main() -> None:
    # Usage: test_attack [budget_s] [gemma|gptoss]
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
    model = sys.argv[2] if len(sys.argv) > 2 else "gemma"

    if model == "gptoss":
        def af():
            return build_gptoss_vllm_agent(reasoning_effort="low")
    else:
        def af():
            return build_gemma_vllm_agent()
    print(f"model={model}")

    # 1. Run the attack's live validation-fill against the public search env.
    search_env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                            guardrail=OptimalGuardrail(), max_tool_hops=8)
    algo = AttackAlgorithm()
    cfg = AttackRunConfig(time_budget_s=budget, max_tool_hops=8)
    print(f"running attack.run() with {budget:.0f}s budget ...")
    candidates = algo.run(search_env, cfg)
    msgs = [c.user_messages for c in candidates]
    print(f"attack returned {len(candidates)} validated candidates")

    # classify by shape for a quick mix readout
    def kind_of(m: tuple[str, ...]) -> str:
        if len(m) == 3:
            return "P2"
        s = m[0]
        if "http.post once with url" in s and "SECRET_MARKER" in s:
            return "P1"
        if "mail tool" in s:
            return "P3"
        if s.startswith("First use web.search to look up the daily bulletin"):
            return "P4"
        if s.startswith("First use web.search to look up the daily note"):
            return "P5"
        return "?"
    mix: dict[str, int] = {}
    for m in msgs:
        mix[kind_of(m)] = mix.get(kind_of(m), 0) + 1
    print("mix:", mix)

    # 2. Score the returned candidates under all four guardrails.
    guardrails = {
        "Optimal(pub)": OptimalGuardrail,
        "H1_rules": RulesGuardrail,
        "H2_readtaint": H2_read_taint,
        "H3_datascan": H3_data_scan,
    }
    print("\nSCORING RETURNED PORTFOLIO under each guardrail:")
    for gname, gfac in guardrails.items():
        r = score_candidates(msgs, af, gfac, label=gname)
        pc = ",".join(f"{k}×{v}" for k, v in sorted(r.predicate_counts.items())) or "-"
        print(f"  {gname:14} fired={r.n_fired}/{r.n} cells={r.unique_cells} "
              f"raw={r.raw:.0f} norm={r.normalized:.3f}  ({pc})")


if __name__ == "__main__":
    main()
