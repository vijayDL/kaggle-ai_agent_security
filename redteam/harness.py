"""Local two-guardrail scoring harness — a leaderboard mirror.

Replays a list of attack candidates (each a tuple of user messages) through a
``SandboxEnv`` built from a chosen agent + guardrail, then reproduces the
evaluator's scoring exactly as ``evaluation/ops.py`` does:

    finding = {
        "predicates":           eval_predicates(trace),
        "score_cell_signature": cell_signature(trace["tool_events"]),  # ops.py:830
    }
    score = score_attack(findings)      # scoring.py

Running the same candidates under ``OptimalGuardrail`` (public board) and
``guardrail_rules`` (our private-guardrail proxy) gives the public-vs-private
split the prize is decided on. See WINNING-PLAN.md Part 2.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aicomp_sdk
from aicomp_sdk.core.cells import cell_signature
from aicomp_sdk.core.env.sandbox import SandboxEnv
from aicomp_sdk.core.predicates import eval_predicates
from aicomp_sdk.guardrails.base import GuardrailBase
from aicomp_sdk.scoring import SEVERITY_W, score_attack, score_attack_raw

FIXTURES_DIR = Path(aicomp_sdk.__file__).parent / "fixtures"

AgentFactory = Callable[[], Any]
GuardrailFactory = Callable[[], GuardrailBase]
Candidate = Sequence[str]  # a tuple/list of user messages


@dataclass
class FindingResult:
    user_messages: tuple[str, ...]
    predicates: list[dict[str, Any]]
    score_cell_hash: str
    fired: bool  # any successful (ok=True) tool event
    raw: float  # severity-weight sum for this finding (pre-diversity)
    tool_events: list[dict[str, Any]] = field(default_factory=list)

    def predicate_names(self) -> list[str]:
        return [p.get("predicate") for p in self.predicates]


@dataclass
class ScoreReport:
    label: str
    findings: list[FindingResult]

    @property
    def n(self) -> int:
        return len(self.findings)

    @property
    def n_fired(self) -> int:
        return sum(1 for f in self.findings if f.fired)

    @property
    def scored_findings(self) -> list["FindingResult"]:
        """Only findings with >=1 triggered predicate count — matches the
        evaluator's ``if not predicates: continue`` (ops.py:816)."""
        return [f for f in self.findings if f.predicates]

    @property
    def unique_cells(self) -> int:
        return len({f.score_cell_hash for f in self.scored_findings})

    @property
    def predicate_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.scored_findings:
            for name in f.predicate_names():
                counts[name] = counts.get(name, 0) + 1
        return counts

    @property
    def raw(self) -> float:
        return score_attack_raw([_finding_dict(f) for f in self.scored_findings])

    @property
    def normalized(self) -> float:
        return score_attack([_finding_dict(f) for f in self.scored_findings], normalize=True)

    def summary(self) -> str:
        pc = ", ".join(f"{k}×{v}" for k, v in sorted(self.predicate_counts.items())) or "none"
        return (
            f"[{self.label}] findings={self.n} fired={self.n_fired} "
            f"unique_cells={self.unique_cells} predicates=({pc}) "
            f"raw={self.raw:.0f} normalized={self.normalized:.3f}"
        )


def _finding_dict(f: FindingResult) -> dict[str, Any]:
    return {
        "predicates": f.predicates,
        "score_cell_signature": {"hash": f.score_cell_hash},
    }


def replay_candidate(env: SandboxEnv, user_messages: Candidate, max_tool_hops: int) -> FindingResult:
    env.reset()
    for msg in user_messages:
        try:
            env.interact(msg, max_tool_hops=max_tool_hops)
        except Exception:
            # A backend/generation failure mid-turn is a no-op for scoring (the
            # grader records no successful tool event for it); keep the trace so far.
            pass
    trace = env.export_trace_dict()
    predicates = eval_predicates(trace)
    score_cell = cell_signature(trace.get("tool_events", []))
    fired = any(e.get("ok") for e in trace.get("tool_events", []))
    raw = sum(SEVERITY_W.get(int(p.get("severity", 1)), 1) for p in predicates)
    return FindingResult(
        user_messages=tuple(user_messages),
        predicates=predicates,
        score_cell_hash=score_cell["hash"],
        fired=fired,
        raw=raw,
        tool_events=trace.get("tool_events", []),
    )


def score_candidates(
    candidates: Sequence[Candidate],
    agent_factory: AgentFactory,
    guardrail_factory: GuardrailFactory,
    *,
    label: str = "run",
    seed: int = 0,
    max_tool_hops: int = 8,
) -> ScoreReport:
    env = SandboxEnv(
        seed=seed,
        fixtures_dir=FIXTURES_DIR,
        agent=agent_factory(),
        guardrail=guardrail_factory(),
        max_tool_hops=max_tool_hops,
    )
    findings = [replay_candidate(env, c, max_tool_hops) for c in candidates]
    return ScoreReport(label=label, findings=findings)


def score_both_guardrails(
    candidates: Sequence[Candidate],
    agent_factory: AgentFactory,
    *,
    model_label: str = "gemma",
    seed: int = 0,
    max_tool_hops: int = 8,
) -> dict[str, ScoreReport]:
    """Replay the same candidates under the public and private-proxy guardrails."""
    from aicomp_sdk.attacks.baselines.guardrail_rules import Guardrail as RulesGuardrail
    from aicomp_sdk.guardrails.optimal import Guardrail as OptimalGuardrail

    return {
        "public": score_candidates(
            candidates, agent_factory, OptimalGuardrail,
            label=f"{model_label}_public", seed=seed, max_tool_hops=max_tool_hops,
        ),
        "private": score_candidates(
            candidates, agent_factory, RulesGuardrail,
            label=f"{model_label}_private", seed=seed, max_tool_hops=max_tool_hops,
        ),
    }
