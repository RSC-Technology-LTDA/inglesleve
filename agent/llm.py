"""Chamada única à Claude API com saída estruturada (Pydantic)."""

import os
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")

T = TypeVar("T", bound=BaseModel)

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


class LLMError(RuntimeError):
    pass


def ask(system: str, prompt: str, output: Type[T], effort: str = "high") -> T:
    # fallbacks="default": se o modelo recusar, a API reexecuta em outro modelo indicado pela Anthropic.
    resp = client().beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=output,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        details = resp.stop_details.explanation if resp.stop_details else ""
        raise LLMError(f"Pedido recusado pelo modelo: {details}")
    if resp.stop_reason == "max_tokens":
        raise LLMError("Resposta cortada por max_tokens")
    if resp.parsed_output is None:
        raise LLMError("Resposta sem JSON válido")
    return resp.parsed_output
