"""Central de extensiones de archivo y exclusiones de directorio.

Única fuente de verdad para:
  - qué extensiones se consideran texto plano (TEXT_EXTENSIONS)
  - cuáles requieren extractor especial (BINARY_EXTENSIONS)
  - qué carpetas se ignoran al recorrer el sistema de archivos (DEFAULT_EXCLUDES)

Los demás módulos importan desde aquí; nunca definas conjuntos duplicados.
"""

# ---------------------------------------------------------------------------
# Extensiones de código
# ---------------------------------------------------------------------------
CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".rb", ".php", ".go", ".rs", ".swift", ".kt", ".sql",
    ".odin",
})

# ---------------------------------------------------------------------------
# Extensiones web
# ---------------------------------------------------------------------------
WEB_EXTENSIONS = frozenset({
    ".html", ".htm", ".xhtml", ".xml", ".rdf", ".css",
    ".svg", ".rss", ".atom", ".asp", ".aspx",
})

# ---------------------------------------------------------------------------
# Extensiones de datos / configuración
# ---------------------------------------------------------------------------
DATA_EXTENSIONS = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".sh", ".ini", ".cfg",
    ".csv",
})

# ---------------------------------------------------------------------------
# Extensiones de documentación
# ---------------------------------------------------------------------------
DOC_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".ipynb",
})

# ---------------------------------------------------------------------------
# Binarios / office (requieren extractor antes de embedir)
# ---------------------------------------------------------------------------
BINARY_EXTENSIONS = frozenset({
    ".doc", ".docx", ".dot", ".dotx",
    ".xls", ".xlsx", ".xlsm", ".xlt", ".xltx",
    ".ppt", ".pptx", ".pptm", ".pot", ".potx",
    ".mdb", ".accdb", ".pub", ".one",
    ".pdf",
})

# ---------------------------------------------------------------------------
# Conjuntos derivados
# ---------------------------------------------------------------------------
TEXT_EXTENSIONS = CODE_EXTENSIONS | WEB_EXTENSIONS | DATA_EXTENSIONS | DOC_EXTENSIONS
ALL_EXTENSIONS  = TEXT_EXTENSIONS | BINARY_EXTENSIONS

# Alias para el agente de código (solo texto plano)
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS

# ---------------------------------------------------------------------------
# Exclusiones de directorio (unión de agent/config y discovery)
# ---------------------------------------------------------------------------
DEFAULT_EXCLUDES = frozenset({
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "env", ".env",
    "build", "dist", "target", "out",
    ".idea", ".vscode", ".DS_Store",
})