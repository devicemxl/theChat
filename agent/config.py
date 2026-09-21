import os
from pathlib import Path

from utils.extensions import ALLOWED_EXTENSIONS, DEFAULT_EXCLUDES

# Directorio raíz donde el agente puede leer/escribir archivos.
PROJECT_ROOT = Path(os.getenv("AGENT_PROJECT_ROOT", Path.cwd())).resolve()

# Carpetas que SIEMPRE se ignorarán al listar/buscar archivos.
EXCLUDED_DIRS = DEFAULT_EXCLUDES

# Extensiones de archivo que el agente puede leer/escribir (texto plano).
ALLOWED_EXTENSIONS = ALLOWED_EXTENSIONS  # importado de utils.extensions

# Modo por defecto.
DEFAULT_AGENT_MODE = "chat"   # "chat" o "code"

# Proveedor por defecto para el RAG.
AGENT_PROVIDER = "DeepSeek"

# ---------------------------------------------------------------------------
# Ciclo agéntico (plan → ejecución → síntesis)
# ---------------------------------------------------------------------------
# Tope duro de rondas de planificación por turno. Al alcanzarlo, el runtime
# fuerza una ronda final sin parser (el modelo solo puede responder).
MAX_PLAN_ROUNDS = 3

# Tope global de búsquedas por turno, acumulado entre rondas. Al alcanzarlo,
# las SEARCH adicionales se ignoran y se fuerza síntesis.
MAX_SEARCHES_PER_TURN = 5

# Número de chunks devueltos por cada SEARCH al retriever.
TOP_N_PER_SEARCH = 5

# Tope de caracteres del contexto acumulado (histórico + inyecciones de
# resultados). Si se supera, se descartan los chunks de las rondas más
# antiguas. Aproximación por chars porque contar tokens requeriría un
# tokenizador por proveedor.
MAX_CONTEXT_CHARS = 60000

# Compat: código legado que aún importa MAX_ITERATIONS / MAX_RESULTS.
# MAX_ITERATIONS = 10
MAX_RESULTS = 50

# ---------------------------------------------------------------------------
# Agente de ingesta (clasificación + troceo por tipo)
# ---------------------------------------------------------------------------
# Si el LLM falla el protocolo, indexar el fragmento crudo como un solo
# unit en lugar de abortar la ingesta. Preferimos un chunk mediocre a
# perder el documento entero.
INGEST_FALLBACK_ON_ERROR = True

# Tope de seguridad por fragmento: si el modelo emite más de N units
# (comportamiento anómalo), se truncan. Evita que un documento se parta
# en 500 chunks por un mal output.
INGEST_MAX_UNITS_PER_FRAGMENT = 200

# Tope de tokens de salida para la llamada de ingesta. Los fragmentos
# clasificados como index pueden generar muchos tags EMIT_UNIT.
INGEST_MAX_OUTPUT_TOKENS = 8000