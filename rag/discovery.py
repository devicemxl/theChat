"""
discovery.py - Recursive file discovery for ingestion pipelines.

Walks a root directory and returns file paths whose extension matches a
requested category. Text-safe files and binary (requires-extractor) files
are kept as disjoint sets so callers can pick unambiguously.

Also exports legacy aliases ALLOWED_EXTENSIONS / BINARY_EXTENSIONS for
consumers that still use the old names.

Copyright (c) 2026 CogNeu / David Ochoa.
"""

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Extension sets - kept disjoint so a file matches exactly one category.
# NOTE: the trailing comma on each line matters. A missing comma silently
#       string-concatenates two literals in Python (e.g. ".aspx" ".txt" ->
#       ".aspx.txt"), which was a real bug in the previous version.
# ---------------------------------------------------------------------------

CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".java", ".c", ".h", ".cpp", ".hpp",
    ".cs", ".rb", ".php", ".go", ".rs", ".swift", ".kt", ".sql",
})

WEB_EXTENSIONS = frozenset({
    ".html", ".htm", ".xhtml", ".xml", ".rdf", ".css",
    ".svg", ".rss", ".atom", ".asp", ".aspx",
})

DATA_EXTENSIONS = frozenset({
    ".json", ".yaml", ".yml", ".toml", ".sh", ".ini", ".cfg",
})

DOC_EXTENSIONS = frozenset({
    ".txt", ".md", ".rst", ".ipynb",
})

# Binary/office formats. These need an extractor before feeding an embedder;
# discovery lists them separately so plain-text pipelines can skip them.
BINARY_EXTENSIONS = frozenset({
    ".doc", ".docx", ".dot", ".dotx",
    ".xls", ".xlsx", ".xlsm", ".xlt", ".xltx",
    ".ppt", ".pptx", ".pptm", ".pot", ".potx",
    ".mdb", ".accdb", ".pub", ".one",
    ".pdf",
})

TEXT_EXTENSIONS = (CODE_EXTENSIONS | WEB_EXTENSIONS
                   | DATA_EXTENSIONS | DOC_EXTENSIONS)

# Union of everything discovery knows about.
ALL_EXTENSIONS = TEXT_EXTENSIONS | BINARY_EXTENSIONS

# Legacy aliases (kept for the earlier ingest scripts).
ALLOWED_EXTENSIONS = ALL_EXTENSIONS


# Directory names to skip during traversal. Anything that is virtually
# guaranteed to be noise for a retrieval index.
DEFAULT_EXCLUDES = frozenset({
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "env",
    "build", "dist", "target", "out", ".idea", ".vscode",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_documents(
    root_dir: str,
    extensions: set | frozenset | None = None,
    excludes: set | frozenset | None = None,
    follow_symlinks: bool = False,
    max_size_bytes: int | None = None,
) -> list[str]:
    """
    Walk root_dir recursively; return absolute paths for files matching
    `extensions` (defaults to TEXT_EXTENSIONS).

    - Directories in `excludes` are pruned in-place (never entered).
    - Symlinks are not followed by default (avoids cycles).
    - `max_size_bytes` (optional) filters out oversized files.
    """
    if extensions is None:
        extensions = TEXT_EXTENSIONS
    if excludes is None:
        excludes = DEFAULT_EXCLUDES

    root_path = Path(root_dir).resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {root_path}")

    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root_path,
                                                followlinks=follow_symlinks):
        # Prune excluded subdirs in-place so os.walk skips them entirely.
        dirnames[:] = [d for d in dirnames if d not in excludes]

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in extensions:
                continue
            full = Path(dirpath) / fname
            if max_size_bytes is not None:
                try:
                    if full.stat().st_size > max_size_bytes:
                        continue
                except OSError:
                    continue
            out.append(str(full.resolve()))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python discovery.py <root_dir>")
        sys.exit(1)

    root = sys.argv[1]
    try:
        docs = scan_documents(root)
    except NotADirectoryError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Found {len(docs)} text files:")
    for p in docs[:20]:
        print(f"  {p}")
    if len(docs) > 20:
        print(f"  ... and {len(docs) - 20} more.")
