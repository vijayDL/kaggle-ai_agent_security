"""Score each primitive across the INDEPENDENT guardrail hypotheses on a real model.

Metrics per cell (review-corrected): predicate hit-rate (fraction of candidates that
fire a SCORING predicate, not any tool event) and raw score / candidate. This is the
honest cross-hypothesis view: a primitive is a good private wager only if it holds up
across independent defenses, not just the correlated H1/H2/H3 proxies.

Run inside aas_harness:  python -m redteam.run_indep_matrix [model] [n]
"""

from __future__ import annotations

import sys

from redteam.gguf_agent import agent_factory_for, build_gguf_server, unload
from redteam.guardrails_indep import INDEP
from redteam.harness import score_candidates
from redteam.primitives import (
    p1_secret_marker,
    p2_read_dual_post,
    p3_confused_deputy,
    p4_burst,
    p4_untrusted_share,
    p5_untrusted_write,
)
from redteam.run_gguf_eval import _p6_injection
from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else "gemma"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    prims = {
        "P1_marker": p1_secret_marker(n),
        "P2_hyphen": p2_read_dual_post(n, hyphen=True),
        "P3_deputy": p3_confused_deputy(n),
        "P4_untrust": p4_untrusted_share(n),
        "P4B_burst": p4_burst(max(2, n // 2), n_posts=4),
        "P5_write": p5_untrusted_write(n),
        "P6_inject": _p6_injection(n),
    }
    guards = {"Optimal(pub)": OptimalGuardrail, **INDEP}
    cols = list(guards)

    server = build_gguf_server(model)
    try:
        af = agent_factory_for(server)
        print(f"\n### {model}: predicate-hit-rate | raw/candidate ###")
        print(f"{'primitive':11} | " + " | ".join(f"{c:>15}" for c in cols))
        print("-" * (13 + len(cols) * 18))
        for pname, cands in prims.items():
            row = []
            for gname, gfac in guards.items():
                r = score_candidates(cands, af, gfac, label=f"{pname}/{gname}")
                hit = len(r.scored_findings) / max(1, r.n)
                rpc = r.raw / max(1, r.n)
                row.append(f"{hit:.2f}|{rpc:4.1f}")
            print(f"{pname:11} | " + " | ".join(f"{c:>15}" for c in row))
        print("\n(hit = fraction firing a SCORING predicate; raw/candidate = raw score per candidate)")
    finally:
        unload(server)


if __name__ == "__main__":
    main()
