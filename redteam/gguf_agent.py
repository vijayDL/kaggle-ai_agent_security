"""Grader-exact GGUF agents: the SDK's own GgufModelServer loads the competition
GGUF in-process via llama-cpp-python and returns the SDK Gemma4/GPTOSS agent — the
identical path the Kaggle grader uses. We drop that agent into our existing
two-guardrail harness (score_candidates), so we score the REAL competition models
(gpt-oss-20b-Q4_K_M, gemma-4-26B-A4B-it-UD-Q4_K_M) under BOTH the public guardrail
and our private-guardrail proxies.

Runs inside the aas_harness container (llama-cpp-python + CUDA). Model paths come
from GPT_OSS_MODEL_PATH / GEMMA_MODEL_PATH env vars (set in docker-compose).
"""

from __future__ import annotations

from typing import Any

from kaggle_evaluation.jed_attack_134815 import gemma_model_server, gpt_oss_model_server
from kaggle_evaluation.jed_attack_134815.gguf_model_server import GgufModelServer

_SPECS = {
    "gpt_oss": gpt_oss_model_server.SPEC,
    "gemma": gemma_model_server.SPEC,
}


def build_gguf_server(model_name: str) -> GgufModelServer:
    """Load the competition GGUF for `model_name` ('gpt_oss'|'gemma') in-process."""
    if model_name not in _SPECS:
        raise ValueError(f"unknown model {model_name!r}; expected one of {list(_SPECS)}")
    server = GgufModelServer(_SPECS[model_name])
    server.load_model()
    return server


def agent_factory_for(server: GgufModelServer):
    """A zero-arg factory returning an SDK agent backed by the loaded GGUF.

    The backend (llama_cpp.Llama) is shared/stateless; each call returns a fresh
    agent wrapper — matches how our harness builds one agent per env."""
    return lambda: server._load_agent()  # noqa: SLF001 (the community harness uses this too)


def unload(server: GgufModelServer) -> None:
    try:
        server.unload()
    except Exception:
        pass
    try:
        import gc
        gc.collect()
    except Exception:
        pass
