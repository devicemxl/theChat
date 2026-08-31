"""
Vista Data / RAG — Ingesta de documentos y asociación a proyectos.

Permite:
  - Seleccionar un proyecto de destino.
  - Subir uno o varios documentos.
  - Ejecutar la ingesta semántica (chunking + DeepSeek + embeddings).
  - Ver progreso en tiempo real.

Los chunks se guardan en `rag_chunks.db` dentro de `rag_data/`.
Cada chunk queda asociado al `project_id` seleccionado.

Requiere que los componentes del motor RAG estén configurados
(`rag/config.py`, `rag/ingestor.py`, DLLs y modelo).
"""

import streamlit as st

from database import ChatDatabase
from ui.components import load_custom_css  # noqa: F401  (CSS ya cargado en app.py)

from utils.extensions import TEXT_EXTENSIONS

import traceback


# ---------------------------------------------------------------------------
# Inicialización defensiva: no romper si se entra directo a esta página.
# ---------------------------------------------------------------------------
if "db" not in st.session_state:
    st.session_state.db = ChatDatabase("chat_history.db")

db: ChatDatabase = st.session_state.db

# ---------------------------------------------------------------------------
# Importar motor RAG (lo envolvemos para dar un mensaje claro si falta algo)
# ---------------------------------------------------------------------------
try:
    from rag import ingestor as rag_ingestor
    from rag import config as rag_config
    RAG_AVAILABLE = True
except ImportError as e:
    RAG_AVAILABLE = False
    rag_ingestor = None
    rag_config = None
    RAG_IMPORT_ERROR = str(e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_rag_prerequisites() -> tuple[list[str], list[str]]:
    """Devuelve (errores_criticos, warnings).

    Crítico = sin esto no se puede embedir ni ingestar.
    Warning = falta algo que se regenera solo (ej. índice HNSW).
    """
    if not RAG_AVAILABLE:
        # No se puede ni importar el paquete → todo es crítico.
        return [f"No se pudieron importar los módulos RAG: {RAG_IMPORT_ERROR}"], []

    if not rag_config:
        return ["No se pudo cargar rag/config.py"], []

    errores: list[str] = []
    warnings: list[str] = []

    # Rutas indispensables para EMBEDIR (sin esto no hay ingesta).
    criticas = {
        "Modelo EmbeddingGemma": rag_config.RAG_MODEL_DIR,
        "Tokenizer SentencePiece": rag_config.RAG_SP_MODEL,
        "DLL del motor (gleann_engine.dll)": rag_config.RAG_ENGINE_LIB,
        "DLL del tokenizer (sp_wrap.dll)": rag_config.RAG_SP_LIB,
        "Pack JSON": rag_config.RAG_PACK_JSON,
    }
    for nombre, path in criticas.items():
        if not path.exists():
            errores.append(f"{nombre} no encontrado: {path}")

    # Rutas regenerables (el índice se reconstruye solo).
    regenerables = {
        "Índice HNSW bin": rag_config.RAG_INDEX_PATH,
        "Índice HNSW meta": rag_config.RAG_INDEX_META_PATH,
    }
    for nombre, path in regenerables.items():
        if not path.exists():
            warnings.append(
                f"{nombre} no encontrado: {path}. "
                "Se reconstruirá automáticamente desde la BD durante la ingesta."
            )

    return errores, warnings

def ingest_uploaded_files(uploaded_files, project_id: int) -> dict:
    """Ejecuta la ingesta con barra de progreso."""
    # Preparar lista de (bytes, nombre)
    files_to_ingest = [(f.getvalue(), f.name) for f in uploaded_files]

    progreso = st.progress(0, text="Preparando ingesta...")
    log_placeholder = st.empty()
    logs = []

    def progress_callback(current: int, total: int, message: str):
        progreso.progress(current / total, text=f"Documento {current}/{total}: {message}")
        logs.append(f"[{current}/{total}] {message}")
        # Mostrar últimos 5 mensajes
        log_placeholder.text("\n".join(logs[-5:]))

    try:
        stats = rag_ingestor.ingest_documents(
            files_to_ingest,
            project_id=project_id,
            mode="semantic",
            progress_callback=progress_callback,
        )
        progreso.progress(1.0, text="Ingesta completada")
        log_placeholder.empty()
        return stats
    except Exception as e:
        progreso.empty()
        log_placeholder.empty()
        raise e


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------

st.title("🔧 Data & RAG")
st.caption(
    "Sube documentos y asócialos a un proyecto. La ingesta genera chunks "
    "semánticos, embeddings y un índice HNSW para búsqueda futura."
)

# 1. Verificar disponibilidad del motor
errores, warnings = check_rag_prerequisites()
if errores:
    st.error("**El motor RAG no está disponible.** Revisa la configuración.")
    for e in errores:
        st.warning(f"- {e}")
    st.info(
        "Asegúrate de que las rutas en `rag/config.py` apunten a los "
        "archivos correctos."
    )
    st.stop()

for w in warnings:
    st.warning(w)

# 2. Cargar proyectos
proyectos = db.get_projects()
if not proyectos:
    st.warning("No hay proyectos. Ve a la pestaña **Projects** y crea uno primero.")
    st.stop()

# 3. Selector de proyecto
project_map = {p["id"]: p for p in proyectos}
project_options = list(project_map.keys())
project_labels = {
    pid: f"{project_map[pid]['icon']} {project_map[pid]['name']}"
    for pid in project_options
}

selected_project_id = st.selectbox(
    "Proyecto de destino",
    options=project_options,
    format_func=lambda pid: project_labels[pid],
)

# 4. Uploader multiarchivo
upload_types = sorted(
    {ext.lstrip(".") for ext in TEXT_EXTENSIONS} | {"pdf", "docx", "csv"}
)

uploaded_files = st.file_uploader(
    "Sube documentos",
    type=upload_types,
    accept_multiple_files=True,
    help="Formatos soportados: texto, Markdown, PDF, DOCX, CSV, JSON, código.",
)

# 5. Botón de ingesta
if uploaded_files:
    st.write(f"**{len(uploaded_files)} archivo(s) seleccionado(s)**")
    if st.button("🚀 Ingestar documentos", type="primary", use_container_width=True):
        try:
            with st.spinner("Ingestando... Esto puede tardar unos minutos."):
                stats = ingest_uploaded_files(uploaded_files, selected_project_id)
            st.success(
                f"✅ Ingesta completada: {stats['inserted']} chunks insertados, "
                f"{stats['failed']} fallidos, {stats['skipped']} omitidos."
            )
        except Exception as e:
            st.error(f"❌ Error durante la ingesta: {e}")
            with st.expander("🔍 Traceback completo"):
                st.code(traceback.format_exc(), language="text")
else:
    st.info("Sube al menos un documento para comenzar.")