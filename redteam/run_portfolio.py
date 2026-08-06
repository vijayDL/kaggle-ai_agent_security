"""Score the P1/P2/P3 portfolio under both guardrails against live Gemma-4.

Run:  .venv/bin/python -m redteam.run_portfolio [N]
"""

from __future__ import annotations

import sys

from redteam.harness import score_both_guardrails
from redteam.primitives import p1_secret_marker, p2_read_dual_post, p3_confused_deputy
from redteam.vllm_agent import build_gemma_vllm_agent


def _dump_sample(name: str, report) -> None:
    """Show the first candidate's trace so we can see what the model actually did."""
    f = report.findings[0]
    print(f"    sample [{name}] fired={f.fired} predicates={f.predicate_names()}")
    for e in f.tool_events:
        data = e["args"].get("data", e["args"].get("body", ""))
        data = (str(data)[:48] + "…") if len(str(data)) > 48 else data
        print(f"      {e['name']:10} ok={str(e['ok']):5} "
              f"args={ {k: (str(v)[:40]) for k, v in e['args'].items()} } err={e.get('error')}")


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8

    def agent_factory():
        return build_gemma_vllm_agent()

    primitives = {
        "P1_secret_marker": p1_secret_marker(n),
        "P2_read_dual_post": p2_read_dual_post(n),
        "P3_confused_deputy": p3_confused_deputy(n),
    }

    print(f"{'primitive':20} {'guardrail':9} {'fired':>7} {'cells':>6} {'raw':>6} {'norm':>7}  predicates")
    print("-" * 92)
    for name, cands in primitives.items():
        reports = score_both_guardrails(cands, agent_factory, model_label=name)
        for board in ("public", "private"):
            r = reports[board]
            pc = ",".join(f"{k}×{v}" for k, v in sorted(r.predicate_counts.items())) or "-"
            print(f"{name:20} {board:9} {r.n_fired:>3}/{r.n:<3} {r.unique_cells:>6} "
                  f"{r.raw:>6.0f} {r.normalized:>7.3f}  {pc}")
        # dump a sample trace from each board for compliance debugging
        _dump_sample(f"{name}/public", reports["public"])
        _dump_sample(f"{name}/private", reports["private"])
        print()


if __name__ == "__main__":
    main()
