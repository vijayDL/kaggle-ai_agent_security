"""Build Kaggle notebooks for the 2026-08-21 v22 batch (2 public + 3 private).
Same proven 3-cell scaffold as build_v18.py/build_v21.py (UUID cell ids,
repr()-escaped banner).

  python submission/build_v22.py
"""
from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSIONS = HERE / "versions"

VARIANTS: dict[str, tuple[str, str]] = {
    "v22-twomsg": (
        "attack_v22_twomsg.py",
        "PUBLIC bet: 2-message stacked candidate (each independently forged), real-board test of the message-stacking idea IDEA.md closed negative on a local GPU probe -- README's own lesson is local mispredicts real board",
    ),
    "v22-margin999": (
        "attack_v22_margin999.py",
        "PUBLIC bet: REPLAY_SAFE_FRAC 0.99->0.999 (decisive step vs v21-tightmargin's noisy 0.995), base=v17-edge",
    ),
    "v22-deleteonly": (
        "attack_v22_deleteonly.py",
        "PRIVATE bet: isolated DESTRUCTIVE_WRITE (fs.delete secret.txt alone, no post/mail stacking) -- clean undiluted signal, live-fire validated 5/5 behavioral",
    ),
    "v22-pureshare": (
        "attack_v22_pureshare.py",
        "PRIVATE bet: 100% SHARE (post carve-out mismatch), isolates v19-privmix's 20% share slice for a clean undiluted read",
    ),
    "v22-storewrite": (
        "attack_v22_storewrite.py",
        "PRIVATE bet: NEW primitive, WRITE-type UNTRUSTED_TO_ACTION via guardrail_rules.py's store wording carve-out mismatch, live-fire validated 6/6 behavioral",
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
