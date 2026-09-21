import streamlit as st
from datetime import datetime
from typing import Any, Literal

# --- Módulos Propios ---
from ui.sidebar import (
    init_database,
    render_sidebar,
    load_conversation_messages,
    switch_conversation,
)
from ui.toolbar import render_toolbar, get_effort_params
from ui.components import add_copy_button
from utils.config import get_secret
from utils.file_handler import extract_text_from_file
from llm.api_clients import (
    detect_reformulation,
    build_context_with_reformulation_awareness,
    stream_deepseek_completion,
    stream_mistral_completion,
    stream_gemini_completion,
    stream_anthropic_completion,
)

import json
import re

from agent.config import (
    MAX_PLAN_ROUNDS,
    MAX_SEARCHES_PER_TURN,
    TOP_N_PER_SEARCH,
)
from agent.prompts import AGENT_SYSTEM_PROMPT
from agent.runner import (
    run_agent_turn,
    AgentThinkingStart,
    AgentPlanLine,
    AgentSearchStart,
    AgentSearchResults,
    AgentSearchSkipped,
    AgentSearchError,
    AgentResponseChunk,
    AgentError,
    AgentTurnComplete,
)

# --- Funciones auxiliares ---

def render_user_message(msg: dict):
    """Renderiza un mensaje de usuario con sus archivos adjuntos (si los hay)."""
    display_content = msg.get("display_content", msg["content"])
    st.markdown(display_content)
    for file_info in msg.get("files", []):
        with st.expander(f"📄 {file_info.get('name', 'archivo')}"):
            st.code(file_info.get("content", ""), language="text")


def commit_orphan_partial() -> None:
    """Comitea un `partial_response` huérfano como mensaje truncado.

    Un partial queda huérfano cuando el handler muere a media generación
    (reload de página, cierre de pestaña, desconexión websocket, excepción
    no capturada). En esos casos el contenido está en `session_state` pero
    NO en `messages` ni en la BD, así que no se renderiza hasta que llega
    el siguiente turno del usuario.

    Este helper se invoca al inicio del handler, después de `render_sidebar()`
    (que carga `current_conversation_id` y `messages`) y antes del loop de
    historial, para que el partial entre a `messages` en el mismo render.
    """
    partial = st.session_state.get("partial_response")
    if not partial:
        return

    # Preferimos el id registrado al arrancar el stream; si no existe, caemos
    # al actual (caso degenerado).
    target_conv = (
        st.session_state.get("partial_conversation_id")
        or st.session_state.get("current_conversation_id")
    )

    # Defensa: si el partial contiene un <PLAN> sin cerrar (el handler murió
    # a media planificación), el usuario nunca vio ese texto en pantalla.
    # Lo descartamos para no persistir contenido que no se renderizó.
    # Un <PLAN> completo también se filtra por la misma razón.
    partial_visible = re.sub(r"<PLAN>.*?</PLAN>", "", partial, flags=re.DOTALL)
    partial_visible = re.sub(r"<PLAN>.*", "", partial_visible, flags=re.DOTALL)
    partial_visible = partial_visible.strip()

    # Si tras filtrar no queda nada, no hay nada que comitear como mensaje.
    # Solo limpiamos el estado transitorio.
    if not partial_visible:
        st.session_state.partial_response = ""
        st.session_state.partial_conversation_id = None
        st.session_state.reformulation_count = 0
        return
    
    if target_conv is not None:

        orphan_msg = {
            "role": "assistant",
            "content": partial,
            "truncated": True,
            "interrupted_at": datetime.now().isoformat(),
            "reformulation_count": st.session_state.get("reformulation_count", 0),
            "agent_status": "interrupted",     # ← NUEVO
        }
        try:
            orphan_msg["id"] = st.session_state.db.save_message(target_conv, orphan_msg)
        except Exception as e:
            st.warning(f"⚠️ No se pudo guardar la respuesta interrumpida: {e}")
        else:
            # Solo inyectamos al historial visual si es la conversación activa.
            # Si el usuario cambió de conversación, el mensaje ya quedó en la BD
            # y aparecerá cuando vuelva a la conversación original.
            if target_conv == st.session_state.get("current_conversation_id"):
                st.session_state.messages.append(orphan_msg)
            st.session_state.tokens_wasted = (
                st.session_state.get("tokens_wasted", 0) + len(partial) // 4
            )

    # Limpieza incondicional del estado transitorio.
    st.session_state.partial_response = ""
    st.session_state.partial_conversation_id = None
    st.session_state.reformulation_count = 0


def main():

    # --- Defaults de session_state ---
    if "agent_mode" not in st.session_state:
        st.session_state.agent_mode = "chat"
    if "api_brainer" not in st.session_state:
        st.session_state.api_brainer = "medio"
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "partial_response" not in st.session_state:
        st.session_state.partial_response = ""
    if "partial_conversation_id" not in st.session_state:
        st.session_state.partial_conversation_id = None
    if "reformulation_count" not in st.session_state:
        st.session_state.reformulation_count = 0
    if "tokens_wasted" not in st.session_state:
        st.session_state.tokens_wasted = 0

    # 1. Inicialización de Estado y Sidebar
    # (set_page_config y load_custom_css viven en app.py — se ejecutan una vez)
    init_database()
    render_sidebar()

    # 2. Comitear partial huérfano ANTES de renderizar el historial.
    #    Si el handler anterior murió mid-stream, este paso lo persiste y lo
    #    hace visible en este mismo render.
    commit_orphan_partial()

    # El proyecto activo se consulta acá también para pasar su system_prompt
    # al build_context más abajo. El indicador visual vive dentro del toolbar.
    active_project = st.session_state.db.get_conversation_project(
        st.session_state.current_conversation_id
    )

    # 4. Dibujar Historial de Mensajes
    for idx, msg in enumerate(st.session_state.messages):
        is_last = idx == len(st.session_state.messages) - 1
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                render_user_message(msg)
            else:
                st.markdown(msg["content"])

            # Renderizar botón de copiar solo en respuestas del asistente
            if msg["role"] == "assistant":
                msg_key = f"msg_{st.session_state.current_conversation_id}_{idx}"
                add_copy_button(msg["content"], msg_key)

            if msg.get("truncated", False):
                st.caption("⚠️ *Mensaje truncado*")

            if (msg.get("reformulation_count") or 0) > 0:
                st.caption(f"🔄 *Reformulado {msg['reformulation_count']} veces*")

            # --- Acciones sobre el último mensaje ---
            if is_last and msg["role"] == "assistant":
                conversation_id = st.session_state.current_conversation_id
                conv = st.session_state.db.get_conversation(conversation_id)
                own_messages = st.session_state.db.get_messages(conversation_id)

                # Solo si hay un turno completo propio (último es assistant)
                has_own_turn = len(own_messages) >= 2 and own_messages[-1]["role"] == "assistant"
                is_branch = bool(conv.get("forked_from_conversation_id"))

                col_fork, col_delete, _ = st.columns([1, 1, 3])
                with col_fork:
                    if not is_branch and has_own_turn:
                        if st.button("🌿 Fork", key=f"fork_{msg['id']}", use_container_width=True):
                            fork_point = own_messages[-1]["id"]
                            new_id = st.session_state.db.create_fork(conversation_id, fork_point)
                            switch_conversation(new_id)
                            st.rerun()
                with col_delete:
                    if has_own_turn:
                        if st.button("🗑️ Eliminar turno", key=f"del_turn_{msg['id']}", use_container_width=True):
                            deleted = st.session_state.db.delete_last_turn(conversation_id)
                            if deleted:
                                st.toast("🗑️ Turno eliminado", icon="✅")
                            else:
                                st.toast("⚠️ No se pudo eliminar el turno", icon="⚠️")
                            st.session_state.messages = load_conversation_messages(conversation_id)
                            st.rerun()

    # Si la conversación es una rama sin mensajes propios, avisarlo
    conv = st.session_state.db.get_conversation(st.session_state.current_conversation_id)
    own_count = len(st.session_state.db.get_messages(st.session_state.current_conversation_id))
    if conv.get("forked_from_conversation_id") and own_count == 0:
        st.caption("🌿 *Rama sin mensajes propios — mostrando contexto heredado de la conversación madre.*")

    # 3. Barra de herramientas superior (extraída en ui/toolbar.py)
    uploaded_files, api_key_ok = render_toolbar()
    if not api_key_ok:
        return

    # ============================================
    # 7. Input del Usuario y Generación
    # ============================================
    if prompt := st.chat_input("Escribe tu mensaje..."):
        file_content = ""
        file_metadata = []

        if uploaded_files:
            for file in uploaded_files:
                text = extract_text_from_file(file)
                if text:
                    file_content += f"\n\n--- Contenido de '{file.name}' ---\n{text}\n"
                    file_metadata.append({
                        "name": file.name,
                        "size": file.size,
                        "content": text,
                    })

            final_prompt = f"Contenido de archivos adjuntos:\n{file_content}" if not prompt else f"{prompt}\n\n{file_content}"
        else:
            final_prompt = prompt

        original_prompt = prompt or "Analiza los archivos adjuntos."

        # Guardar mensaje de usuario
        user_msg = {"role": "user", "content": final_prompt}
        if file_metadata:
            user_msg["display_content"] = original_prompt
            user_msg["files"] = file_metadata
        st.session_state.messages.append(user_msg)
        st.session_state.last_user_message = original_prompt
        user_msg["id"] = st.session_state.db.save_message(
            st.session_state.current_conversation_id,
            {"role": "user", "content": final_prompt},
        )

        # --- RAG retrieval ---
        # Mostrar mensaje de usuario
        with st.chat_message("user"):
            render_user_message(user_msg)

        # ------------------------------------------------------------------
        # Preparar retriever para el ciclo agéntico
        # ------------------------------------------------------------------
        retriever = None
        project_id = None
        if (
            st.session_state.get("rag_enabled", False)
            and st.session_state.get("rag_available", False)
            and active_project
        ):
            retriever = st.session_state.rag_retriever
            project_id = active_project["id"]

        agent_system_prompt = AGENT_SYSTEM_PROMPT if retriever else None

        # Procesar Respuesta del Asistente
        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            plan_placeholder = st.empty()
            response_placeholder = st.empty()

            full_response = ""
            is_reformulation = detect_reformulation(original_prompt)

            if is_reformulation:
                st.session_state.reformulation_count += 1
                st.session_state.total_reformulations += 1
                st.caption(f"🔄 *Reformulación #{st.session_state.reformulation_count}*")

            api_messages = build_context_with_reformulation_awareness(
                st.session_state.messages,
                is_reformulation,
                st.session_state.reformulation_count,
                project_system_prompt=(active_project.get("system_prompt") if active_project else None),
                agent_system_prompt=agent_system_prompt,
            )

            st.session_state.partial_conversation_id = st.session_state.current_conversation_id

            # --- stream_fn bound to the current provider ---
            def _stream_fn(msgs):
                effort_params = get_effort_params(
                    st.session_state.api_provider, st.session_state.api_brainer
                )
                if st.session_state.api_provider == "DeepSeek":
                    return stream_deepseek_completion(
                        msgs, st.session_state.api_key, **effort_params
                    )
                elif st.session_state.api_provider == "Mistral AI":
                    return stream_mistral_completion(
                        msgs, st.session_state.api_key, **effort_params
                    )
                elif st.session_state.api_provider == "Anthropic (Claude)":
                    return stream_anthropic_completion(
                        msgs, st.session_state.api_key, **effort_params
                    )
                else:
                    return stream_gemini_completion(
                        msgs, st.session_state.api_key, **effort_params
                    )

            # --- Acumuladores del turno ---
            final_text = ""
            all_sources = []
            turn_status = "error"
            rounds_used = 0
            searches_used = 0
            plan_lines_by_round: dict[int, list] = {}
            current_max_rounds = MAX_PLAN_ROUNDS    # ← NUEVO

            try:
                for event in run_agent_turn(
                    api_messages=api_messages,
                    stream_fn=_stream_fn,
                    retriever=retriever,
                    project_id=project_id,
                    max_rounds=MAX_PLAN_ROUNDS,
                    max_searches=MAX_SEARCHES_PER_TURN,
                    top_n_per_search=TOP_N_PER_SEARCH,
                ):
                    if isinstance(event, AgentThinkingStart):
                        current_max_rounds = event.max_rounds    # ← Capturar
                        if event.is_final:
                            status_placeholder.markdown(
                                "_🧠 Sintetizando respuesta final..._"
                            )
                        else:
                            status_placeholder.markdown(
                                f"_🧠 Pensando... Planificando "
                                f"(ronda {event.round_num}/{event.max_rounds})_"
                            )

                    elif isinstance(event, AgentPlanLine):
                        plan_lines_by_round.setdefault(event.round_num, []).append(event)
                        snippet = event.raw.strip()[:60]
                        if snippet:
                            status_placeholder.markdown(
                                f"_🧠 Pensando... Planificando "
                                f"(ronda {event.round_num}/{current_max_rounds})_\n\n"   # ← Usar variable
                                f"`{snippet}`"
                            )

                    elif isinstance(event, AgentSearchStart):
                        status_placeholder.markdown(
                            f"_🔍 Buscando ({event.index}/{event.total}): "
                            f"`{event.query[:80]}`_"
                        )

                    elif isinstance(event, AgentSearchResults):
                        pass

                    elif isinstance(event, AgentSearchSkipped):
                        if event.reason == "budget_exhausted":
                            st.caption(
                                f"⏸ Búsqueda omitida (tope alcanzado): "
                                f"`{event.query[:60]}`"
                            )

                    elif isinstance(event, AgentSearchError):
                        st.warning(f"⚠️ Búsqueda fallida: {event.message}")

                    elif isinstance(event, AgentResponseChunk):
                        full_response += event.text
                        st.session_state.partial_response = full_response
                        response_placeholder.markdown(full_response + "▌")

                    elif isinstance(event, AgentError):
                        st.error(f"❌ {event.message}")

                    elif isinstance(event, AgentTurnComplete):
                        final_text = event.final_text
                        all_sources = event.all_sources
                        turn_status = event.status
                        rounds_used = event.rounds_used
                        searches_used = event.searches_used

                # --- Render final del turno ---

                # 1. Limpiar el indicador de estado
                status_placeholder.empty()

                # 2. Renderizar los planes por ronda (arriba de la respuesta)
                if plan_lines_by_round:
                    with plan_placeholder.container():
                        for rnum in sorted(plan_lines_by_round):
                            with st.expander(
                                f"🧠 Ronda {rnum} — plan ejecutado",
                                expanded=False,
                            ):
                                for line_ev in plan_lines_by_round[rnum]:
                                    if line_ev.task is not None:
                                        st.markdown(
                                            f"- 🔍 **{line_ev.task.payload}**"
                                        )
                                    elif line_ev.invalid_reason:
                                        st.markdown(
                                            f"- ⚠️ `{line_ev.raw.strip()[:80]}` "
                                            f"— *{line_ev.invalid_reason}*"
                                        )
                                    elif line_ev.raw.strip():
                                        st.markdown(
                                            f"- `{line_ev.raw.strip()[:80]}`"
                                        )

                # 3. Respuesta final
                response_placeholder.markdown(final_text)

                # 4. Fuentes RAG (dedup por id)
                if all_sources:
                    seen_ids = set()
                    unique_sources = []
                    for r in all_sources:
                        rid = r.get("id")
                        if rid in seen_ids:
                            continue
                        seen_ids.add(rid)
                        unique_sources.append(r)

                    with st.expander(
                        f"📚 Fuentes utilizadas ({len(unique_sources)})",
                        expanded=False,
                    ):
                        for r in unique_sources:
                            st.markdown(
                                f"**Score:** {r['score']:.2f} | "
                                f"**Origen:** `{r['text_link']}`"
                            )
                            st.write(r["text"][:500])

                # 5. Persistir el mensaje con metadatos
                metadata = {
                    "sources": [
                        {
                            "id": r.get("id"),
                            "text_link": r.get("text_link"),
                            "score": r.get("score"),
                        }
                        for r in all_sources
                    ],
                }
                final_msg = {
                    "role": "assistant",
                    "content": final_text,
                    "truncated": False,
                    "reformulation_count": (
                        st.session_state.reformulation_count if is_reformulation else 0
                    ),
                    "agent_status": turn_status,
                    "rounds_used": rounds_used,
                    "searches_used": searches_used,
                    "metadata_json": json.dumps(metadata, ensure_ascii=False),
                }
                st.session_state.messages.append(final_msg)
                st.session_state.messages[-1]["id"] = st.session_state.db.save_message(
                    st.session_state.current_conversation_id,
                    st.session_state.messages[-1],
                )

                st.session_state.last_assistant_response = final_text

                # 6. Limpieza
                st.session_state.partial_response = ""
                st.session_state.partial_conversation_id = None
                st.session_state.reformulation_count = 0

            except Exception as e:
                # Red de seguridad: errores de mapping/rendering que no vengan
                # ya del runner. El runner captura errores del stream_fn.
                st.error(f"❌ Error inesperado: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"⚠️ Error al generar respuesta: {str(e)}",
                    "truncated": False,
                    "agent_status": "error",
                })
                st.session_state.partial_response = ""
                st.session_state.partial_conversation_id = None
                st.session_state.reformulation_count = 0

        st.session_state.uploader_key += 1
        st.rerun()


main()