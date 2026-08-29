import streamlit as st
from datetime import datetime
from typing import Any, Literal

# --- Módulos Propios ---
from ui.sidebar import init_database, render_sidebar, clear_current_conversation
from ui.components import load_custom_css, add_copy_button
from utils.file_handler import extract_text_from_file
from llm.api_clients import (
    detect_reformulation, 
    build_context_with_reformulation_awareness, 
    stream_deepseek_completion, 
    stream_mistral_completion, 
    stream_gemini_completion
)

def main():
    # 1. Configuración de página y estilos
    st.set_page_config(
        page_title="💬 Multi-IA Chat",
        page_icon="💬",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    load_custom_css()

    # 2. Inicialización de Estado y Sidebar
    init_database()
    render_sidebar()

    st.header("", divider="rainbow")

    # 3. Acciones contextuales (Botón Limpiar)
    with st.container():
        st.caption(f"Conversación #{st.session_state.current_conversation_id} | Mensajes: {len(st.session_state.messages)} | Reformulaciones: {st.session_state.total_reformulations} | Provider: {st.session_state.api_provider}")
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("🗑️ Limpiar"):
                clear_current_conversation()
                st.rerun()

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
                
    # 5. Validación de API Key
    if not st.session_state.api_key:
        st.warning(f"⚠️ Configura tu API Key de {st.session_state.api_provider} en la barra lateral o en config.toml.")
        return

    # 6. Subida de Archivos
    uploaded_files = st.file_uploader(
        "📎 Adjuntar archivos (opcional)",
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.uploader_key}",
        label_visibility="collapsed",
        help="Sube archivos de texto, PDF, DOCX, CSV, JSON, código, etc."
    )

    if uploaded_files:
        with st.container():
            st.caption(f"📎 Archivos adjuntos: {', '.join([f.name for f in uploaded_files])}")

    # 7. Input del Usuario y Generación
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
                st.session_state.reformulation_count
            )

            try:
                # Selección dinámica de la API
                if st.session_state.api_provider == "DeepSeek":
                    stream_gen = stream_deepseek_completion(api_messages, st.session_state.api_key)
                elif st.session_state.api_provider == "Mistral AI":
                    stream_gen = stream_mistral_completion(api_messages, st.session_state.api_key)
                else:
                    stream_gen = stream_gemini_completion(api_messages, st.session_state.api_key)

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

if __name__ == "__main__":
    main()