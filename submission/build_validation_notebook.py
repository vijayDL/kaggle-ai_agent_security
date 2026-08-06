"""Build a LOCAL-VALIDATION notebook (no submission spent) for a given variant.

Forks the community `aas-local-validation.ipynb`, which runs the OFFICIAL SDK
`evaluate_redteam` against BOTH real GGUFs (gpt_oss + gemma) under the public
Optimal guardrail on a Kaggle T4, producing an ABSOLUTE public score that the
community reports correlates with the public LB (cell 1 table). We keep every
generic cell verbatim and only:
  * neutralize the template's `!cp .../attack_pilkwang.py` cell (don't pull a
    stranger's attack), and
  * replace the commented example-attack cell with OUR attack.py inlined, with
    the variant's `_PLAN` substituted and the same code_sha stamp as the
    submission notebook, so a local score is attributable to an exact source.

  python submission/build_validation_notebook.py v3_pure_p1 v7_multipost
  python submission/build_validation_notebook.py            # all variants

Output: submission/versions/validation/<label>__validate.ipynb
Attach the competition SDK + the two GGUF model datasets, GPU on, then Run All.
Set BUDGET_S lower in cell 3 for a quick smoke test (full 9000s => true score).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from build_notebook import BUILD_TAG, VARIANTS, _attack_src_for  # reuse the substitution

import hashlib

HERE = Path(__file__).resolve().parent
KAGGLE_ROOT = HERE.parent
TEMPLATE = KAGGLE_ROOT / "aas-local-validation.ipynb"
OUT_DIR = HERE / "versions" / "validation"


def _find_cell(cells: list[dict], needle: str) -> int:
    for i, c in enumerate(cells):
        if c.get("cell_type") == "code" and needle in "".join(c.get("source", [])):
            return i
    raise SystemExit(f"template cell containing {needle!r} not found")


def _attack_write_cell(label: str, code_sha: str, attack_code: str) -> str:
    stamp = (f"=== VALIDATION VERSION: {label} | build={BUILD_TAG} "
             f"| code_sha={code_sha} ===")
    # Inline our attack.py exactly as the submission notebook does (r'''...''').
    return (
        f"# --- OUR attack.py ({label}) inlined for local validation -----------------\n"
        "ATTACK_CODE = r'''\n" + attack_code + "'''\n"
        "ATTACK_PATH.write_text(ATTACK_CODE, encoding='utf-8')\n"
        f"print({stamp!r})\n"
        "print('Wrote attack file:', ATTACK_PATH, '|', len(ATTACK_CODE), 'chars')\n"
    )


def build(label: str) -> Path:
    if "'''" in TEMPLATE.read_text():
        pass  # template may contain ''' in markdown; we only touch code cells
    nb = json.loads(TEMPLATE.read_text())
    cells = nb["cells"]

    plan, _desc = VARIANTS[label]
    attack_code = _attack_src_for(plan, label)
    if "'''" in attack_code:
        raise SystemExit("attack.py contains ''' which breaks the r'''...''' wrapper")
    code_sha = hashlib.sha256(attack_code.encode()).hexdigest()[:8]

    # 1) Neutralize the template's "copy a stranger's attack" cell.
    cp_idx = _find_cell(cells, "attack_pilkwang")
    cells[cp_idx]["source"] = [
        "# (disabled) template pulled another user's attack here; we inline ours below.\n",
        "print('using inlined attack.py — skipping template cp')\n",
    ]

    # 2) Replace the commented example-attack cell with our real inlined attack.
    ex_idx = _find_cell(cells, "ATTACK_PATH.write_text")
    cells[ex_idx]["source"] = _attack_write_cell(label, code_sha, attack_code).splitlines(
        keepends=True
    )

    nb.setdefault("metadata", {})["aas_version"] = {
        "label": label, "build": BUILD_TAG, "code_sha": code_sha, "kind": "validation",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{label}__validate.ipynb"
    out.write_text(json.dumps(nb, indent=1))
    print(f"  {label}: {out.relative_to(HERE)}  sha={code_sha}")
    return out


def main() -> None:
    if not TEMPLATE.exists():
        raise SystemExit(f"missing template: {TEMPLATE}")
    want = sys.argv[1:] or list(VARIANTS)
    print("building local-validation notebooks in submission/versions/validation/ :")
    for label in want:
        if label not in VARIANTS:
            raise SystemExit(f"unknown variant {label!r}; known: {list(VARIANTS)}")
        build(label)
    print("Attach SDK + both GGUF datasets, GPU on, Run All. No submission spent.")


if __name__ == "__main__":
    main()
