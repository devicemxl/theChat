"""Agent loop: plan → execute → inject → repeat → synthesize.

The runner is provider-agnostic. It receives a `stream_fn(messages) -> Iterator[str]`
and a retriever. It yields events that the caller (chat.py) renders.

Contract:
    - If retriever is None, the loop degenerates to a single streaming call
      and yields AgentResponseChunk events directly. No parser, no plan.
    - If retriever is provided, up to `max_rounds` planning rounds are allowed,
      with `max_searches` global budget across rounds. On budget exhaustion or
      round exhaustion, a final synthesis call is forced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Protocol

from agent.parser import (
    PlanStreamParser,
    ParsePlanClosed,
    ParsePlanLine,
    ParsePlanOpened,
    ParseTextChunk,
    Task,
    TaskKind,
)


# ---------------------------------------------------------------------------
# Events yielded by run_agent_turn
# ---------------------------------------------------------------------------

@dataclass
class AgentThinkingStart:
    round_num: int
    max_rounds: int
    is_final: bool = False


@dataclass
class AgentPlanLine:
    round_num: int
    raw: str
    task: Task | None
    invalid_reason: str = ""


@dataclass
class AgentSearchStart:
    round_num: int
    query: str
    index: int
    total: int


@dataclass
class AgentSearchResults:
    round_num: int
    query: str
    results: list[dict]


@dataclass
class AgentSearchSkipped:
    round_num: int
    query: str
    reason: str


@dataclass
class AgentSearchError:
    round_num: int
    query: str
    message: str


@dataclass
class AgentResponseChunk:
    text: str


@dataclass
class AgentError:
    message: str


@dataclass
class AgentTurnComplete:
    final_text: str
    all_sources: list[dict]
    rounds_used: int
    searches_used: int
    status: str
    # status: "completed" | "max_rounds_reached" | "max_searches_reached"
    #       | "parse_failed" | "empty_plan" | "error"


StreamFn = Callable[[list[dict]], Iterator[str]]


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

@dataclass
class _TurnState:
    messages: list[dict]
    retriever: Any
    project_id: int | None
    max_rounds: int
    max_searches: int
    top_n_per_search: int

    round_num: int = 0
    searches_used: int = 0
    all_sources: list[dict] = field(default_factory=list)
    final_text: str = ""
    status: str = "in_progress"
    done: bool = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_agent_turn(
    *,
    api_messages: list[dict],
    stream_fn: StreamFn,
    retriever: Any | None,
    project_id: int | None,
    max_rounds: int,
    max_searches: int,
    top_n_per_search: int,
) -> Iterator[object]:
    """Yield agent events for one full turn.

    The caller is expected to consume all events and use AgentTurnComplete
    to persist the turn and render the sources expander.
    """
    # ------------------------------------------------------------------
    # Degenerate mode: no retriever → single streaming call, no parser.
    # ------------------------------------------------------------------
    if retriever is None:
        final_text = ""
        try:
            for chunk in stream_fn(api_messages):
                if chunk:
                    final_text += chunk
                    yield AgentResponseChunk(text=chunk)
        except Exception as e:
            yield AgentError(message=str(e))
            yield AgentTurnComplete(
                final_text=final_text, all_sources=[],
                rounds_used=1, searches_used=0, status="error",
            )
            return

        yield AgentTurnComplete(
            final_text=final_text, all_sources=[],
            rounds_used=1, searches_used=0, status="completed",
        )
        return

    # ------------------------------------------------------------------
    # Full agent cycle
    # ------------------------------------------------------------------
    state = _TurnState(
        messages=list(api_messages),
        retriever=retriever,
        project_id=project_id,
        max_rounds=max_rounds,
        max_searches=max_searches,
        top_n_per_search=top_n_per_search,
    )

    while state.round_num < state.max_rounds and not state.done:
        state.round_num += 1
        yield from _run_one_round(state, stream_fn)

    if not state.done:
        state.status = "max_rounds_reached"
        yield from _force_final_response(state, stream_fn)

    unique_sources = _dedupe_sources(state.all_sources)

    yield AgentTurnComplete(
        final_text=state.final_text,
        all_sources=unique_sources,
        rounds_used=state.round_num,
        searches_used=state.searches_used,
        status=state.status,
    )


# ---------------------------------------------------------------------------
# One planning round
# ---------------------------------------------------------------------------

def _run_one_round(state: _TurnState, stream_fn: StreamFn) -> Iterator[object]:
    yield AgentThinkingStart(round_num=state.round_num, max_rounds=state.max_rounds)

    parser = PlanStreamParser()
    accumulated = ""

    # --- 1. Stream and parse ---
    try:
        stream = stream_fn(state.messages)
        for chunk in stream:
            if not chunk:
                continue
            accumulated += chunk
            for ev in parser.feed(chunk):
                if isinstance(ev, ParsePlanOpened):
                    # Descartar cualquier pre-plan text del cómputo final.
                    accumulated = ""
                yield from _map_parser_event(ev, state.round_num)
    except Exception as e:
        yield AgentError(message=str(e))
        state.status = "error"
        state.done = True
        return

    for ev in parser.finish():
        yield from _map_parser_event(ev, state.round_num)

    # --- 2. Decide what this round was ---

    # No plan → this IS the final response.
    if not parser.had_plan:
        state.final_text = accumulated
        state.status = "completed"
        state.done = True
        return

    # Plan opened but never closed → malformed.
    if parser.malformed:
        state.status = "parse_failed"
        # Fallback: use whatever text the parser extracted as the response.
        state.final_text = accumulated
        state.done = True
        return

    # Plan parsed but empty → model misbehaved.
    if not parser.tasks:
        state.status = "empty_plan"
        state.final_text = accumulated
        state.done = True
        return

    # --- 3. Persist the plan in the working context ---
    state.messages.append({"role": "assistant", "content": accumulated})

    # --- 4. Execute tasks ---
    round_results: list[tuple[str, list[dict]]] = []

    for i, task in enumerate(parser.tasks):
        if task.kind != TaskKind.SEARCH:
            yield AgentSearchSkipped(
                round_num=state.round_num, query=task.raw_line,
                reason="unknown_task",
            )
            continue

        if state.searches_used >= state.max_searches:
            yield AgentSearchSkipped(
                round_num=state.round_num, query=task.payload,
                reason="budget_exhausted",
            )
            round_results.append((task.payload, []))
            continue

        state.searches_used += 1
        yield AgentSearchStart(
            round_num=state.round_num, query=task.payload,
            index=i + 1, total=len(parser.tasks),
        )

        try:
            results = state.retriever.search(
                task.payload,
                project_id=state.project_id,
                top_n=state.top_n_per_search,
            )
        except Exception as e:
            yield AgentSearchError(
                round_num=state.round_num, query=task.payload,
                message=str(e),
            )
            results = []

        round_results.append((task.payload, results))
        state.all_sources.extend(results)
        yield AgentSearchResults(
            round_num=state.round_num, query=task.payload, results=results,
        )

    # --- 5. Inject results as a user message ---
    injection = _format_search_injection(
        round_num=state.round_num,
        max_rounds=state.max_rounds,
        searches_used=state.searches_used,
        max_searches=state.max_searches,
        results_per_query=round_results,
    )
    state.messages.append({"role": "user", "content": injection})

    # --- 6. If budget exhausted, force synthesis next round ---
    if state.searches_used >= state.max_searches:
        state.status = "max_searches_reached"
        state.messages.append({
            "role": "user",
            "content": (
                "[Search budget exhausted. Respond now with what you have. "
                "Do not emit another <PLAN>.]"
            ),
        })
        # Next call to _run_one_round will run with an exhausted budget.
        # The parser will see any <PLAN> but every SEARCH will be skipped
        # (budget check). To avoid wasting a round, the loop will exit
        # when round_num hits max_rounds, or this round already answered.
        # If the model respects the hint, it responds directly and we exit.


# ---------------------------------------------------------------------------
# Forced synthesis (max rounds or budget exhausted)
# ---------------------------------------------------------------------------

def _force_final_response(state: _TurnState, stream_fn: StreamFn) -> Iterator[object]:
    """Stream a final response with the parser disabled.

    Any <PLAN> the model emits here is treated as plain text — we are past
    the planning phase and a plan at this point is a protocol violation.
    """
    yield AgentThinkingStart(
        round_num=state.round_num, max_rounds=state.max_rounds, is_final=True,
    )

    # Ensure the last message is a "respond now" hint (avoid duplicates).
    last = state.messages[-1] if state.messages else None
    needs_hint = not (
        last
        and last.get("role") == "user"
        and "respond now" in (last.get("content") or "").lower()
    )
    if needs_hint:
        state.messages.append({
            "role": "user",
            "content": (
                "[Planning rounds exhausted. Respond now with what you have. "
                "Do not emit <PLAN>.]"
            ),
        })

    text = ""
    try:
        for chunk in stream_fn(state.messages):
            if chunk:
                text += chunk
                yield AgentResponseChunk(text=chunk)
    except Exception as e:
        yield AgentError(message=str(e))
        state.status = "error"
        state.final_text = text
        state.done = True
        return

    state.final_text = text
    state.done = True
    # If we got here because of max_searches_reached, keep that status;
    # otherwise the caller already set max_rounds_reached.


# ---------------------------------------------------------------------------
# Parser → runner event mapping
# ---------------------------------------------------------------------------

def _map_parser_event(ev: object, round_num: int) -> Iterator[object]:
    if isinstance(ev, ParseTextChunk):
        yield AgentResponseChunk(text=ev.text)
    elif isinstance(ev, ParsePlanOpened):
        # No dedicated runner event for "opened"; the UI reacts to plan lines.
        pass
    elif isinstance(ev, ParsePlanLine):
        yield AgentPlanLine(
            round_num=round_num, raw=ev.raw,
            task=ev.task, invalid_reason=ev.invalid_reason,
        )
    elif isinstance(ev, ParsePlanClosed):
        pass  # Also silent; PlanLine events already conveyed the content.


# ---------------------------------------------------------------------------
# Injection formatting
# ---------------------------------------------------------------------------

def _dedupe_sources(sources: list[dict]) -> list[dict]:
    """Deduplica por `id`, conservando la entrada de mayor score.

    Cuando el agente busca varias veces en un turno, es común que dos rondas
    devuelvan el mismo chunk con scores distintos (la query cambió). El
    retriever no garantiza orden, así que el orden de aparición no es señal
    de calidad. Se conserva el de mayor score para que el expander final
    refleje el mejor match conocido.

    El orden de inserción se preserva (dict en Python 3.7+ mantiene orden
    de primera inserción de cada clave, aunque se reasigne el valor).

    Fallback si `id` es None: usa (text_link, prefijo de text) como clave.
    """
    best: dict = {}
    for r in sources:
        rid = r.get("id")
        if rid is None:
            key = (r.get("text_link"), (r.get("text") or "")[:100])
        else:
            key = rid

        existing = best.get(key)
        if existing is None or r.get("score", 0.0) > existing.get("score", 0.0):
            best[key] = r

    return list(best.values())

def _format_search_injection(
    *,
    round_num: int,
    max_rounds: int,
    searches_used: int,
    max_searches: int,
    results_per_query: list[tuple[str, list[dict]]],
) -> str:
    """Build the message injected after a round's searches.

    Format is stable and documented in AGENT_SYSTEM_PROMPT: the model is
    told it will receive results prefixed with the round number.
    """
    lines: list[str] = []
    lines.append(f"[Round {round_num} search results]")
    lines.append("")

    for query, results in results_per_query:
        lines.append(f'--- Query: "{query}" ---')
        if not results:
            lines.append("(no results found)")
        else:
            for i, r in enumerate(results, 1):
                score = r.get("score", 0.0)
                link = r.get("text_link", "?")
                text = r.get("text", "")
                lines.append(f"[{i}] score={score:.3f} | source={link}")
                lines.append(text)
                lines.append("")
        lines.append("")

    rounds_left = max(0, max_rounds - round_num)
    searches_left = max(0, max_searches - searches_used)
    lines.append(
        f"[End of round {round_num}. "
        f"Rounds remaining: {rounds_left}. "
        f"Searches remaining: {searches_left}.]"
    )

    return "\n".join(lines)