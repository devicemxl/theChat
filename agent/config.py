# agent/config.py
import os
from pathlib import Path

# Directorio raíz donde el agente puede leer/escribir archivos.
# Por defecto, el directorio actual de trabajo (donde se ejecuta Streamlit).
# En producción, se puede cambiar mediante variable de entorno o en la UI.
PROJECT_ROOT = Path(os.getenv("AGENT_PROJECT_ROOT", Path.cwd())).resolve()

# Carpetas que SIEMPRE se ignorarán al listar/buscar archivos.
EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "venv",
    ".venv",
    "env",
    ".env",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".DS_Store",
}

# Extensiones de archivo que el agente puede leer/escribir (texto plano).
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst",
    ".py", ".js", ".ts", ".go", ".c", ".h", ".cpp", ".hpp",
    ".odin", ".rs", ".java", ".json", ".yml", ".yaml", ".toml",
    ".xml", ".html", ".css", ".sql", ".csv",
}

# Límite de iteraciones del ciclo agéntico.
MAX_ITERATIONS = 10

# Máximo número de resultados devueltos por herramientas de exploración.
MAX_RESULTS = 50

# Modo por defecto. Se puede sobrescribir en la UI.
DEFAULT_AGENT_MODE = "chat"   # "chat" o "code"

# Proveedor por defecto para el agente (en esta fase solo DeepSeek).
AGENT_PROVIDER = "DeepSeek"