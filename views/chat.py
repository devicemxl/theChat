import streamlit as st
from datetime import datetime
from typing import Any, Literal

# --- Módulos Propios ---
from ui.sidebar import init_database, render_sidebar
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

# --- Funciones auxiliares (colocar al inicio, después de imports) ---


def main():

    if "agent_mode" not in st.session_state:
        st.session_state.agent_mode = "chat"
    if "api_brainer" not in st.session_state:
        st.session_state.api_brainer = "medio"
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 1. Inicialización de Estado y Sidebar
    # (set_page_config y load_custom_css viven en app.py — se ejecutan una sola vez)
    init_database()
    render_sidebar()


    # El proyecto activo se consulta acá también para pasar su system_prompt
    # al build_context más abajo. El indicador visual vive dentro del toolbar.
    active_project = st.session_state.db.get_conversation_project(
        st.session_state.current_conversation_id
    )

    # 4. Dibujar Historial de Mensajes
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user" and "--- Contenido de '" in msg["content"]:
                # Separar prompt de archivos
                parts = msg["content"].split("--- Contenido de '")
                prompt_part = parts[0].strip()
                st.markdown(prompt_part)

                for part in parts[1:]:
                    if "' ---" in part:
                        filename = part.split("' ---")[0]
                        content: Any | Literal[''] = part.split("' ---")[1].strip() if "' ---" in part else ""
                        with st.expander(f"📄 {filename}"):
                            st.code(content, language="text")
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
                

    # 3. Barra de herramientas superior (extraída en ui/toolbar.py)
    uploaded_files, api_key_ok = render_toolbar()
    if not api_key_ok:
        return
    # 
    # ============================================
    # 

    # 7. Input del Usuario y Generación
    # ============================================
    #
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
                        "content_preview": text[:200] + "..." if len(text) > 200 else text
                    })

            final_prompt = f"Contenido de archivos adjuntos:\n{file_content}" if not prompt else f"{prompt}\n\n{file_content}"
        else:
            final_prompt = prompt

        original_prompt = prompt or "Analiza los archivos adjuntos."

        # Guardar parcial truncado si existía
        if st.session_state.partial_response:
            st.session_state.messages.append({
                "role": "assistant",
                "content": st.session_state.partial_response,
                "truncated": True,
                "interrupted_at": datetime.now().isoformat(),
                "reformulation_count": st.session_state.reformulation_count
            })
            st.session_state.db.save_message(st.session_state.current_conversation_id, st.session_state.messages[-1])
            st.session_state.tokens_wasted += len(st.session_state.partial_response) // 4
            st.session_state.partial_response = ""

        # Guardar mensaje de usuario
        st.session_state.messages.append({"role": "user", "content": final_prompt})
        st.session_state.last_user_message = original_prompt
        st.session_state.db.save_message(st.session_state.current_conversation_id, {"role": "user", "content": final_prompt})

        # Mostrar mensaje de usuario
        with st.chat_message("user"):
            st.markdown(original_prompt)
            if uploaded_files:
                for file_info in file_metadata:
                    with st.expander(f"📄 {file_info['name']} ({file_info['size']} bytes)"):
                        st.code(file_info['content_preview'], language="text")

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
            )

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

                # Guardar respuesta final
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "truncated": False,
                    "reformulation_count": st.session_state.reformulation_count if is_reformulation else 0
                })
                st.session_state.db.save_message(st.session_state.current_conversation_id, st.session_state.messages[-1])

                st.session_state.last_assistant_response = full_response
                st.session_state.partial_response = ""
                st.session_state.reformulation_count = 0

            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"⚠️ Error al generar respuesta: {str(e)}",
                    "truncated": False
                })

        st.session_state.uploader_key += 1
        st.rerun()

# Ejecutar la página. st.navigation invoca este script al seleccionar "Chat".
main()