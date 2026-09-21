"""Streaming parser for <PLAN> blocks emitted by the LLM.

The parser consumes text chunks (as they arrive from a streaming API) and
extracts a <PLAN>...</PLAN> block, one task per line. It is deliberately
strict about the tag case and format: if the model deviates, the parser
falls back to "no plan detected" and the entire output is treated as the
final response. That keeps the failure mode simple.

Why not regex over the full response? Because we need to react in real time
to update the UI ("Thinking... Planning... line 1, line 2...") while the
model is still generating. Regex over a complete string can't do that.

Task kinds currently supported:
    SEARCH: <query>
Future kinds (WRITE, FETCH, CODE) plug into _parse_task_line without
touching the state machine.
"""

from __future__ import annotations

import re

from dataclasses import dataclass, field
from enum import Enum


PLAN_OPEN = "<PLAN>"
PLAN_CLOSE = "</PLAN>"


# ---------------------------------------------------------------------------
# Task representation
# ---------------------------------------------------------------------------

class TaskKind(Enum):
    SEARCH = "SEARCH"


@dataclass
class Task:
    kind: TaskKind
    payload: str
    raw_line: str


# ---------------------------------------------------------------------------
# Parser events (consumed by the runner, which maps them to UI events)
# ---------------------------------------------------------------------------

@dataclass
class ParseTextChunk:
    """Text that belongs to the final response (outside any plan)."""
    text: str


@dataclass
class ParsePlanOpened:
    pass


@dataclass
class ParsePlanLine:
    raw: str
    task: Task | None
    invalid_reason: str = ""


@dataclass
class ParsePlanClosed:
    pass


ParserEvent = ParseTextChunk | ParsePlanOpened | ParsePlanLine | ParsePlanClosed


# ---------------------------------------------------------------------------
# Internal states
# ---------------------------------------------------------------------------

_ST_IDLE       = 0   # Before deciding: plan or text?
_ST_TEXT       = 1   # Definitely text (no plan detected)
_ST_IN_PLAN    = 2   # Between <PLAN> and </PLAN>
_ST_AFTER_PLAN = 3   # After </PLAN> (post-plan text — usually empty)


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------

class PlanStreamParser:
    """Stateful parser. Feed chunks in order; call finish() at stream end."""

    def __init__(self) -> None:
        self._state = _ST_IDLE
        self._header_buf = ""     # accumulates potential <PLAN> prefix
        self._tail_buf = ""
        self._plan_buf = ""       # accumulates plan body (until close tag)
        self._post_plan_buf = ""  # text after </PLAN>

        self._tasks: list[Task] = []
        self._invalid_lines: list[str] = []
        self._plan_opened = False
        self._plan_closed = False


    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def had_plan(self) -> bool:
        return self._plan_opened

    @property
    def plan_closed(self) -> bool:
        return self._plan_closed

    @property
    def malformed(self) -> bool:
        """True if <PLAN> was opened but never closed."""
        return self._plan_opened and not self._plan_closed

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks)

    @property
    def invalid_lines(self) -> list[str]:
        return list(self._invalid_lines)

    @property
    def post_plan_text(self) -> str:
        return self._post_plan_buf

    # ------------------------------------------------------------------
    # Feeding
    # ------------------------------------------------------------------

    def feed(self, chunk: str) -> list[ParserEvent]:
        """Consume a chunk, return all events it produces."""
        events: list[ParserEvent] = []
        text_buf = ""

        for ch in chunk:
            if self._state == _ST_IDLE:
                # Skip leading whitespace — plans often start with "\n<PLAN>".
                if not self._header_buf and ch.isspace():
                    continue
                self._header_buf += ch

                if self._header_buf == PLAN_OPEN:
                    if text_buf:
                        events.append(ParseTextChunk(text=text_buf))
                        text_buf = ""
                    self._plan_opened = True
                    self._state = _ST_IN_PLAN
                    self._header_buf = ""
                    events.append(ParsePlanOpened())
                elif PLAN_OPEN.startswith(self._header_buf):
                    # Still a viable prefix — keep waiting.
                    pass
                else:
                    # Diverged from <PLAN>. Everything is text.
                    text_buf += self._header_buf
                    self._header_buf = ""
                    self._state = _ST_TEXT

            elif self._state == _ST_TEXT:
                self._tail_buf += ch
                # Comprobar <PLAN> ANTES de emitir. Si está, entramos en modo
                # plan y descartamos el tail buffer completo (incluye los
                # chars de <PLAN>, que no deben llegar al usuario).
                if self._tail_buf.endswith(PLAN_OPEN):
                    prefix = self._tail_buf[: -len(PLAN_OPEN)]
                    if prefix:
                        events.append(ParseTextChunk(text=prefix))
                    self._tail_buf = ""
                    self._plan_opened = True
                    self._state = _ST_IN_PLAN
                    events.append(ParsePlanOpened())
                else:
                    # Emitir todo excepto los últimos 5 chars (que podrían
                    # ser el inicio de <PLAN>).
                    while len(self._tail_buf) > len(PLAN_OPEN) - 1:
                        events.append(ParseTextChunk(text=self._tail_buf[0]))
                        self._tail_buf = self._tail_buf[1:]

            elif self._state == _ST_IN_PLAN:
                self._plan_buf += ch
                # Only check the close tag on '>' to keep it O(n).
                if ch == ">" and self._plan_buf.endswith(PLAN_CLOSE):
                    body = self._plan_buf[: -len(PLAN_CLOSE)]
                    # Normalizar: forzar salto de línea antes de cada SEARCH:
                    # por si el modelo los puso en la misma línea.
                    body = re.sub(r"[ \t]*SEARCH:", "\nSEARCH:", body).strip()
                    for line in body.split("\n"):
                        self._handle_plan_line(line, events)
                    self._plan_buf = ""
                    self._plan_closed = True
                    self._state = _ST_AFTER_PLAN
                    events.append(ParsePlanClosed())
                elif "\n" in self._plan_buf:
                    line, rest = self._plan_buf.split("\n", 1)
                    self._plan_buf = rest
                    self._handle_plan_line(line, events)

            elif self._state == _ST_AFTER_PLAN:
                self._post_plan_buf += ch

        # text_buf ya no se usa: los chars de _ST_TEXT se emiten arriba
        # con retardo de 5 para no romper <PLAN>. El tail_buf pendiente se
        # flushea en finish().
        return events

    def finish(self) -> list[ParserEvent]:
        """Finalize parsing. Flush any dangling buffer as best we can."""
        events: list[ParserEvent] = []

        # If we were still waiting for <PLAN> and had a partial header, it's
        # just text that never became a plan.
        if self._state == _ST_IDLE and self._header_buf:
            events.append(ParseTextChunk(text=self._header_buf))
            self._header_buf = ""
            self._state = _ST_TEXT

        # If a plan was opened but never closed, flush whatever lines we have
        # and let the caller see malformed=True.
        if self._state == _ST_IN_PLAN:
            body = re.sub(r"[ \t]*SEARCH:", "\nSEARCH:", self._plan_buf).strip()
            for line in body.split("\n"):
                self._handle_plan_line(line, events)
            self._plan_buf = ""
            # Note: _plan_closed stays False → malformed property is True.

        return events

    # ------------------------------------------------------------------
    # Line handling
    # ------------------------------------------------------------------

    def _handle_plan_line(self, line: str, events: list[ParserEvent]) -> None:
        task, reason = _parse_task_line(line)
        if task is None and not reason:
            return  # empty line — skip silently
        if task is None:
            self._invalid_lines.append(line)
        else:
            self._tasks.append(task)
        events.append(ParsePlanLine(raw=line, task=task, invalid_reason=reason))


# ---------------------------------------------------------------------------
# Line → Task
# ---------------------------------------------------------------------------

def _parse_task_line(line: str) -> tuple[Task | None, str]:
    """Parse a single line inside the plan.

    Returns (task, reason). reason is "" when the line was valid or empty.
    """
    stripped = line.strip()
    if not stripped:
        return None, ""

    # Dispatch on prefix. Add new tools here (WRITE:, FETCH:, CODE:).
    if stripped.startswith("SEARCH:"):
        payload = stripped[len("SEARCH:"):].strip()
        if not payload:
            return None, "empty SEARCH payload"
        return Task(kind=TaskKind.SEARCH, payload=payload, raw_line=line), ""

    return None, f"unknown task prefix: {stripped[:30]!r}"