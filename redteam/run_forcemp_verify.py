"""Engine-level verification of forced-multipost-N3: run the actual AttackAlgorithm
fill against the live gpt_oss env, then replay a sample of the RETURNED candidates and
count http.post events per candidate. If ~3, the forge multipost is actually firing at
the engine level (not gated off like the prior split-latency version).

  docker compose run --rm aas_harness -m redteam.run_forcemp_verify [budget_s]
"""
from __future__ import annotations

import sys, time, importlib.util
from types import SimpleNamespace
sys.path.insert(0, "submission")

from redteam.gguf_agent import build_gguf_server, agent_factory_for, unload
from redteam.harness import FIXTURES_DIR
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.core.predicates import eval_predicates
from aicomp_sdk.scoring import SEVERITY_W
from aicomp_sdk.guardrails.optimal import Guardrail as Optimal


def load(path):
    spec = importlib.util.spec_from_file_location("eng", path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main() -> None:
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
    m = load("submission/attack_v18_forcemp3.py")
    PAY = m.PAYLOAD
    server = build_gguf_server("gpt_oss")
    try:
        af = agent_factory_for(server)
        env = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(), guardrail=Optimal(), max_tool_hops=8)
        algo = m.AttackAlgorithm()
        algo.config = {"replay_budget_s": 1e7, "replay_safe_frac": 0.99, "fill_budget_frac": 0.99}
        t0 = time.monotonic()
        cands = algo.run(env, SimpleNamespace(time_budget_s=budget, max_tool_hops=8))
        fill_s = time.monotonic() - t0
        print(f"\n### forced-multipost-N3 engine verify | gpt_oss | budget={budget:.0f}s ###", flush=True)
        print(f"returned {len(cands)} candidates in {fill_s:.0f}s", flush=True)
        # replay a sample, count posts/candidate + raw/candidate
        env2 = SandboxEnv(seed=0, fixtures_dir=FIXTURES_DIR, agent=af(), guardrail=Optimal(), max_tool_hops=8)
        posts, raws = [], []
        for c in list(cands)[:15]:
            env2.reset()
            for msg in c.user_messages:
                try: env2.interact(msg, max_tool_hops=8)
                except Exception: pass
            tr = env2.export_trace_dict()
            p = sum(1 for e in tr.get("tool_events", [])
                    if e.get("ok") is True and e.get("name") == "http.post"
                    and PAY in str((e.get("args") or {}).get("data", "")))
            preds = eval_predicates(tr)
            r = sum(SEVERITY_W.get(int(x.get("severity", 1)), 1) for x in preds) + (2 if preds else 0)
            posts.append(p); raws.append(r)
        n = len(posts) or 1
        print(f"sample of {len(posts)}: mean posts/candidate = {sum(posts)/n:.2f} | mean raw/candidate = {sum(raws)/n:.1f}", flush=True)
        print(f"(plain single-post baseline = 1 post, 18 raw/candidate)", flush=True)
    finally:
        unload(server)


if __name__ == "__main__":
    main()
