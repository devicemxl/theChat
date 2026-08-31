import streamlit as st

from utils.config import get_secret
from ui.sidebar import clear_current_conversation


# ========== PARÁMETROS POR PROVEEDOR ==========

def get_effort_params(provider: str, effort: str) -> dict:
    """Devuelve los parámetros específicos para el proveedor según el esfuerzo."""
    if provider == "DeepSeek":
        # DeepSeek acepta reasoning_effort como string.
        return {"reasoning_effort": effort}
    elif provider == "Google AI Studio (Gemini)":
        temp_map = {"bajo": 0.3, "medio": 0.7, "alto": 1.0}
        return {"temperature": temp_map.get(effort, 0.7)}
    elif provider == "Mistral AI":
        temp_map = {"bajo": 0.3, "medio": 0.7, "alto": 1.0}
        return {"temperature": temp_map.get(effort, 0.7)}
    elif provider == "Anthropic (Claude)":
        temp_map = {"bajo": 0.3, "medio": 0.7, "alto": 1.0}
        return {"temperature": temp_map.get(effort, 0.7)}
    else:
        return {}


# ========== CONFIGURACIÓN DE UI ==========

def configure_model_effort():
    """Configura el esfuerzo del modelo desde la interfaz."""
    esfuerzo = ["bajo", "medio", "alto"]
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


def configure_api_key():
    """Configura el Proveedor y la API key desde la interfaz."""
    proveedores = ["DeepSeek", "Google AI Studio (Gemini)", "Mistral AI", "Anthropic (Claude)"]

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

    elif st.session_state.api_provider == "Anthropic (Claude)":
        key_input = get_secret("ANTHROPIC_API_KEY")
        st.session_state.anthropic_api_key = key_input
        st.session_state.api_key = key_input


# ========== MODAL DE CONFIRMACIÓN ==========

@st.dialog("Confirmar limpieza")
def confirm_clear_conversation():
    """Modal nativo de Streamlit — pide confirmación antes de vaciar la conversación."""
    st.warning(
        "¿Vaciar toda la conversación actual?\n\n"
        "Los mensajes se eliminarán de la base de datos y esta acción no se puede deshacer."
    )
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("🗑️ Sí, vaciar", type="primary", use_container_width=True, key="dlg_clear_yes"):
            clear_current_conversation()
            st.rerun()
    with col_no:
        if st.button("Cancelar", use_container_width=True, key="dlg_clear_no"):
            st.rerun()


# ========== BARRA DE HERRAMIENTAS SUPERIOR ==========

def _render_project_selector():
    """Selector de proyecto para la conversación actual.

    Al cambiar, reasigna la conversación al proyecto elegido (o None para
    'Sin proyecto') y hace rerun para reflejar el cambio en el sidebar.
    """
    db = st.session_state.db
    current_id = st.session_state.current_conversation_id
    current_conv = db.get_conversation(current_id)
    current_project_id = current_conv.get("project_id") if current_conv else None

    projects = db.get_projects()
    project_map = {p["id"]: p for p in projects}

    # None = "Sin proyecto" (siempre primero).
    options = [None] + [p["id"] for p in projects]

    def fmt(pid):
        if pid is None:
            return "— Sin proyecto —"
        p = project_map[pid]
        return f"{p['icon']} {p['name']}"

    try:
        current_idx = options.index(current_project_id)
    except ValueError:
        # El proyecto fue borrado por otro flujo — degradar a 'Sin proyecto'.
        current_idx = 0

    # Key único por conversación: evita que el widget quede pegado a un valor
    # antiguo cuando se cambia de chat.
    selected_pid = st.selectbox(
        "Proyecto",
        options=options,
        index=current_idx,
        format_func=fmt,
        key=f"project_selector_{current_id}",
    )

    if selected_pid != current_project_id:
        db.assign_conversation_to_project(current_id, selected_pid)
        st.rerun()


def render_toolbar():
    """Renderiza el expander superior con toda la configuración de sesión.

    Retorna:
        tuple[list | None, bool]:
          - uploaded_files: lista de archivos subidos por el uploader (o None).
          - api_key_ok:     False si falta la API key (el caller debe abortar).
    """
    msgX = "Enjoy It"
    uploaded_files = None
    api_key_ok = True

    if st.session_state.agent_mode == "code":
        msgX = "Modo Code activado: el asistente podrá explorar y modificar archivos (con restricciones)."

    header = (
        f"Conversación #{st.session_state.current_conversation_id} | "
        f"Mensajes: {len(st.session_state.messages)} | "
        f"Reformulaciones: {st.session_state.total_reformulations} | "
        f"Provider: {st.session_state.api_provider}"
    )

    with st.expander(label=header):
        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1:
            configure_api_key()
            if not st.session_state.api_key:
                msgX = (
                    f"⚠️ Configura tu API Key de {st.session_state.api_provider} "
                    f"en la barra lateral o en config.toml."
                )
                api_key_ok = False

        with col2:
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

        with col4:
            uploaded_files = st.file_uploader(
                "📎 Adjuntar archivos (opcional)",
                accept_multiple_files=True,
                key=f"file_uploader_{st.session_state.uploader_key}",
                label_visibility="collapsed",
                help="Sube archivos de texto, PDF, DOCX, CSV, JSON, código, etc."
            )
            if uploaded_files:
                msgX = f"📎 Archivos adjuntos: {', '.join([f.name for f in uploaded_files])}"

        with col5:
            _render_project_selector()

        with col6:
            st.caption("Vaciar Platica")
            if st.button("🗑️ ", key="btn_clear_top"):
                # Abre el modal de confirmación en vez de limpiar directo.
                confirm_clear_conversation()

        # Indicador de system-prompt del proyecto (si aplica).
        # Se aplica DESPUÉS de los checks de columnas para no borrar el warning
        # de "falta API key" (más urgente), y ANTES del st.info final. Los
        # mensajes de acción activa (archivos adjuntos, modo Code) tienen
        # prioridad y ya sobreescribieron msgX arriba si aplica; por eso solo
        # sobreescribimos si msgX sigue siendo el default "Enjoy It".
        if api_key_ok and msgX == "Enjoy It":
            active_project = st.session_state.db.get_conversation_project(
                st.session_state.current_conversation_id
            )
            if active_project and active_project.get("system_prompt"):
                msgX = (
                    f"🔧 System-prompt del proyecto **{active_project['icon']} "
                    f"{active_project['name']}** activo — reemplaza al default "
                    "y omite la lógica de reformulación."
                )
                
        # --- Toggle RAG ---
        if st.session_state.get("rag_available", False):
            active_project = st.session_state.db.get_conversation_project(
                st.session_state.current_conversation_id
            )
            default_rag = st.session_state.get("rag_enabled", False)
            st.checkbox(
                "📚 Activar RAG (contexto de documentos)",
                value=default_rag,
                key="rag_enabled",
                help="Busca y añade información de los documentos del proyecto a la respuesta.",
            )

        st.info(msgX)

    return uploaded_files, api_key_ok