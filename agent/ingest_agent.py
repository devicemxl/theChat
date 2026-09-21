"""Agente de ingesta: una llamada al LLM por fragmento.

No es iterativo (a diferencia del chat agent). El modelo ve el fragmento,
lo clasifica, y emite los tags correspondientes en una sola pasada. El
runtime parsea y devuelve un IngestOutput listo para persistir.
"""

from __future__ import annotations

from typing import Callable

from agent.ingest_parser import IngestOutput, parse_ingest_response
from agent.ingest_prompts import INGEST_SYSTEM_PROMPT


# Firma del cliente LLM: recibe mensajes, devuelve la respuesta completa.
LLMCall = Callable[[list[dict]], str]


class IngestAgent:
    """Procesa fragmentos con el LLM y devuelve IngestOutput."""

    def __init__(self, llm_call: LLMCall, fallback_enabled: bool = True):
        self.llm_call = llm_call
        self.fallback_enabled = fallback_enabled

    def process(self, fragment: str, filename: str) -> IngestOutput:
        """Clasifica y trocea un fragmento.

        Nunca lanza si fallback_enabled=True: en caso de error del LLM o
        protocolo roto, devuelve un IngestOutput.fallback con el fragmento
        crudo como un único unit.
        """
        messages = [
            {"role": "system", "content": INGEST_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Fragment from file '{filename}':\n\n{fragment}",
            },
        ]

        try:
            raw = self.llm_call(messages)
            output = parse_ingest_response(raw)
            if not output.is_valid():
                raise ValueError(
                    f"invalid response: kind={output.kind!r} "
                    f"units={len(output.units)} summary={bool(output.summary)}"
                )
            return output
        except Exception as e:
            if self.fallback_enabled:
                return IngestOutput.fallback(fragment, reason=str(e))
            raise