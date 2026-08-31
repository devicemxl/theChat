"""
Configuración central para el motor RAG.
Las rutas y parámetros se resuelven en este orden:
1. Variables de entorno (RAG_*)
2. st.secrets (si la app corre en Streamlit)
3. Valores por defecto (relativos a la raíz del proyecto theChat)
"""

import os
from pathlib import Path

# Raíz del proyecto theChat (un nivel arriba de rag/)
BASE_DIR = Path(__file__).resolve().parent.parent


def _get_env_or_secret(key: str, default: str) -> str:
    """Obtiene valor de variable de entorno, st.secrets o default."""
    # 1. Variable de entorno
    env_val = os.getenv(key)
    if env_val:
        return env_val
    # 2. Streamlit secrets (si disponible)
    try:
        import streamlit as st
        secret_val = st.secrets.get(key)
        if secret_val:
            return secret_val
    except Exception:
        pass
    # 3. Default
    return default


# ---------------------------------------------------------------------------
# Rutas de datos (BD y archivos HNSW)
# ---------------------------------------------------------------------------
RAG_DATA_DIR        = Path(_get_env_or_secret("RAG_DATA_DIR", str(BASE_DIR / "rag_data")))
RAG_DB_PATH         = Path(_get_env_or_secret("RAG_DB_PATH", str(RAG_DATA_DIR / "rag_chunks.db")))
RAG_INDEX_PATH      = Path(_get_env_or_secret("RAG_INDEX_PATH", str(RAG_DATA_DIR / "hnsw_index.bin")))
RAG_INDEX_META_PATH = Path(_get_env_or_secret("RAG_INDEX_META_PATH", str(RAG_DATA_DIR / "hnsw_index_meta.json")))

# ---------------------------------------------------------------------------
# Rutas del modelo y DLLs
# ---------------------------------------------------------------------------
RAG_MODEL_DIR   = Path(_get_env_or_secret("RAG_MODEL_DIR", str(BASE_DIR / "models" / "embeddinggemma-300m")))
RAG_SP_MODEL    = Path(_get_env_or_secret("RAG_SP_MODEL", str(RAG_MODEL_DIR / "tokenizer.model")))
RAG_ENGINE_LIB  = Path(_get_env_or_secret("RAG_ENGINE_LIB", str(BASE_DIR / "runtime" / "gleann_engine.dll")))
RAG_SP_LIB      = Path(_get_env_or_secret("RAG_SP_LIB", str(BASE_DIR / "runtime" / "sp_wrap.dll")))
RAG_PACK_JSON   = Path(_get_env_or_secret("RAG_PACK_JSON", str(BASE_DIR / "models" / "embeddinggemma-300m.json")))

# ---------------------------------------------------------------------------
# Parámetros del motor
# ---------------------------------------------------------------------------
RAG_TARGET_DIM    = int(_get_env_or_secret("RAG_TARGET_DIM", "256"))
RAG_CHUNK_SIZE    = int(_get_env_or_secret("RAG_CHUNK_SIZE", "2000"))
RAG_CHUNK_OVERLAP = int(_get_env_or_secret("RAG_CHUNK_OVERLAP", "500"))

# Podemos añadir una función para crear directorios si no existen
def ensure_dirs():
    """Crea los directorios necesarios para RAG."""
    RAG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAG_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    Path(RAG_ENGINE_LIB).parent.mkdir(parents=True, exist_ok=True)
    Path(RAG_SP_LIB).parent.mkdir(parents=True, exist_ok=True)
    Path(RAG_PACK_JSON).parent.mkdir(parents=True, exist_ok=True)