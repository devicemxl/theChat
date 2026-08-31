import os
from pathlib import Path

from utils.extensions import ALLOWED_EXTENSIONS, DEFAULT_EXCLUDES

# Directorio raíz donde el agente puede leer/escribir archivos.
PROJECT_ROOT = Path(os.getenv("AGENT_PROJECT_ROOT", Path.cwd())).resolve()

# Carpetas que SIEMPRE se ignorarán al listar/buscar archivos.
EXCLUDED_DIRS = DEFAULT_EXCLUDES

# Extensiones de archivo que el agente puede leer/escribir (texto plano).
ALLOWED_EXTENSIONS = ALLOWED_EXTENSIONS  # importado de utils.extensions

# Límite de iteraciones del ciclo agéntico.
MAX_ITERATIONS = 10

# Máximo número de resultados devueltos por herramientas de exploración.
MAX_RESULTS = 50

# Modo por defecto.
DEFAULT_AGENT_MODE = "chat"   # "chat" o "code"

# Proveedor por defecto para el agente.
AGENT_PROVIDER = "DeepSeek"