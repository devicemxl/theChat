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

def displayMSGx(msg):
    st.info(msg)

def get_secret(key: str) -> str:
    """Intenta obtener un secreto de forma segura desde los secrets de Streamlit."""
    try:
        return st.secrets[key] if key in st.secrets else ""
    except Exception:
        return ""

# --- Funciones auxiliares (colocar al inicio, después de imports) ---

def get_effort_params(provider: str, effort: str) -> dict:
    """Devuelve los parámetros específicos para el proveedor según el esfuerzo."""
    if provider == "DeepSeek":
        # DeepSeek espera reasoning_effort como string: "bajo", "medio", "alto"
        # El mapeo a inglés se hará dentro de la función de streaming
        return {"reasoning_effort": effort}
    elif provider == "Google AI Studio (Gemini)":
        temp_map = {"bajo": 0.3, "medio": 0.7, "alto": 1.0}
        return {"temperature": temp_map.get(effort, 0.7)}
    elif provider == "Mistral AI":
        temp_map = {"bajo": 0.3, "medio": 0.7, "alto": 1.0}
        return {"temperature": temp_map.get(effort, 0.7)}
    else:
        return {}

def configure_model_effort():
    """Configura el esfuerzo del modelo desde la interfaz."""
    esfuerzo = ["bajo", "medio", "alto"]
    # Inicializar si no existe
    if "api_brainer" not in st.session_state:
        st.session_state.api_brainer = "medio"
    nuevo_esfuerzo = st.selectbox(
        "Esfuerzo del modelo",
        esfuerzo,
        index=esfuerzo.index(st.session_state.api_brainer) if st.session_state.api_brainer in esfuerzo else 1
    )
    if nuevo_esfuerzo != st.session_state.api_brainer:
        st.session_state.api_brainer = nuevo_esfuerzo
        st.rerun()
    # Solo guardamos el string, no sobrescribimos con números

def configure_api_key():
    """Configura el Proveedor y la API key desde la interfaz"""
    proveedores = ["DeepSeek", "Google AI Studio (Gemini)", "Mistral AI"]

    nuevo_proveedor = st.selectbox(
        "Proveedor de IA",
        proveedores,
        index=proveedores.index(st.session_state.api_provider) if st.session_state.api_provider in proveedores else 0
    )

    if nuevo_proveedor != st.session_state.api_provider:
        st.session_state.api_provider = nuevo_proveedor
        st.rerun()
        
    if st.session_state.api_provider == "DeepSeek":
        key_input = get_secret("DEEPSEEK_API_KEY")
        st.session_state.deepseek_api_key = key_input
        st.session_state.api_key = key_input

    elif st.session_state.api_provider == "Google AI Studio (Gemini)":
        key_input = get_secret("GEMINI_API_KEY")
        st.session_state.gemini_api_key = key_input
        st.session_state.api_key = key_input

    elif st.session_state.api_provider == "Mistral AI":
        key_input = get_secret("MISTRAL_API_KEY")
        st.session_state.mistral_api_key = key_input
        st.session_state.api_key = key_input


def main():

    msgX = "Enjoy It"

    if "agent_mode" not in st.session_state:
        st.session_state.agent_mode = "chat"
    if st.session_state.agent_mode == "code":
        msgX = "Modo Code activado: el asistente podrá explorar y modificar archivos (con restricciones)."
    if "api_brainer" not in st.session_state:
        st.session_state.api_brainer = "medio"
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 1. Configuración de página y estilos
    st.set_page_config(
        page_title="💬 Multi-IA Chat",
        page_icon="💬",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    load_custom_css()

    # 2. Inicialización de Estado y Sidebar
    init_database()
    render_sidebar()

    # 3. Acciones contextuales (Botón Limpiar)
    with st.expander(label=f"Conversación #{st.session_state.current_conversation_id} | Mensajes: {len(st.session_state.messages)} | Reformulaciones: {st.session_state.total_reformulations} | Provider: {st.session_state.api_provider}"):
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        with col1:
                configure_api_key()
                # 5. Validación de API Key
                if not st.session_state.api_key:
                    msgX = f"⚠️ Configura tu API Key de {st.session_state.api_provider} en la barra lateral o en config.toml."
                    return
        with col2: 
            # 6b. Modo de agente (chat / code)
            agent_mode = st.radio(
                        "Modo de agente",
                        options=["chat", "code"],
                        index=0 if st.session_state.agent_mode == "chat" else 1,
                        horizontal=True,
                        help="Chat: conversación normal. Code: el asistente puede explorar y modificar archivos del proyecto (con restricciones)."
            )
            if agent_mode != st.session_state.agent_mode:
                        st.session_state.agent_mode = agent_mode
                        st.rerun()
        with col3: 
            configure_model_effort()
            if not st.session_state.api_brainer:
                pass
        with col4:
            # 6a. Subida de Archivos
            uploaded_files = st.file_uploader(
                "📎 Adjuntar archivos (opcional)",
                accept_multiple_files=True,
                key=f"file_uploader_{st.session_state.uploader_key}",
                label_visibility="collapsed",
                help="Sube archivos de texto, PDF, DOCX, CSV, JSON, código, etc."
            )                

            if uploaded_files:
                msgX = f"📎 Archivos adjuntos: {', '.join([f.name for f in uploaded_files])}"
        with col5, col6: "" 
        with col7:
            st.caption("Vaciar Platica")
            if st.button("🗑️ "):
                clear_current_conversation()
                st.rerun()
        #
        displayMSGx(msg=msgX)

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
                st.session_state.reformulation_count
            )

            try:
                effort_params = get_effort_params(st.session_state.api_provider, st.session_state.api_brainer)
                
                if st.session_state.api_provider == "DeepSeek":
                    stream_gen = stream_deepseek_completion(api_messages, st.session_state.api_key, **effort_params)
                elif st.session_state.api_provider == "Mistral AI":
                    stream_gen = stream_mistral_completion(api_messages, st.session_state.api_key, **effort_params)
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

if __name__ == "__main__":
    main()