import streamlit as st
from datetime import datetime
from typing import List, Dict

# Importamos la base de datos (asumiendo que database.py está en la raíz)
from database import ChatDatabase

# Importaremos estas funciones de los módulos que crearás después
from utils.file_handler import extract_files_from_message
from utils.data_export import (
    export_current_conversation, 
    export_all_conversations, 
    import_conversations
)

# ========== UTILIDADES DE ESTADO ==========

def get_secret(key: str) -> str:
    """Intenta obtener un secreto de forma segura desde los secrets de Streamlit."""
    try:
        return st.secrets[key] if key in st.secrets else ""
    except Exception:
        return ""

def init_database():
    """Inicializa la base de datos y todas las variables de estado (session_state)"""
    if "db" not in st.session_state:
        st.session_state.db = ChatDatabase("chat_history.db")

    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = st.session_state.db.create_conversation(
            f"Conversación {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    if "messages" not in st.session_state:
        st.session_state.messages = load_conversation_messages(st.session_state.current_conversation_id)

    if "reformulation_count" not in st.session_state:
        st.session_state.reformulation_count = 0

    if "last_user_message" not in st.session_state:
        st.session_state.last_user_message = ""

    if "last_assistant_response" not in st.session_state:
        st.session_state.last_assistant_response = ""

    if "tokens_wasted" not in st.session_state:
        st.session_state.tokens_wasted = 0

    if "total_reformulations" not in st.session_state:
        st.session_state.total_reformulations = 0

    if "conversation_start_time" not in st.session_state:
        st.session_state.conversation_start_time = datetime.now()

    # --- VARIABLES PARA MÚLTIPLES APIS ---
    if "api_provider" not in st.session_state:
        st.session_state.api_provider = "DeepSeek"

    if "deepseek_api_key" not in st.session_state:
        st.session_state.deepseek_api_key = get_secret("DEEPSEEK_API_KEY")

    if "gemini_api_key" not in st.session_state:
        st.session_state.gemini_api_key = get_secret("GEMINI_API_KEY")

    if "mistral_api_key" not in st.session_state:
        st.session_state.mistral_api_key = get_secret("MISTRAL_API_KEY")

    if "api_key" not in st.session_state:
        st.session_state.api_key = st.session_state.deepseek_api_key

    if "partial_response" not in st.session_state:
        st.session_state.partial_response = ""

    if "editing_conv_id" not in st.session_state:
        st.session_state.editing_conv_id = None

    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0


# ========== GESTIÓN DE CONVERSACIONES ==========

def load_conversation_messages(conversation_id: int) -> List[Dict]:
    """Carga los mensajes de una conversación desde la base de datos"""
    db = st.session_state.db
    messages = db.get_messages(conversation_id)

    formatted_messages = []
    for msg in messages:
        content = msg["content"]

        if msg["role"] == "user" and "--- Contenido de '" in content:
            prompt, files = extract_files_from_message(content)
            formatted_messages.append({
                "role": msg["role"],
                "content": content,
                "display_content": prompt,
                "files": files,
                "truncated": msg["truncated"],
                "interrupted_at": msg["interrupted_at"],
                "reformulation_count": msg.get("reformulation_count") or 0
            })
        else:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "truncated": msg["truncated"],
                "interrupted_at": msg["interrupted_at"],
                "reformulation_count": msg.get("reformulation_count") or 0
            })
    return formatted_messages

def create_new_conversation():
    """Crea una nueva conversación y la establece como actual"""
    db = st.session_state.db
    title = f"Conversación {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    new_id = db.create_conversation(title)

    st.session_state.current_conversation_id = new_id
    st.session_state.messages = []
    st.session_state.reformulation_count = 0
    st.session_state.last_user_message = ""
    st.session_state.last_assistant_response = ""
    st.session_state.conversation_start_time = datetime.now()
    st.session_state.partial_response = ""
    return new_id

def switch_conversation(conversation_id: int):
    """Cambia a una conversación existente"""
    st.session_state.current_conversation_id = conversation_id
    st.session_state.messages = load_conversation_messages(conversation_id)
    st.session_state.reformulation_count = 0
    st.session_state.last_user_message = ""
    st.session_state.last_assistant_response = ""
    st.session_state.conversation_start_time = datetime.now()
    st.session_state.partial_response = ""

def delete_conversation(conversation_id: int):
    """Elimina una conversación"""
    db = st.session_state.db
    db.delete_conversation(conversation_id)
    if conversation_id == st.session_state.current_conversation_id:
        create_new_conversation()

def clear_current_conversation():
    """Limpia la conversación actual"""
    st.session_state.messages = []
    st.session_state.db.delete_messages(st.session_state.current_conversation_id)
    st.session_state.reformulation_count = 0
    st.session_state.last_user_message = ""
    st.session_state.last_assistant_response = ""
    st.session_state.conversation_start_time = datetime.now()
    st.session_state.partial_response = ""
    st.success("🗑️ Conversación limpiada")

def rename_conversation(conversation_id: int, new_title: str):
    """Renombra una conversación existente"""
    st.session_state.db.update_conversation_title(conversation_id, new_title)
    st.success(f"✅ Conversación renombrada a: {new_title}")


# ========== INTERFAZ DEL SIDEBAR ==========

def view_conversation_history():
    """Renderiza el historial de conversaciones en el expander"""
    conversations = st.session_state.db.get_conversations()
    if "editing_conv_id" not in st.session_state:
        st.session_state.editing_conv_id = None

    for conv in conversations:
        with st.expander(f"📄 {conv['title']}"):
            st.write(f"**ID:** {conv['id']}")
            st.write(f"**Creada:** {conv['created_at']}")
            st.write(f"**Última actualización:** {conv['updated_at']}")
            if conv['last_message']:
                st.write(f"**Último mensaje:** {conv['last_message'][:100]}...")

            if st.session_state.editing_conv_id == conv['id']:
                new_title = st.text_input("Nuevo título", value=conv['title'], key=f"title_input_{conv['id']}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾", key=f"save_title_{conv['id']}"):
                        if new_title.strip():
                            rename_conversation(conv['id'], new_title.strip())
                            st.session_state.editing_conv_id = None 
                            st.rerun()
                        else:
                            st.warning("El título no puede estar vacío")
                with col2:
                    if st.button("🗑️", help="Cancelar", key=f"cancel_edit_{conv['id']}"):
                        st.session_state.editing_conv_id = None
                        st.rerun()
            else:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"**Título**\n\t{conv['title']}")
                with col2:
                    if st.button("✏️", key=f"edit_btn_{conv['id']}"):
                        st.session_state.editing_conv_id = conv['id']
                        st.rerun()

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📂 Cargar", key=f"load_{conv['id']}"):
                    switch_conversation(conv['id'])
                    st.rerun()
            with col2:
                if st.button("🗑️ Borrar", key=f"delete_{conv['id']}"):
                    delete_conversation(conv['id'])
                    st.rerun()

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

def render_sidebar():
    """Renderiza toda la barra lateral visualmente"""
    with st.sidebar:
        start_time = st.session_state.conversation_start_time
        st.caption(f"🕐 Sesión iniciada: {start_time.strftime('%H:%M:%S')}")
        st.caption("💡 Consejo: Usa 'reformula' para mejorar una respuesta")
        st.divider()

        if st.button("➕ Nueva conversación", use_container_width=True):
            create_new_conversation()
            st.rerun()

        with st.expander("📚 Historial"):
            view_conversation_history()

        st.divider()
        with st.expander("📤 Exportar"):
            if st.button("📥 Exportar actual", use_container_width=True):
                export_current_conversation()
            if st.button("📤 Exportar todas", use_container_width=True):
                export_all_conversations()

        with st.expander("📂 Importar"):
            uploaded_file = st.file_uploader(
                "Importar conversaciones",
                type=["json"],
                key="import_file_uploader"
            )
            if uploaded_file is not None:
                if st.button("📂 Importar archivo", use_container_width=True):
                    import_conversations(uploaded_file)
                    st.rerun()

        with st.expander("📊 Estadísticas"):
            stats = st.session_state.db.get_stats()
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Conversaciones", stats["total_conversations"])
                st.metric("Mensajes", stats["total_messages"])
            with col2:
                st.metric("Truncados", stats["total_truncated"])
                st.metric("Con truncamiento", stats["conversations_with_truncation"])

        st.divider()

        with st.expander("⚙️ API / Proveedor"):
            configure_api_key()