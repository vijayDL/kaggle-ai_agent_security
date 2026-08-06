"""Robustness matrix: each primitive scored under each guardrail hypothesis.

Shows which primitives survive which *kind* of stricter private guardrail — the
core Pillar A question. Cells report normalized score (and fired/n).

Run:  .venv/bin/python -m redteam.run_robustness [N]
"""

from __future__ import annotations

import sys

from redteam.harness import score_candidates
from redteam.guardrails_hyp import H2_read_taint, H3_data_scan
from redteam.primitives import (
    p1_secret_marker,
    p2_read_dual_post,
    p3_confused_deputy,
    p4_untrusted_share,
)
from redteam.vllm_agent import build_gemma_vllm_agent
from aicomp_sdk.attacks.baselines.guardrail_rules import Guardrail as RulesGuardrail
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    def af():
        return build_gemma_vllm_agent()

    primitives = {
        "P1_marker": p1_secret_marker(n),
        "P2_hyphen": p2_read_dual_post(n, hyphen=True),
        "P3_deputy": p3_confused_deputy(n),
        "P4_untrust": p4_untrusted_share(n),
    }
    guardrails = {
        "Optimal(pub)": OptimalGuardrail,
        "H1_rules": RulesGuardrail,
        "H2_readtaint": H2_read_taint,
        "H3_datascan": H3_data_scan,
    }

    # header
    cols = list(guardrails)
    print(f"\n{'primitive':12} | " + " | ".join(f"{c:>14}" for c in cols))
    print("-" * (14 + len(cols) * 17))
    results = {}
    for pname, cands in primitives.items():
        row = []
        for gname, gfac in guardrails.items():
            r = score_candidates(cands, af, gfac, label=f"{pname}/{gname}")
            results[(pname, gname)] = r
            row.append(f"{r.normalized:5.2f} ({r.n_fired}/{r.n})")
        print(f"{pname:12} | " + " | ".join(f"{c:>14}" for c in row))

    # portfolio (union) private-side view: best-case if the real private guardrail
    # is any single one of the hypotheses, what does the WHOLE portfolio score?
    print("\nPer-guardrail PORTFOLIO normalized (all primitives combined):")
    for gname in cols:
        raw = sum(results[(p, gname)].raw for p in primitives)
        # normalized of summed raw (diversity across primitives assumed disjoint here;
        # this is an upper-ish estimate — exact requires disjoint domains, see note).
        from aicomp_sdk.scoring import ATTACK_ELITE_RAW
        norm = min(1000.0, raw / ATTACK_ELITE_RAW * 1000.0)
        fired = sum(results[(p, gname)].n_fired for p in primitives)
        total = sum(results[(p, gname)].n for p in primitives)
        print(f"  {gname:14} raw={raw:6.0f}  norm={norm:6.3f}  fired={fired}/{total}")


if __name__ == "__main__":
    main()
