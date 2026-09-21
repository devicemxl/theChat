import streamlit as st
from datetime import datetime
from typing import List, Dict

# Importamos la base de datos (asumiendo que database.py está en la raíz)
from database import ChatDatabase

from utils.config import get_secret
from utils.file_handler import extract_files_from_message
from utils.data_export import (
    export_current_conversation, 
    export_all_conversations, 
    import_conversations
)

# ========== UTILIDADES DE ESTADO ==========

def init_database():
    """Inicializa la base de datos y todas las variables de estado (session_state)"""
    if "db" not in st.session_state:
        st.session_state.db = ChatDatabase("chat_history.db")
        # Limpieza defensiva al arranque: elimina conversaciones vacías de
        # sesiones previas. Corre ANTES de crear la nueva de este arranque
        # para no borrarla por accidente.
        st.session_state.db.delete_empty_conversations()

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

    if "anthropic_api_key" not in st.session_state:
        st.session_state.anthropic_api_key = get_secret("ANTHROPIC_API_KEY")

    if "api_key" not in st.session_state:
        st.session_state.api_key = st.session_state.deepseek_api_key

    if "partial_response" not in st.session_state:
        st.session_state.partial_response = ""

    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
        
    # --- Variables RAG ---
    if "rag_enabled" not in st.session_state:
        st.session_state.rag_enabled = False

    if "rag_retriever" not in st.session_state:
        try:
            from rag.retriever import RAGRetriever
            st.session_state.rag_retriever = RAGRetriever()
            st.session_state.rag_available = True
        except Exception as e:
            print(f"[RAG] Retriever no disponible: {e}")
            st.session_state.rag_retriever = None
            st.session_state.rag_available = False

# ========== GESTIÓN DE CONVERSACIONES ==========

def load_conversation_messages(conversation_id: int) -> List[Dict]:
    """Carga los mensajes de una conversación desde la base de datos.

    Si la conversación es una rama, incluye los mensajes de la madre
    hasta el punto de fork seguidos de los propios.
    """
    db = st.session_state.db
    messages = db.get_messages_for_context(conversation_id)

    formatted_messages = []
    for msg in messages:
        content = msg["content"]

        if msg["role"] == "user" and "--- Contenido de '" in content:
            prompt, files = extract_files_from_message(content)
            formatted_messages.append({
                "id": msg["id"],                     # ← NUEVO
                "role": msg["role"],
                "content": content,
                "display_content": prompt,
                "files": files,
                "truncated": msg["truncated"],
                "interrupted_at": msg["interrupted_at"],
                "agent_status": msg.get("agent_status"),
                "rounds_used": msg.get("rounds_used"),
                "searches_used": msg.get("searches_used"),
                "metadata_json": msg.get("metadata_json"),
                "reformulation_count": msg.get("reformulation_count") or 0
            })
        else:
            formatted_messages.append({
                "id": msg["id"],                     # ← NUEVO
                "role": msg["role"],
                "content": msg["content"],
                "truncated": msg["truncated"],
                "interrupted_at": msg["interrupted_at"],
                "agent_status": msg.get("agent_status"),
                "rounds_used": msg.get("rounds_used"),
                "searches_used": msg.get("searches_used"),
                "metadata_json": msg.get("metadata_json"),
                "reformulation_count": msg.get("reformulation_count") or 0
            })
    return formatted_messages

def create_new_conversation():
    """Crea una nueva conversación y la establece como actual.

    Herencia de proyecto: si la conversación actual pertenece a un proyecto,
    la nueva hereda ese proyecto. Racional: el 90% del tiempo, el usuario que
    crea un chat nuevo mientras está viendo un proyecto quiere el nuevo en
    ese mismo proyecto. Para uno sin proyecto lo cambia manualmente en el
    selector del toolbar.
    """
    db = st.session_state.db
    title = f"Conversación {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    # Detectar el proyecto de la conversación actual (si aplica).
    parent_project_id = None
    if "current_conversation_id" in st.session_state:
        current = db.get_conversation(st.session_state.current_conversation_id)
        if current:
            parent_project_id = current.get("project_id")

    new_id = db.create_conversation(title)
    if parent_project_id is not None:
        db.assign_conversation_to_project(new_id, parent_project_id)

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
    # Limpieza: elimina vacías del histórico ANTES de cargar la seleccionada.
    # Excluimos la que se está cargando: aunque esté vacía, el usuario la
    # eligió deliberadamente y podría querer continuarla.
    st.session_state.db.delete_empty_conversations(exclude_ids=[conversation_id])

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
    """DEPRECATED: usar _dialog_rename_conv directamente. Se mantiene por compat."""
    st.session_state.db.update_conversation_title(conversation_id, new_title)
    st.success(f"✅ Conversación renombrada a: {new_title}")


# ========== INTERFAZ DEL SIDEBAR ==========

@st.dialog("Renombrar conversación")
def _dialog_rename_conv(conv: Dict):
    """Modal para renombrar una conversación."""
    new_title = st.text_input("Nuevo título", value=conv["title"], key=f"rename_input_{conv['id']}")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Guardar", type="primary", use_container_width=True, key=f"rename_ok_{conv['id']}"):
            if not new_title.strip():
                st.error("El título no puede estar vacío.")
            else:
                st.session_state.db.update_conversation_title(conv["id"], new_title.strip())
                st.rerun()
    with col_cancel:
        if st.button("Cancelar", use_container_width=True, key=f"rename_cancel_{conv['id']}"):
            st.rerun()


@st.dialog("Eliminar conversación")
def _dialog_delete_conv(conv: Dict):
    """Modal de confirmación para eliminar una conversación (soft delete)."""
    st.warning(f"¿Eliminar la conversación **{conv['title']}**?")
    st.caption("Los mensajes se ocultan pero permanecen en la base de datos.")
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("🗑️ Eliminar", type="primary", use_container_width=True, key=f"delconv_ok_{conv['id']}"):
            delete_conversation(conv["id"])
            st.rerun()
    with col_no:
        if st.button("Cancelar", use_container_width=True, key=f"delconv_cancel_{conv['id']}"):
            st.rerun()


def _render_conversation_row(conv: Dict, is_branch: bool = False, mother_title: str = ""):
    """Renderiza una conversación como fila compacta con título, id y acciones.

    Las ramas se muestran sangradas con prefijo 🌿. Si tienen mensajes propios
    se muestra el título real; si no, aparece 'Rama #id'.
    """
    is_current = conv["id"] == st.session_state.current_conversation_id
    conv_id = conv["id"]
    title = conv["title"]
    extra = " (sin msgs)" if is_branch and conv.get("msg_count", 0) == 0 else ""

    if is_branch:
        icon = "🌿"
        if mother_title and title == mother_title:
            label = f"{icon} Rama #{conv_id}{extra}"
        else:
            label = f"{icon} {title} #{conv_id}{extra}"
    else:
        icon = "▶️" if is_current else "📄"
        label = f"{icon} {title} #{conv_id}"

    # Layout: para ramas añadimos una columna de indentación
    if is_branch:
        cols = st.columns([0.7, 3.3, 1, 1, 1])
        indent_col, title_col, id_col, edit_col, del_col = cols
        with indent_col:
            st.write("")  # sangría visual
    else:
        cols = st.columns([4, 1, 1, 1])
        title_col, id_col, edit_col, del_col = cols

    with title_col:
        if st.button(
            label,
            key=f"load_{conv_id}",
            use_container_width=True,
            type="primary" if is_current else "secondary",
        ):
            if not is_current:
                switch_conversation(conv_id)
                st.rerun()
    with id_col:
        st.caption(f"#{conv_id}")
    with edit_col:
        if st.button("✏️", key=f"edit_{conv_id}", help="Renombrar"):
            _dialog_rename_conv(conv)
    with del_col:
        if st.button("🗑️", key=f"del_{conv_id}", help="Eliminar"):
            _dialog_delete_conv(conv)

def _render_conversation_entry(entry: Dict):
    """Renderiza una conversación madre y sus ramas debajo de ella."""
    mother = entry["conversation"]
    mother_title = mother["title"]
    _render_conversation_row(mother, is_branch=False)

    for branch in entry.get("branches", []):
        _render_conversation_row(branch, is_branch=True, mother_title=mother_title)

def view_conversation_history():
    """Renderiza el historial agrupado por proyecto, con ramas bajo su madre.

    Cada proyecto se muestra como un expander; la sección 'Sin proyecto'
    va siempre al final. Se auto-expande el grupo que contiene la
    conversación activa (ya sea madre o rama).
    """
    db = st.session_state.db
    groups = db.get_conversations_grouped()
    current_id = st.session_state.current_conversation_id

    for group in groups:
        project = group["project"]
        entries = group["conversations"]

        if project:
            label = f"{project['icon']} {project['name']} ({len(entries)})"
        else:
            label = f"📄 Sin proyecto ({len(entries)})"

        # Auto-expandir si el grupo contiene la conversación actual
        contains_current = False
        for entry in entries:
            if entry["conversation"]["id"] == current_id:
                contains_current = True
                break
            if any(b["id"] == current_id for b in entry.get("branches", [])):
                contains_current = True
                break

        with st.expander(label, expanded=contains_current):
            if not entries:
                st.caption("_Sin conversaciones_")
                continue
            for entry in entries:
                _render_conversation_entry(entry)

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

        st.subheader("📚 Historial")
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