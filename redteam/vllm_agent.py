"""Wire a local vLLM OpenAI-compatible endpoint into the SDK agent loop.

The SDK's ``LlamaCppChatTemplateBackend`` already does exactly what we need: it
takes an ``HFGenerationRequest`` (rendered messages + tools), calls
``llm.create_chat_completion(**kwargs)``, and expects an OpenAI chat-completion
dict back. vLLM's ``/v1/chat/completions`` returns precisely that schema. So we
only provide a tiny ``llm`` shim whose ``create_chat_completion`` POSTs to the
endpoint, and reuse the SDK's message/tool conversion + response extraction
unchanged. ``Gemma4Agent`` then consumes the structured ``tool_calls`` via the
base agent's ``parsed_response`` path (agent.py:341).

Fidelity note: the chat template is applied *server-side* by vLLM (launched with
``--tool-call-parser gemma4 --reasoning-parser gemma4 enable_thinking=false``).
This is the fast-iteration path; parity-critical runs should cross-check against
the SDK's in-process ``build_gemma4_backend`` (see WINNING-PLAN Pillar 0).
"""

from __future__ import annotations

import json
from typing import Any

import requests

from aicomp_sdk.agents.gemma4_agent import Gemma4Agent
from aicomp_sdk.agents.gpt_oss_agent import GPTOSSAgent
from aicomp_sdk.agents.hf_chat_template.backends.llama_cpp import (
    LlamaCppChatTemplateBackend,
)
from aicomp_sdk.agents.hf_chat_template.types import HFBackendConfig

DEFAULT_BASE_URL = "http://localhost:47821/v1"
DEFAULT_MODEL = "gemma-4-31B-it-NVFP4"

# GPT-OSS co-hosted on the Blackwell (GPU 0); Harmony template + tool calls applied
# server-side by vLLM (--reasoning-parser openai_gptoss --tool-call-parser openai).
GPTOSS_BASE_URL = "http://localhost:47823/v1"
GPTOSS_MODEL = "gpt-oss-20b"


class VLLMChatClient:
    """Minimal ``create_chat_completion`` shim over an OpenAI-compatible server.

    Mirrors the subset of the llama.cpp ``Llama`` interface that
    ``LlamaCppChatTemplateBackend._build_completion_kwargs`` produces:
    ``messages``, ``max_tokens``, ``temperature``, and ``tools``.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 120.0,
        max_retries: int = 4,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        # Extra top-level request fields merged into every call (e.g.
        # chat_template_kwargs for gpt-oss reasoning_effort).
        self.extra_body = dict(extra_body or {})
        self._session = requests.Session()

    def create_chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model}
        payload.update(self.extra_body)
        payload.update(kwargs)
        # vLLM wants tool_choice when tools are present; auto matches the grader's
        # "model decides" behavior.
        if payload.get("tools") and "tool_choice" not in payload:
            payload["tool_choice"] = "auto"
        body = json.dumps(payload)
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._session.post(
                    f"{self.base_url}/chat/completions",
                    data=body,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                # Retry transient server-side errors (vLLM 500s under MTP/load).
                if resp.status_code >= 500:
                    last_err = requests.HTTPError(f"{resp.status_code} {resp.text[:200]}")
                    continue
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as err:
                last_err = err
        raise RuntimeError(f"vLLM request failed after {self.max_retries} attempts: {last_err}")

    def close(self) -> None:
        self._session.close()


def build_vllm_backend(
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    *,
    max_new_tokens: int = 256,
    timeout: float = 120.0,
    extra_body: dict[str, Any] | None = None,
) -> LlamaCppChatTemplateBackend:
    client = VLLMChatClient(base_url, model, timeout=timeout, extra_body=extra_body)
    config = HFBackendConfig(
        model_id=model,
        # Greedy to match deterministic replay. do_sample=False -> the llama.cpp
        # backend sets temperature=0.0 for us.
        generation_kwargs={"do_sample": False},
        max_new_tokens=max_new_tokens,
    )
    return LlamaCppChatTemplateBackend(llm=client, config=config, supports_tools=True)


def build_gemma_vllm_agent(
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    *,
    max_new_tokens: int = 256,
    timeout: float = 120.0,
) -> Gemma4Agent:
    """A ``Gemma4Agent`` whose generation is served by the vLLM endpoint."""
    backend = build_vllm_backend(
        base_url, model, max_new_tokens=max_new_tokens, timeout=timeout
    )
    return Gemma4Agent(backend)


def build_gptoss_vllm_agent(
    base_url: str = GPTOSS_BASE_URL,
    model: str = GPTOSS_MODEL,
    *,
    max_new_tokens: int = 512,
    timeout: float = 180.0,
    reasoning_effort: str | None = "low",
) -> GPTOSSAgent:
    """A ``GPTOSSAgent`` served by the co-hosted gpt-oss vLLM endpoint.

    Uses the default (plain-OpenAI) request builder, so the SDK sends role/content
    + tool messages and vLLM applies the Harmony template server-side; the base
    agent then consumes the structured tool_calls vLLM returns. max_new_tokens is
    larger than Gemma's because gpt-oss emits an analysis (reasoning) channel.

    reasoning_effort='low' (default) shrinks the analysis channel — this cuts the
    redundant web.search spam and the `commentary`-channel tool-name mangling that
    gpt-oss otherwise produces on multi-hop tool sequences."""
    extra_body = (
        {"chat_template_kwargs": {"reasoning_effort": reasoning_effort}}
        if reasoning_effort
        else None
    )
    backend = build_vllm_backend(
        base_url, model, max_new_tokens=max_new_tokens, timeout=timeout,
        extra_body=extra_body,
    )
    return GPTOSSAgent(backend)
