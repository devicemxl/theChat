"""Parser de la respuesta del agente de ingesta.

A diferencia del parser del chat, este NO es streaming — la ingesta es un
proceso en lote y no necesita feedback en vivo. Se llama una vez con la
respuesta completa y devuelve un IngestOutput estructurado.

Formato esperado (ver agent/ingest_prompts.py para el contrato completo):
    <CLASSIFY>kind</CLASSIFY>
    <EMIT_UNIT>...</EMIT_UNIT>  (0..N)
    <EMIT_WHOLE>...</EMIT_WHOLE>  (0..1)
    <EMIT_SUMMARY>...</EMIT_SUMMARY>  (0..1)
    <EMIT_TAGS>a, b, c</EMIT_TAGS>  (0..1)
    <DONE/>
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


VALID_KINDS = frozenset({"index", "diagram", "article", "code"})


def _tag_re(name: str) -> re.Pattern:
    return re.compile(rf"<{name}>(.*?)</{name}>", re.DOTALL)


def _extract_first(text: str, tag: str) -> str | None:
    m = _tag_re(tag).search(text)
    return m.group(1).strip() if m else None


def _extract_all(text: str, tag: str) -> list[str]:
    return [m.group(1).strip() for m in _tag_re(tag).finditer(text)]


@dataclass
class IngestOutput:
    kind: str
    units: list[str] = field(default_factory=list)
    whole: str | None = None
    summary: str | None = None
    tags: list[str] = field(default_factory=list)
    raw_response: str = ""
    
    def is_valid(self) -> bool:
        if self.kind not in VALID_KINDS:
            return False
        if not self.units and not self.whole:
            return False
        # Aceptar sin summary si hay units válidos: mejor un fragmento sin
        # resumen que perder el contenido entero por una truncación del LLM.
        return True
    
    @classmethod
    def fallback(cls, fragment: str, reason: str = "") -> "IngestOutput":
        """Fallback conservador: un solo unit con el fragmento crudo.

        Se usa cuando el modelo falla el protocolo. Preferimos indexar el
        fragmento entero como un único chunk antes que perder el contenido.
        """
        return cls(
            kind="article",
            units=[fragment],
            whole=None,
            summary=f"[FALLBACK] {fragment[:200]}",
            tags=["fallback", "unprocessed"],
            raw_response=reason,
        )

MAX_UNITS_PER_RESPONSE = 20
def parse_ingest_response(text: str) -> IngestOutput:
    units = _extract_all(text, "EMIT_UNIT")
    if len(units) > MAX_UNITS_PER_RESPONSE:
        units = units[:MAX_UNITS_PER_RESPONSE]
    return IngestOutput(
        kind=(_extract_first(text, "CLASSIFY") or "").lower(),
        units=units,
        whole=_extract_first(text, "EMIT_WHOLE"),
        summary=_extract_first(text, "EMIT_SUMMARY"),
        tags=_parse_tags(_extract_first(text, "EMIT_TAGS")),
        raw_response=text,
    )


def _parse_tags(tags_str: str | None) -> list[str]:
    if not tags_str:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags_str.split(","):
        t = raw.strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
            if len(out) >= 5:
                break
    return out