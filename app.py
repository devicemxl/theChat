"""Entry point de la app.

Configura la página, aplica CSS global y registra las vistas mediante
st.navigation. Cada vista es un script independiente en views/.
"""
import streamlit as st

from ui.components import load_custom_css

# --- Configuración de página (única, aplica a todas las vistas) ---
st.set_page_config(
    page_title="💬 Multi-IA Chat",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",  # navigation vive en el sidebar
)

load_custom_css()

# --- Registro de vistas ---
chat_page     = st.Page("views/chat.py",     title="Chat",     icon="🗨️", default=True)
projects_page = st.Page("views/projects.py", title="Projects", icon="🏗️")
ingest_page   = st.Page("views/ingest.py",   title="Data",     icon="🔧")

pg = st.navigation([chat_page, projects_page, ingest_page])
pg.run()
