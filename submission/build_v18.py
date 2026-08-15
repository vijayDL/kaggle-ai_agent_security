"""Build Kaggle notebooks for the v18 chassis-based attack.py variants.

Wraps each submission/attack_v18_*.py (and attack_v17_edge.py) in the exact proven
3-cell scaffold from versions/v17-edge.ipynb (dataset-root setup -> write attack.py
-> serve). One notebook per label; never overwrites an existing versions/*.ipynb
(matches the "artifacts are immutable" rule in STATE.md / old MANIFEST.md).

  python submission/build_v18.py
"""

from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = HERE / "versions"

# label -> (source .py, one-line description for the print banner)
VARIANTS: dict[str, tuple[str, str]] = {
    "v18-multipost-n4": (
        "attack_v18_multipost_n4.py",
        "PUBLIC bet: gpt_oss Harmony-forge multipost N=4 (isolated), base=v17-edge 88.920",
    ),
    "v18-multipost-n6": (
        "attack_v18_multipost_n6.py",
        "PUBLIC bet: gpt_oss Harmony-forge multipost N=6 dose-response, base=v17-edge 88.920",
    ),
    "v18-probehops": (
        "attack_v18_probehops.py",
        "PUBLIC bet: 1-hop fill probing isolated, base=v17-edge 88.920",
    ),
    "v18-multipost-n7": (
        "attack_v18_multipost_n7.py",
        "PUBLIC bet: gpt_oss Harmony-forge multipost N=7 (1-hop slack), base=v17-edge 88.920",
    ),
    "v18-multipost-n5": (
        "attack_v18_multipost_n5.py",
        "PUBLIC bet: gpt_oss Harmony-forge multipost N=5, midpoint N4/N6, base=v17-edge 88.920",
    ),
    "v18-blindemit": (
        "attack_v18_blindemit.py",
        "PUBLIC bet: calibrate 30 live, then blind-emit toward HARD_N_CAP=2000 if fire rate>=0.85",
    ),
    "v18-blindemit-stack": (
        "attack_v18_blindemit_stack.py",
        "PUBLIC bet: blind-emit chassis + P1 http.post stacked with P3 email.send in one candidate",
    ),
    "v18-p3-deputy-blindemit": (
        "attack_v18_p3_deputy_blindemit.py",
        "PRIVATE bet: CONFUSED_DEPUTY floor, blind-emit extension of v18-p3-deputy (22.965 public)",
    ),
    "v18-p2-realsecret-blindemit": (
        "attack_v18_p2_realsecret_blindemit.py",
        "PRIVATE bet: read->dual-post, blind-emit extension of v18-p2-realsecret (22.860 public)",
    ),
    "v18-p6-injection": (
        "attack_v18_p6_injection.py",
        "PRIVATE bet: indirect prompt injection via fixture pages, NEW primitive, blind-emit-capable",
    ),
    "v18-gemma-forge": (
        "attack_v18_gemma_forge.py",
        "PUBLIC bet: Gemma-native forge on fast row, isolated, base=v17-edge 88.920",
    ),
    "v18-no-ok": (
        "attack_v18_no_ok.py",
        "PUBLIC bet: drop wrap-up 'answer OK' instruction everywhere, isolated",
    ),
    "v18-terse-ok": (
        "attack_v18_terse_ok.py",
        "PUBLIC bet: shorten wrap-up to 'Then reply OK.' everywhere, isolated",
    ),
    "v18-gemma-forge-no-ok": (
        "attack_v18_gemma_forge_no_ok.py",
        "PUBLIC bet: gemma-forge + no-ok combined (classification phase + fast row only)",
    ),
    "v18-p3-deputy": (
        "attack_v18_p3_deputy.py",
        "PRIVATE bet: CONFUSED_DEPUTY email floor, new primitive",
    ),
    "v18-p2-realsecret": (
        "attack_v18_p2_realsecret.py",
        "PRIVATE bet: read secret.txt -> dual-post (marker + real secret), new primitive",
    ),
}

_SETUP_CELL = """import sys, glob
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

_SERVE_CELL = """import os, csv
if os.getenv('KAGGLE_IS_COMPETITION_RERUN'):
    import kaggle_evaluation.jed_attack_134815.jed_attack_inference_server as server
    server.JEDAttackInferenceServer().serve()
else:
    with open('/kaggle/working/submission.csv', 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['Id', 'Score'])
        w.writerows([['gpt_oss_public', 0.0], ['gpt_oss_private', 0.0], ['gemma_public', 0.0], ['gemma_private', 0.0]])
    print('placeholder submission.csv written. Set GPU T4 x2, Internet Off, then Submit.')
"""


def _code_cell(source: str) -> dict:
    # 2026-08-10: EVERY cell in the known-working v17-edge.ipynb carries a UUID "id"
    # field; the first build_v18.py run omitted it and all 5 notebooks it produced
    # failed on Kaggle with a system error. nbformat 4.4 doesn't strictly require
    # cell ids, but Kaggle's own ingestion evidently does -- match the proven
    # scaffold exactly rather than the bare spec minimum.
    return {
        "id": str(uuid.uuid4()),
        "cell_type": "code",
        "metadata": {},
        "outputs": [],
        "execution_count": None,
        "source": source,
    }


def build_one(label: str, py_file: str, description: str) -> Path:
    out_path = VERSIONS / f"{label}.ipynb"
    if out_path.exists():
        print(f"SKIP (exists): {out_path.name}")
        return out_path

    attack_src = (HERE / py_file).read_text()
    b64 = base64.b64encode(attack_src.encode()).decode()
    # 2026-08-13: use repr() for the banner message instead of manual single-quote
    # wrapping -- a `description` containing an apostrophe or single-quoted phrase
    # (e.g. "drop wrap-up 'answer OK'") used to break the generated print() statement
    # with a SyntaxError on Kaggle's side (attack_v18_no_ok.py / attack_v18_terse_ok.py
    # both hit this). repr() escapes correctly regardless of what's in the string.
    banner = f"=== SUBMISSION VERSION: {label} | {description} ==="
    write_cell = (
        f"_B64 = {b64!r}\n"
        "import base64\n"
        f"print({banner!r})\n"
        "open('/kaggle/working/attack.py','wb').write(base64.b64decode(_B64))\n"
        "print('attack.py written')\n"
    )

    nb = {
        "cells": [
            _code_cell(_SETUP_CELL),
            _code_cell(write_cell),
            _code_cell(_SERVE_CELL),
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "aas_version": {"label": label, "source_file": py_file},
        },
        "nbformat": 4,
        "nbformat_minor": 4,
    }
    out_path.write_text(json.dumps(nb, indent=1))
    print(f"WROTE: {out_path.name} ({len(attack_src)} chars source)")
    return out_path


if __name__ == "__main__":
    for label, (py_file, desc) in VARIANTS.items():
        build_one(label, py_file, desc)
