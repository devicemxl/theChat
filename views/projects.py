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
from turtle import clear, color
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
    name = st.text_input("Nombre *", placeholder="Ej: Raites")
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

@st.dialog("Edit")
def dialog_edit(project: dict):
    # Inject CSS targeting Streamlit's internal modal test IDs
    st.html("""
        <style>
        div[data-testid="stDialog"] div[role="dialog"] {
            width: 80vw !important; /* Forces the dialog to take up 80% of viewport width */
            max-width: 1200px;     /* Optional: sets an upper boundary */
        }
        </style>
        """)
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

@st.dialog("Toughs")
def dialog_toughs(project: dict):
    # Inject CSS targeting Streamlit's internal modal test IDs
    st.html("""
        <style>
        div[data-testid="stDialog"] div[role="dialog"] {
            width: 80vw !important; /* Forces the dialog to take up 80% of viewport width */
            max-width: 1200px;     /* Optional: sets an upper boundary */
        }
        .stTextArea {
            overflow-y:hidden;
        }
        </style>
        """)
    st.markdown(
        f"<div style='background:{color};height:20px;border-radius:4px;margin-bottom:12px;'>You</div>",
        unsafe_allow_html=True
    )
    tagDict = {"Summary": "cogneu — CogNeu: a closed, auditable neutrosophic cognitive architecture and its encyclopedia corpus.",
               "Architecture Decisions": "CogNeu ADRs, load-bearing architectural principles, and the technical stack — read before touching any layer boundary or logic choice\n\n", 
               "Principles": "A Git-first architecture for knowledge storage enables a key differentiator: semantic time-travel queries at near-zero additional cost.\nConsistent documentation structure across ecosystem components (problem statement, architecture, use cases, competitive positioning, roadmap) helps establish a coherent product identity.",
               "Design Patterns": "CogNeu Design Patterns, the reusable solutions to common problems in the architecture\n\n",
               "Approach": "David works at the intersection of architecture design and documentation — conversations blend technical implementation details with product vision and positioning.\n\nPrefers comprehensive, structured artifacts (README.md, vision docs) that consolidate prior context.\n\nUses reference documents from existing components (e.g. Bealach) as templates when documenting new ones (e.g. trunKV), to keep the ecosystem consistent.","Thinks": "As ecosystem, individual components are designed with clear interfaces and roles relative to the whole",
               }
    for tag, definition in tagDict.items():
        col_youTag, col_youDef, col_youDate = st.columns(3)
        with col_youTag:
            st.caption(tag)
        with col_youDef:
            st.text_area(value=definition, height=75,label=tag,disabled=True, max_chars=20)
        with col_youDate:
            st.caption("Date")

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
            col_info, col_think, col_edit, col_del = st.columns([10, 0.5, 0.5, 0.5])
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
                        
            # Ver platica con deepseek:
            # https://chat.deepseek.com/a/chat/s/035e4297-bc42-4011-b745-d42c17418e8d
            with col_think:
                if st.button("💭", key=f"think_{p['id']}", help="Memory", type="secondary"):
                    dialog_toughs(p)
            with col_edit:
                if st.button("✏️", key=f"edit_{p['id']}", help="Edit", type="secondary"):
                    dialog_edit(p)
            with col_del:
                if st.button("🗑️", key=f"del_{p['id']}", help="Delete", type="primary"):
                    dialog_delete(p)
