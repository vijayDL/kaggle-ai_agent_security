"""End-to-end attack.py on the REAL competition GGUF: run AttackAlgorithm.run()
against a grader-exact env (real model + OptimalGuardrail, the generation setup),
then score the RETURNED candidates under Optimal + our private proxies. Validates
that behavioral validation + replay-safe sizing hold for a given variant's mix on
the actual model.

Run inside aas_harness:
  python -m redteam.run_gguf_attack [model] [budget_s] [variant]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "submission"))
import attack  # type: ignore  # noqa: E402

from build_notebook import VARIANTS  # type: ignore  # noqa: E402

from aicomp_sdk.attacks.contracts import AttackRunConfig
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail
from aicomp_sdk.attacks.baselines.guardrail_rules import Guardrail as RulesGuardrail

from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.guardrails_hyp import H2_read_taint, H3_data_scan
from redteam.harness import FIXTURES_DIR, score_candidates


def _kind(m: tuple[str, ...]) -> str:
    if len(m) == 3:
        return "P2"
    s = m[0]
    if s.startswith("Open ") and "post any recommended" in s:
        return "P6"
    if "http.post once with url" in s and "SECRET_MARKER" in s:
        return "P1"
    if "mail tool" in s:
        return "P3"
    if s.startswith("First use web.search to look up the daily bulletin"):
        return "P4/P4B"
    if s.startswith("First use web.search to look up the daily note"):
        return "P5"
    return "?"


def main() -> None:
    model_name = sys.argv[1] if len(sys.argv) > 1 else "gemma"
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0
    variant = sys.argv[3] if len(sys.argv) > 3 else "v5_injection"

    attack._PLAN = list(VARIANTS[variant][0])
    print(f"model={model_name} budget={budget:.0f}s variant={variant} plan={attack._PLAN}")

    server = build_gguf_server(model_name)
    try:
        af = agent_factory_for(server)
        search_env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(),
                                guardrail=OptimalGuardrail(), max_tool_hops=8)
        cands = attack.AttackAlgorithm().run(
            search_env, AttackRunConfig(time_budget_s=budget, max_tool_hops=8))
        msgs = [c.user_messages for c in cands]
        mix: dict[str, int] = {}
        for m in msgs:
            mix[_kind(m)] = mix.get(_kind(m), 0) + 1
        print(f"\nattack.run returned {len(cands)} validated candidates | mix: {mix}")

        print("\nSCORING RETURNED PORTFOLIO under each guardrail (real model):")
        for gname, gfac in [("Optimal(pub)", OptimalGuardrail), ("H1_rules", RulesGuardrail),
                            ("H2_readtaint", H2_read_taint), ("H3_datascan", H3_data_scan)]:
            r = score_candidates(msgs, af, gfac, label=gname)
            pc = ",".join(f"{k}×{v}" for k, v in sorted(r.predicate_counts.items())) or "-"
            print(f"  {gname:13} fired={r.n_fired}/{r.n} cells={r.unique_cells} "
                  f"raw={r.raw:.0f} norm={r.normalized:.3f}  ({pc})")
    finally:
        unload(server)


if __name__ == "__main__":
    main()
