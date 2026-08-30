"""Vista de gestión de proyectos.

CRUD sobre la tabla `projects`. Cada proyecto puede tener:
  - nombre único
  - descripción libre
  - system_prompt (si se define, REEMPLAZA al default en los chats del proyecto)
  - emoji (input libre)
  - color (paleta curada de 8)

Los chats se asignan a proyectos desde la vista Chat (Fase 3 del refactor).
Al borrar un proyecto los chats quedan en 'Sin proyecto', nunca se eliminan.
"""
import sqlite3
import streamlit as st

from database import ChatDatabase
from utils.constants import PROJECT_COLORS

# --- Init defensivo: entrar directo a esta página no debe reventar ---
if "db" not in st.session_state:
    st.session_state.db = ChatDatabase("chat_history.db")

db: ChatDatabase = st.session_state.db


# ========== MODALES ==========

@st.dialog("Nuevo proyecto")
def dialog_create():
    name = st.text_input("Nombre *", placeholder="Ej: Raitec")
    icon = st.text_input(
        "Emoji",
        value="📁",
        max_chars=4,
        help="Cualquier emoji para identificar visualmente el proyecto"
    )
    color = st.selectbox(
        "Color",
        PROJECT_COLORS,
        format_func=lambda c: f"⬤  {c}"
    )
    st.markdown(
        f"<div style='background:{color};height:20px;border-radius:4px;margin-bottom:12px;'></div>",
        unsafe_allow_html=True
    )
    description = st.text_area("Descripción (opcional)", height=80)
    system_prompt = st.text_area(
        "System prompt (opcional)",
        height=150,
        placeholder="Ej: Eres parte de un pipeline. Solo responde, no opines...",
        help="Si lo defines, REEMPLAZA al system-prompt default en los chats de este proyecto."
    )

    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Crear", type="primary", use_container_width=True, key="dlg_create_ok"):
            if not name.strip():
                st.error("El nombre es obligatorio.")
            else:
                try:
                    db.create_project(
                        name=name,
                        description=description or None,
                        system_prompt=system_prompt or None,
                        icon=icon or "📁",
                        color=color,
                    )
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Ya existe un proyecto llamado '{name.strip()}'.")
    with col_cancel:
        if st.button("Cancelar", use_container_width=True, key="dlg_create_cancel"):
            st.rerun()


@st.dialog("Editar proyecto")
def dialog_edit(project: dict):
    name = st.text_input("Nombre *", value=project["name"])
    icon = st.text_input("Emoji", value=project.get("icon") or "📁", max_chars=4)

    current_color = project.get("color") or PROJECT_COLORS[0]
    color_idx = PROJECT_COLORS.index(current_color) if current_color in PROJECT_COLORS else 0
    color = st.selectbox(
        "Color",
        PROJECT_COLORS,
        index=color_idx,
        format_func=lambda c: f"⬤  {c}"
    )
    st.markdown(
        f"<div style='background:{color};height:20px;border-radius:4px;margin-bottom:12px;'></div>",
        unsafe_allow_html=True
    )
    description = st.text_area(
        "Descripción",
        value=project.get("description") or "",
        height=80
    )
    system_prompt = st.text_area(
        "System prompt",
        value=project.get("system_prompt") or "",
        height=150,
        help="Reemplaza al system-prompt default. Vacío = usar default."
    )

    col_ok, col_cancel = st.columns(2)
    with col_ok:
        if st.button("Guardar", type="primary", use_container_width=True, key="dlg_edit_ok"):
            if not name.strip():
                st.error("El nombre es obligatorio.")
            else:
                try:
                    db.update_project(
                        project["id"],
                        name=name,
                        description=description or None,
                        system_prompt=system_prompt or None,
                        icon=icon or "📁",
                        color=color,
                    )
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error(f"Ya existe un proyecto llamado '{name.strip()}'.")
    with col_cancel:
        if st.button("Cancelar", use_container_width=True, key="dlg_edit_cancel"):
            st.rerun()


@st.dialog("Eliminar proyecto")
def dialog_delete(project: dict):
    st.warning(
        f"¿Eliminar el proyecto **{project.get('icon', '📁')} {project['name']}**?"
    )
    n_chats = project.get("conversation_count", 0)
    if n_chats > 0:
        st.info(
            f"📌 Los **{n_chats}** chat(s) asociados quedarán en 'Sin proyecto'. "
            "No se eliminan."
        )
    st.caption(
        "⚠️ Esta acción no se puede deshacer. "
        "El backup a zip está pendiente de implementación."
    )

    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("🗑️ Eliminar", type="primary", use_container_width=True, key="dlg_del_ok"):
            db.delete_project(project["id"])
            st.rerun()
    with col_no:
        if st.button("Cancelar", use_container_width=True, key="dlg_del_cancel"):
            st.rerun()


# ========== VISTA ==========

st.title("🏗️ Projects")
st.caption(
    "Organiza tus chats por proyecto. Cada proyecto puede tener su propio "
    "system-prompt, que reemplaza al default para todos los chats del proyecto."
)

col_left, col_right = st.columns([3, 1])
with col_left:
    st.subheader("Tus proyectos")
with col_right:
    if st.button("➕ Nuevo proyecto", use_container_width=True, type="primary"):
        dialog_create()

projects = db.get_projects()

if not projects:
    st.info("Aún no tienes proyectos. Crea el primero con el botón de arriba.")
else:
    for p in projects:
        with st.container(border=True):
            col_info, col_edit, col_del = st.columns([8, 1, 1])
            with col_info:
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:10px;'>"
                    f"<div style='width:14px;height:14px;background:{p['color']};"
                    f"border-radius:3px;flex-shrink:0;'></div>"
                    f"<span style='font-size:18px;font-weight:600;'>"
                    f"{p['icon']} {p['name']}</span>"
                    f"<span style='color:#888;font-size:13px;'>"
                    f"· {p['conversation_count']} chat(s)</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if p.get("description"):
                    st.caption(p["description"])
                if p.get("system_prompt"):
                    with st.expander("Ver system prompt"):
                        st.code(p["system_prompt"], language="text")

            with col_edit:
                if st.button("✏️", key=f"edit_{p['id']}", help="Editar"):
                    dialog_edit(p)
            with col_del:
                if st.button("🗑️", key=f"del_{p['id']}", help="Eliminar"):
                    dialog_delete(p)
