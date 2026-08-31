"""
store.py - Atomic SQLite + HNSW insertion helpers for theChat RAG.

Adaptado para theChat:
  * Table `rag_chunks` with a mandatory `project_id` column.
  * Stores the text content of each chunk alongside its embedding and tags.
  * Uses a separate SQLite database (`rag_chunks.db`) and HNSW index file.
  * All cross-store operations are atomic at the row level.

The original code was adapted from the standalone CogNeu RAG prototype.
Copyright (c) 2026 CogNeu / David Ochoa.
"""

import json
import sqlite3
import struct
from pathlib import Path
from typing import Iterable

import numpy as np


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS rag_chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL,
    text_link    TEXT    NOT NULL,
    text         TEXT    NOT NULL,
    embedding    BLOB    NOT NULL,
    tags         TEXT    NOT NULL DEFAULT '[]',
    content_hash TEXT    DEFAULT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_project ON rag_chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_link    ON rag_chunks(text_link);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_hash    ON rag_chunks(content_hash);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the `rag_chunks` table and indexes if missing."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Sizing / capacity
# ---------------------------------------------------------------------------

def resize_if_needed(index, extra_slots: int = 1, growth_factor: int = 2) -> None:
    """Ensure the HNSW index has capacity for `extra_slots` more items."""
    needed = index.element_count + extra_slots
    if needed <= index.max_elements:
        return
    new_cap = max(needed, index.max_elements * growth_factor)
    index.resize_index(new_cap)


# ---------------------------------------------------------------------------
# Atomic insertion
# ---------------------------------------------------------------------------

def insert_atomic(
    conn: sqlite3.Connection,
    index,
    project_id: int,
    text_link: str,
    text: str,
    tags: list[str],
    vec: np.ndarray,
    dim: int,
    content_hash: str | None = None,
) -> int:
    """
    Insert a single chunk (embedding, link, text, tags, project_id) into
    SQLite `rag_chunks` and the HNSW index as one logical unit.

    Sequence:
      1. BEGIN SQLite transaction.
      2. INSERT row -> obtain rowid.
      3. Ensure HNSW capacity, then add_items([vec], [rowid]).
      4. COMMIT SQLite. Both writes are visible.

    Failure modes:
      - INSERT fails                    -> rollback, no HNSW change. Raise.
      - add_items fails                 -> rollback SQLite. HNSW untouched
                                           (single-item add_items is atomic
                                           in hnswlib). Raise.
      - COMMIT fails (disk full, etc.)  -> rollback SQLite; HNSW already
                                           has the row. Best-effort
                                           mark_deleted to clean up. Raise.

    Returns the new SQLite rowid on success.
    """
    if vec.shape != (dim,):
        raise ValueError(f"vec shape {vec.shape} != expected ({dim},)")
    if not np.isfinite(vec).all():
        raise ValueError("vec contains NaN or Inf")

    emb_blob  = sqlite3.Binary(struct.pack(f"{dim}f", *vec.astype(np.float32)))
    tags_json = json.dumps(list(tags))

    conn.execute("BEGIN")
    rowid = None
    added_to_index = False
    try:
        cursor = conn.execute(
            "INSERT INTO rag_chunks "
            "(project_id, text_link, text, embedding, tags, content_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, text_link, text, emb_blob, tags_json, content_hash),
        )
        rowid = cursor.lastrowid

        resize_if_needed(index, extra_slots=1)
        index.add_items([vec.astype(np.float32)], [rowid])
        added_to_index = True

        conn.execute("COMMIT")
        return rowid
    except Exception:
        # SQLite rollback first (cheap, always safe).
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        # If HNSW got the row but the transaction did not commit, remove it.
        if added_to_index and rowid is not None:
            try:
                index.mark_deleted(rowid)
            except Exception:
                pass  # Already inconsistent; verify_consistency will surface it.
        raise


# ---------------------------------------------------------------------------
# Duplicate suppression via content hash
# ---------------------------------------------------------------------------

def link_or_hash_exists(
    conn: sqlite3.Connection,
    text_link: str,
    content_hash: str | None = None,
    project_id: int | None = None,
) -> bool:
    """
    Return True if a row with the same text_link or content_hash already
    exists. Optionally restrict the check to a specific project_id.

    Callers use this to skip re-embedding unchanged content.
    """
    if project_id is not None:
        if content_hash is not None:
            row = conn.execute(
                "SELECT 1 FROM rag_chunks "
                "WHERE (text_link = ? OR content_hash = ?) AND project_id = ? "
                "LIMIT 1",
                (text_link, content_hash, project_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM rag_chunks "
                "WHERE text_link = ? AND project_id = ? LIMIT 1",
                (text_link, project_id),
            ).fetchone()
    else:
        if content_hash is not None:
            row = conn.execute(
                "SELECT 1 FROM rag_chunks "
                "WHERE text_link = ? OR content_hash = ? LIMIT 1",
                (text_link, content_hash),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM rag_chunks WHERE text_link = ? LIMIT 1",
                (text_link,),
            ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Consistency check + checkpoint
# ---------------------------------------------------------------------------

def verify_consistency(conn: sqlite3.Connection, index) -> tuple[int, int, bool]:
    """
    Compare SQLite row count and HNSW element count.
    Returns (db_count, index_count, ok). Callers decide how to react
    (warn, rebuild index from BD, abort).
    """
    row = conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()
    db_count  = int(row[0])
    idx_count = int(index.element_count)
    return db_count, idx_count, (db_count == idx_count)


def checkpoint(
    index,
    index_path: str,
    meta_path: str,
    dim: int,
    db_path: str,
    space: str = "cosine",
    extra: dict | None = None,
) -> None:
    """
    Persist the HNSW index and its meta.json together.
    Meta is written after the index to bias against half-writes.
    """
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)
    index.save_index(index_path)

    meta = {
        "dim": dim,
        "num_elements": index.element_count,
        "index_path": index_path,
        "db_path": db_path,
        "space": space,
        "ef": index.ef,
    }
    if extra:
        meta.update(extra)

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# ---------------------------------------------------------------------------
# Blob helpers (for readers rebuilding the index from BD)
# ---------------------------------------------------------------------------

def unpack_blob(blob: bytes, dim: int) -> np.ndarray:
    """Decode a stored embedding BLOB back into a float32 numpy array."""
    if isinstance(blob, str):
        # Legacy: earlier scripts stored JSON strings instead of BLOBs.
        return np.array(json.loads(blob), dtype=np.float32)
    return np.frombuffer(blob, dtype=np.float32, count=dim).copy()


def iter_all_embeddings(
    conn: sqlite3.Connection, dim: int
) -> Iterable[tuple[int, np.ndarray]]:
    """Yield (rowid, vec) for every row in rag_chunks."""
    for rowid, blob in conn.execute("SELECT id, embedding FROM rag_chunks"):
        yield rowid, unpack_blob(blob, dim)