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

    if target_conv is not None:
        orphan_msg = {
            "role": "assistant",
            "content": partial,
            "truncated": True,
            "interrupted_at": datetime.now().isoformat(),
            "reformulation_count": st.session_state.get("reformulation_count", 0),
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
        rag_context = ""
        rag_sources = []
        if st.session_state.get("rag_enabled", False) and st.session_state.get("rag_available", False):
            project_id = active_project["id"] if active_project else None
            if project_id:
                retriever = st.session_state.rag_retriever
                rag_sources = retriever.search(original_prompt, project_id=project_id, top_n=5)
                if rag_sources:
                    rag_context = "\n\n---\n\n".join(
                        f"Fuente: {r['text_link']}\nContenido: {r['text']}"
                        for r in rag_sources
                    )

        # Mostrar mensaje de usuario
        with st.chat_message("user"):
            render_user_message(user_msg)

        # Procesar Respuesta del Asistente
        with st.chat_message("assistant"):
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
                rag_context=rag_context,   # <--- RAG
            )

            # Registrar a qué conversación pertenece este stream. Si el usuario
            # cambia de conversación mid-stream, el partial huérfano se comitea
            # a esta conversación y no a la nueva.
            st.session_state.partial_conversation_id = st.session_state.current_conversation_id

            try:
                effort_params = get_effort_params(st.session_state.api_provider, st.session_state.api_brainer)

                if st.session_state.api_provider == "DeepSeek":
                    stream_gen = stream_deepseek_completion(api_messages, st.session_state.api_key, **effort_params)
                elif st.session_state.api_provider == "Mistral AI":
                    stream_gen = stream_mistral_completion(api_messages, st.session_state.api_key, **effort_params)
                elif st.session_state.api_provider == "Anthropic (Claude)":
                    stream_gen = stream_anthropic_completion(api_messages, st.session_state.api_key, **effort_params)
                else:
                    stream_gen = stream_gemini_completion(api_messages, st.session_state.api_key, **effort_params)

                # Iterar el streaming
                for chunk in stream_gen:
                    if chunk:
                        full_response += chunk
                        st.session_state.partial_response = full_response
                        response_placeholder.markdown(full_response + "▌")

                response_placeholder.markdown(full_response)

                # Mostrar fuentes RAG
                if rag_sources:
                    with st.expander(f"📚 Fuentes utilizadas ({len(rag_sources)})", expanded=False):
                        for r in rag_sources:
                            st.markdown(f"**Score:** {r['score']:.2f} | **Origen:** `{r['text_link']}`")
                            st.write(r["text"][:500])

                # Guardar respuesta final
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "truncated": False,
                    "reformulation_count": st.session_state.reformulation_count if is_reformulation else 0,
                })
                st.session_state.messages[-1]["id"] = st.session_state.db.save_message(
                    st.session_state.current_conversation_id,
                    st.session_state.messages[-1],
                )

                st.session_state.last_assistant_response = full_response

                # Limpieza tras éxito
                st.session_state.partial_response = ""
                st.session_state.partial_conversation_id = None
                st.session_state.reformulation_count = 0

            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"⚠️ Error al generar respuesta: {str(e)}",
                    "truncated": False,
                })
                # Limpieza de estado transitorio: sin esto, el partial a medio
                # generar se persiste como turno fantasma en el siguiente mensaje.
                st.session_state.partial_response = ""
                st.session_state.partial_conversation_id = None
                st.session_state.reformulation_count = 0

        st.session_state.uploader_key += 1
        st.rerun()


main()