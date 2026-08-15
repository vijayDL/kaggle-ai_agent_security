"""Build tracked, versioned Kaggle submission notebooks from submission/attack.py.

Each variant differs only in the candidate mix (_PLAN). We keep every version as a
separate file under submission/versions/ (never overwritten) so we can map each
Kaggle submission to the exact notebook that produced its score.

  python submission/build_notebook.py                # build ALL variants
  python submission/build_notebook.py v3_pure_p1     # build one variant

Record each version's Kaggle score in submission/versions/MANIFEST.md.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATTACK_PY = HERE / "attack.py"
VERSIONS = HERE / "versions"

# Each variant = a label -> (_PLAN list, one-line description). _PLAN is the only
# thing that changes; everything else (behavioral validation, replay-safe sizing,
# primitives) is shared from attack.py.
P1 = "P1"
VARIANTS: dict[str, tuple[list[str], str]] = {
    "v1_portfolio12": (
        ["P4", "P2", "P3", "P1", "P4", "P2", "P5", "P3"],
        "Original 12.5% P1 portfolio — the version that scored 4.890 public (Kaggle V2).",
    ),
    "v2_hybrid70": (
        [P1]*7 + ["P4", "P3", "P2"] + [P1]*7 + ["P4", "P3", "P5"],
        "70% P1 + 30% private tail (P4/P3-heavy). Public strength + private hedge.",
    ),
    "v3_pure_p1": (
        [P1],
        "100% P1 SECRET_MARKER — diagnostic to measure our fill's public ceiling vs the 90-notebook.",
    ),
    "vprobe_diag200": (
        ["P1"],
        "PROBE: 200 blind-emit single-post P1 with the DIAGNOSTIC intent-evasion prompt "
        "(marker + exfil intent hidden). Fast run. Confirms it fires on the real grader "
        "(~norm 49 = works) -> ready as a stronger private-bet full run. Costs 1 slot.",
    ),
    "vprobe_fwd200": (
        ["P1"],
        "PROBE: 200 blind-emit single-post P1 with the FORWARD intent-evasion prompt. Fast. "
        "Confirms real-grader firing of the second evasion style. Costs 1 slot.",
    ),
    "vprobe_p1m20": (
        ["P1M"],
        "DIAGNOSTIC PROBE: blind-emits only 20 P1M candidates (skips live fill), so the "
        "Kaggle run finishes in minutes. Tests whether multipost replay works at small "
        "scale. Completes -> hang is our sizing (too many cands). Hangs -> per-candidate "
        "replay or Kaggle-side. Expected score ~6 (20 cands x 4 posts). Costs 1 slot.",
    ),
    "vprobe_p1m200": (
        ["P1M"],
        "DIAGNOSTIC PROBE: blind-emits exactly 200 P1M candidates (skips live fill). Near "
        "the real fill scale, so it doubles as (a) a completion test and (b) a real sample. "
        "COMPLETES ~norm 50 (gpt_oss 66/gemma 34) -> multipost sound AND safe count >=200 -> "
        "final ~50+ (competitive with v3), and note replay TIME to extrapolate the safe ceiling. "
        "HANGS -> safe threshold <200; single-post v3 (52) wins. One slot, definitive.",
    ),
    "v10_multiturn": (
        ["P1M"],
        "MULTI-TURN P1M (N=6 one-post messages/candidate). Kills the single-message wander "
        "AND unlocks gemma past 2 posts. MEASURED fill @150s: +16% gpt_oss, +70% gemma, +36% "
        "combined over the single-message pool (73.085). Est. real ~95-100 -> the push toward "
        "the 114.6 target. Replay-SAFE (fits budget). THE NEW WORKHORSE.",
    ),
    "v13_pool_aggr": (
        ["P1M"],
        "SAFE >84: single-message pool (73.085) + aggressive sizing (+15% real) + our URLs "
        "already shorter than v20's. Both edges stacked over the competitor -> est ~84-88. Safe.",
    ),
    "v14_pool_n2": (
        ["P1M"],
        "SIGNAL HUNT: single-message N=2 + aggressive. Low context/candidate = fastest per post. "
        "Tests if fewer posts/candidate (less context accumulation) fills MORE candidates on T4.",
    ),
    "v15_pool_n7": (
        ["P1M"],
        "SIGNAL HUNT: single-message N=7 + aggressive (max posts/candidate within the 8-hop cap). "
        "Tests if wrap-up amortization dominates. With v13(N4)/v14(N2) = a real-board N-sweep.",
    ),
    "v12_multiturn_nook": (
        ["P1M"],
        "Multi-turn + no_OK (drop the 'answer OK' wrap-up: +116% gemma / +276% gpt_oss local "
        "replay throughput, same 6 posts/cand), baseline sizing. Isolates the no_OK lever.",
    ),
    "v11_multiturn_aggr": (
        ["P1M"],
        "MAX bet: multi-turn + no_OK + AGGRESSIVE sizing (SLOWEST_MULT 1.35, frac 0.92, fill "
        "0.95). Stacks all levers — multi-turn (+36%) + no_OK + v20 candidate-count trick. "
        "The path to 114.6+. 1.35 proven-safe by v20.",
    ),
    "v7_multipost": (
        ["P1M"],
        "100% P1M multipost SECRET_MARKER (S4 phrasing + compact _label + SHORT-DOMAIN POOL: "
        "combinatorial 1-char domains, no taper). gpt_oss 4.0 posts/cand, gemma 2.0. Two URL "
        "throughput wins over the original long-url engine: band 2M->0 (+83%@120s) and the pool "
        "(+15.9% gpt_oss/+5.8% gemma @300s over band-0, no taper at T4 depth). Cell collapse on "
        "gemma is score-irrelevant (no cell-dedup; posts dominate). THE PUBLIC WORKHORSE. Prior "
        "submissions: band-2M (crippled) and band-0 (bdc83c30); THIS sha adds the pool.",
    ),
    "v8_hybrid_multipost": (
        ["P1M"]*7 + ["P4", "P3", "P4B"] + ["P1M"]*7 + ["P4", "P3", "P4B"],
        "v2's hybrid with the P1 public slots upgraded to P1M multipost (70% exfil "
        "workhorse) + a tail (P4/P4B untrusted-burst + P3 floor). Best portfolio UNDER A "
        "PROVENANCE-ORIENTED private assumption (P1M survives provenance). CAVEAT: if the "
        "private guardrail SCANS the marker payload, the 70% P1M dies and only the ~30% "
        "tail (P4/P4B benign posts survive marker-scan; P3 clean email) carries it.",
    ),
    "v4_private_max": (
        ["P4B", "P4", "P3", "P2", "P4B", "P4", "P3", "P5", "P1", "P1"],
        "Private-optimized: P4-burst-heavy (weight-16 UNTRUSTED x many/finding) + P3 floor "
        "+ P2/P5, small P1. Maximizes the internal-harness private-proxy across H1/H2/H3.",
    ),
    "v5_injection": (
        ["P6", "P6", "P6", "P6", "P6", "P6", "P3", "P1", "P6", "P6", "P6", "P6", "P6", "P6", "P3", "P1"],
        "Injection-heavy (the intended vector): P6 indirect-injection + keyword-gap fires "
        "EXFIL+UNTRUSTED+DESTRUCTIVE on the real models across 283 distinct pages, + P3 floor "
        "+ a little P1 for the public row. Highest-diversity private-board bet.",
    ),
    "v6_combined": (
        # Hedge across ALL guardrail shapes in one submission:
        #   P6  -> best on H1-like (guardrail_rules) private guardrails (real-secret exfil)
        #   P4B -> best on H2 (taint) / H3 (DLP) private guardrails (benign UNTRUSTED, no secret)
        #   P3  -> guardrail-agnostic floor (fires everywhere)
        #   P1  -> the public row (+ lenient-private hedge)
        ["P6", "P4B", "P3", "P1", "P6", "P4", "P3", "P6", "P4B", "P1",
         "P6", "P4", "P3", "P6", "P4B", "P1", "P6", "P4", "P3", "P1"],
        "Combined all-guardrail hedge: P6 injection (H1) + P4-burst (H2/H3) + P3 floor + P1 "
        "public. One submission robust across every private-guardrail shape we've modeled.",
    ),
}

SETUP = """\
# --- Setup: make the competition's kaggle_evaluation package importable -------
import sys, glob
from pathlib import Path
sys.argv = [sys.argv[0]]
for candidate in glob.glob('/kaggle/input/**/kaggle_evaluation', recursive=True):
    root = str(Path(candidate).parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    print('Dataset root:', root)
    break
print('Setup complete')
"""

SERVE = """\
# --- Serve on competition rerun; else write a placeholder submission ----------
import os, csv
if os.getenv('KAGGLE_IS_COMPETITION_RERUN'):
    import kaggle_evaluation.jed_attack_134815.jed_attack_inference_server as server
    server.JEDAttackInferenceServer().serve()
else:
    with open('/kaggle/working/submission.csv', 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['Id', 'Score'])
        w.writerows([['gpt_oss_public', 0.0], ['gpt_oss_private', 0.0],
                     ['gemma_public', 0.0], ['gemma_private', 0.0]])
    print('placeholder submission.csv written. Set accelerator + Internet Off, then Submit.')
"""


def _code_cell(src: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": src.splitlines(keepends=True)}


# Diagnostic probe variants: label -> _PROBE_N (blind-emit exactly N candidates,
# skipping the live fill, so the whole Kaggle run finishes in minutes).
_PROBE_N_FOR: dict[str, int] = {
    "vprobe_p1m20": 20,
    "vprobe_p1m200": 200,
    "vprobe_diag200": 200,
    "vprobe_fwd200": 200,
}

# Per-variant engine-constant overrides (substituted into attack.py). Lets a variant
# flip an engine knob (e.g. multi-turn) without a separate primitive.
_ENGINE_OVERRIDE: dict[str, dict[str, object]] = {
    # Slot 1 (SAFE insurance): multi-turn WITH the OK wrap-up + baseline sizing. The
    # fully-validated version (fill test showed it completes + gains); clean multi-turn read.
    "v10_multiturn": {"_P1M_MULTITURN": 1, "_P1_MULTIPOST_N": 6},
    # Fast blind-emit probes of the intent-evasion prompts (marker + intent hidden),
    # to confirm they FIRE on the real grader before committing a full private-bet run.
    "vprobe_diag200": {"_P1_STYLE": "diagnostic"},
    "vprobe_fwd200": {"_P1_STYLE": "forward"},
    # Slot 2: multi-turn + no_OK (drop the wrap-up: +116% gemma / +276% gpt_oss local),
    # baseline sizing. Isolates the no_OK lever's real-board value vs v10.
    "v12_multiturn_nook": {"_P1M_MULTITURN": 1, "_P1_MULTIPOST_N": 6, "_P1M_MT_DROP_OK": 1},
    # Slot 3 (MAX bet): multi-turn + no_OK + AGGRESSIVE sizing (SLOWEST_MULT 1.35 proven
    # safe by v20; frac 0.85->0.92, fill 0.92->0.95). Stacks every lever -> path to 114.6+.
    "v11_multiturn_aggr": {"_P1M_MULTITURN": 1, "_P1_MULTIPOST_N": 6, "_P1M_MT_DROP_OK": 1,
                           "_REPLAY_SAFE_FRAC_CHEAP": 0.92, "_FILL_FRAC": 0.95,
                           "_SLOWEST_MULT": 1.35},
    # The RELIABLE path (proven by real scores, not local): our single-message pool
    # multipost (73.085) + AGGRESSIVE sizing (the competitor v20's edge; single-message +
    # SLOWEST_MULT 1.35 is proven to complete AND score 84 on the real board). NO multi-turn.
    "v13_pool_aggr": {"_P1M_MULTITURN": 0, "_P1_MULTIPOST_N": 4,
                      "_REPLAY_SAFE_FRAC_CHEAP": 0.92, "_FILL_FRAC": 0.95,
                      "_SLOWEST_MULT": 1.35},
    # Real-board N-sweep (same aggressive sizing, single-message) to map the throughput
    # optimum: posts-per-candidate amortization vs context-accumulation cost.
    "v14_pool_n2": {"_P1M_MULTITURN": 0, "_P1_MULTIPOST_N": 2,
                    "_REPLAY_SAFE_FRAC_CHEAP": 0.92, "_FILL_FRAC": 0.95, "_SLOWEST_MULT": 1.35},
    "v15_pool_n7": {"_P1M_MULTITURN": 0, "_P1_MULTIPOST_N": 7,
                    "_REPLAY_SAFE_FRAC_CHEAP": 0.92, "_FILL_FRAC": 0.95, "_SLOWEST_MULT": 1.35},
}


def _attack_src_for(plan: list[str], label: str) -> str:
    """Return attack.py source with its _PLAN (and, for probe variants, _PROBE_N)
    line substituted for this variant."""
    text = ATTACK_PY.read_text()
    if "'''" in text:
        raise SystemExit("attack.py contains ''' which breaks the r'''...''' wrapper")
    new_line = f"_PLAN = {plan!r}  # variant: {label}"
    text, n = re.subn(r"^_PLAN = .*$", new_line, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit("could not find the single-line `_PLAN = ...` to substitute")
    probe_n = _PROBE_N_FOR.get(label, 0)
    if probe_n:
        text, m = re.subn(r"^_PROBE_N = .*$", f"_PROBE_N = {probe_n}  # DIAGNOSTIC PROBE",
                          text, count=1, flags=re.MULTILINE)
        if m != 1:
            raise SystemExit("could not find the single-line `_PROBE_N = ...` to substitute")
    for const, val in _ENGINE_OVERRIDE.get(label, {}).items():
        text, m = re.subn(rf"^{re.escape(const)} = .*$", f"{const} = {val!r}  # variant: {label}",
                          text, count=1, flags=re.MULTILINE)
        if m != 1:
            raise SystemExit(f"could not substitute engine override `{const}` for {label}")
    return text


# Bump when the attack engine changes materially, so a version is identifiable
# beyond just its plan/label. Shown in the Kaggle run log + archived filename.
BUILD_TAG = "eng4-forge+1hop+mixsize"

_SHAS: dict[str, str] = {}
_VERS: dict[str, int] = {}

# Version ledger: label -> ordered list of unique code_shas ever built. Position (1-
# indexed) is the version number, so a `_verN` suffix on the generated notebook tracks
# the Kaggle upload version (each distinct engine = a new ver). Same code_sha always
# maps to the same ver (idempotent rebuilds). Seeded with the v7 Kaggle history so the
# current pool engine resolves to ver3 (ver1=band-2M, ver2=band-0, ver3=pool).
_LEDGER_PATH = VERSIONS / "VER_LEDGER.json"
_LEDGER_SEED: dict[str, list[str]] = {
    "v7_multipost": ["a104f1aa", "bdc83c30", "005667d5"],
}


def _load_ledger() -> dict[str, list[str]]:
    if _LEDGER_PATH.exists():
        return json.loads(_LEDGER_PATH.read_text())
    return {k: list(v) for k, v in _LEDGER_SEED.items()}


def _ver_for(ledger: dict[str, list[str]], label: str, code_sha: str) -> int:
    hist = ledger.setdefault(label, [])
    if code_sha not in hist:
        hist.append(code_sha)
    return hist.index(code_sha) + 1  # 1-indexed = Kaggle-style verN


_LEDGER = _load_ledger()


def build(label: str) -> Path:
    plan, desc = VARIANTS[label]
    attack_code = _attack_src_for(plan, label)
    p1 = plan.count("P1") + plan.count("P1M")  # exfil workhorse (single + multipost)
    p1pct = 100 * p1 // len(plan)
    # code_sha uniquely identifies the EXACT attack.py shipped (plan + engine), so
    # any Kaggle submission can be mapped back to its precise source (review §5).
    code_sha = hashlib.sha256(attack_code.encode()).hexdigest()[:8]
    _SHAS[label] = code_sha
    ver = _ver_for(_LEDGER, label, code_sha)   # 1-indexed, tracks Kaggle upload version
    _VERS[label] = ver
    versioned = f"{label}_ver{ver}"
    stamp = (f"=== SUBMISSION VERSION: {versioned} | build={BUILD_TAG} | code_sha={code_sha} "
             f"| P1={p1pct}% | plan_len={len(plan)} ===")

    write_cell = (
        f"# --- Write attack.py ({versioned}) to /kaggle/working -----------------------\n"
        "attack_code = r'''\n" + attack_code + "'''\n"
        "with open('/kaggle/working/attack.py', 'w') as f:\n"
        "    f.write(attack_code)\n"
        f"print({stamp!r})\n"
        f"print('attack.py written:', len(attack_code), 'chars')\n"
    )
    nb = {
        "cells": [_code_cell(SETUP), _code_cell(write_cell), _code_cell(SERVE)],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                    "name": "python3"},
                     "language_info": {"name": "python"},
                     "aas_version": {"label": label, "ver": ver, "build": BUILD_TAG,
                                     "code_sha": code_sha, "p1_pct": p1pct}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    VERSIONS.mkdir(exist_ok=True)
    # Primary output carries the _verN suffix (matches the Kaggle upload version); a
    # plain `<label>.ipynb` latest-pointer is also written for convenience/tooling.
    out = VERSIONS / f"{versioned}.ipynb"
    out.write_text(json.dumps(nb, indent=1))
    (VERSIONS / f"{label}.ipynb").write_text(json.dumps(nb, indent=1))
    # Immutable archive keyed by ver+code_sha so a submitted artifact is never lost.
    archive = VERSIONS / "archive"
    archive.mkdir(exist_ok=True)
    (archive / f"{versioned}__{code_sha}.ipynb").write_text(json.dumps(nb, indent=1))
    print(f"  {versioned}: {out.name}  sha={code_sha}  (P1 {p1}/{len(plan)} = {p1pct}%)  {desc}")
    return out


# Kaggle PUBLIC scores. IMPORTANT: the early scores were earned by EARLIER engine
# states (pre forge / fill-fix), so they do NOT map to the current code_sha. Record
# new results as "<score> @<code_sha>" so every score is attributable (review §5).
KAGGLE_PUBLIC = {
    "v1_portfolio12": "4.890 (old engine)",
    "v2_hybrid70": "19.060 (old engine)",
    "v3_pure_p1": "37.280 (old engine) -> 52.375 (forge+1hop single-post engine, 15h run)",
    "v4_private_max": "3.585 (old engine)",
    "v6_combined": "2.640 (old engine, 20% P1 private-hedge)",
    # v7_multipost REAL-BOARD results (all COMPLETED — multipost beats single-post):
    #   ver1 a104f1aa (band-2M crippled) = 66.315
    #   ver2 bdc83c30 (band-0 fixed)     = 70.740   (URL fix = +6.7% real)
    #   ver3 005667d5 (pool)             = pending (~72-76 est)
    # vs v3 single-post 52.375 -> multipost +35%. NOTE: local Blackwell % gains are
    # ~3-12x inflated vs the real T4 (band fix was +83% local @120s but +6.7% real).
    "v7_multipost": "66.315 @a104f1aa -> 70.740 @bdc83c30 (band-0) -> 73.085 @005667d5 (pool). BEST.",
    # MULTI-TURN branch UNDERPERFORMED on the real board (local said +36%; real = -29%):
    "v12_multiturn_nook": "51.940 (multi-turn + no_OK) — BELOW the 73.085 single-message pool. "
                          "Local misled again. v10 (multi-turn+OK) pending to isolate MT vs no_OK.",
    # Competitor public: v20 (single-message + aggressive sizing) = 84.165; top = 114.590.
    # Reliable path = our single-message pool + aggressive sizing (v13_pool_aggr).
}


def write_manifest() -> None:
    lines = ["# Submission versions", "",
             f"Engine build: **{BUILD_TAG}**. Each notebook prints "
             "`SUBMISSION VERSION: <label> | build=... | code_sha=...` on run and is archived "
             "immutably at `versions/archive/<label>__<sha>.ipynb`. Record scores as "
             "`<score> @<code_sha>` so they're attributable.", "",
             "| Version | ver | P1 % | code_sha | Description | Kaggle public | Kaggle private |",
             "|---|---|---|---|---|---|---|"]
    for label, (plan, desc) in VARIANTS.items():
        p1 = 100 * (plan.count("P1") + plan.count("P1M")) // len(plan)
        note = KAGGLE_PUBLIC.get(label, "—")
        sha = _SHAS.get(label, "—")
        ver = _VERS.get(label)
        vtag = f"v{ver}" if ver else "—"
        lines.append(f"| `{label}` | {vtag} | {p1}% | `{sha}` | {desc} | {note} | (hidden) |")
    lines += ["", "Private scores are hidden until the competition ends. "
              "Only v2 (old engine) was submitted recently; current-sha versions are unsubmitted."]
    (VERSIONS / "MANIFEST.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    want = sys.argv[1:] or list(VARIANTS)
    print("building versioned notebooks in submission/versions/ :")
    for label in want:
        if label not in VARIANTS:
            raise SystemExit(f"unknown variant {label!r}; known: {list(VARIANTS)}")
        build(label)
    _LEDGER_PATH.write_text(json.dumps(_LEDGER, indent=1))
    write_manifest()
    print("manifest: submission/versions/MANIFEST.md | ledger: submission/versions/VER_LEDGER.json")


if __name__ == "__main__":
    main()
