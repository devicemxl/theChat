"""
store.py - Atomic SQLite + HNSW insertion helpers for theChat RAG.

Adaptado para theChat:
  * Tabla `rag_chunks` con columna obligatoria `project_id`.
  * Guarda el contenido textual del chunk junto a su embedding y tags.
  * Usa una base de datos SQLite separada (`rag_chunks.db`) y un archivo de índice HNSW.
  * Todas las operaciones entre BD e índice son atómicas a nivel de fila.

Código original adaptado del prototipo CogNeu RAG.
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
    """Crea la tabla `rag_chunks` y sus índices si no existen."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Sizing / capacity
# ---------------------------------------------------------------------------

def resize_if_needed(index, extra_slots: int = 1, growth_factor: int = 2) -> None:
    """Asegura que el índice HNSW tenga capacidad para `extra_slots` elementos más."""
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
    Inserta un chunk (embedding, link, texto, tags, project_id) en SQLite
    `rag_chunks` y en el índice HNSW como una sola unidad lógica.

    Secuencia:
      1. BEGIN de SQLite.
      2. INSERT de la fila -> obtener rowid.
      3. Asegurar capacidad del HNSW y add_items([vec], [rowid]).
      4. COMMIT de SQLite. Ambos writes son visibles.

    Modos de fallo:
      - Si INSERT falla              -> rollback, sin cambios en HNSW. Raise.
      - Si add_items falla           -> rollback SQLite. HNSW queda intacto
                                        (add_items de un solo item es atómico
                                        en hnswlib). Raise.
      - Si COMMIT falla              -> rollback SQLite; HNSW ya tiene la fila.
                                        Se intenta mark_deleted. Raise.

    Devuelve el nuevo rowid SQLite si todo sale bien.
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
        # Primero rollback SQLite (barato y siempre seguro).
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        # Si HNSW recibió la fila pero la transacción no commitó, limpiarlo.
        if added_to_index and rowid is not None:
            try:
                index.mark_deleted(rowid)
            except Exception:
                pass  # Inconsistencia detectable por verify_consistency.
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
    Devuelve True si ya existe una fila con el mismo text_link o content_hash.
    Opcionalmente restringe la verificación a un proyecto concreto.

    Se usa para evitar re-embeber contenido que no ha cambiado.
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
    Compara el número de filas en SQLite y elementos en HNSW.
    Devuelve (db_count, index_count, ok). El llamador decide cómo reaccionar
    (avisar, reconstruir índice desde BD, abortar).
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
    Persiste el índice HNSW y su meta.json juntos.
    El meta se escribe después del índice para reducir el riesgo de escrituras a medias.
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
# Blob helpers (para lectores que reconstruyen el índice desde BD)
# ---------------------------------------------------------------------------

def unpack_blob(blob: bytes, dim: int) -> np.ndarray:
    """Decodifica un BLOB de embedding guardado a un array numpy float32."""
    if isinstance(blob, str):
        # Legacy: scripts anteriores guardaban strings JSON en lugar de BLOBs.
        return np.array(json.loads(blob), dtype=np.float32)
    return np.frombuffer(blob, dtype=np.float32, count=dim).copy()


def iter_all_embeddings(
    conn: sqlite3.Connection, dim: int
) -> Iterable[tuple[int, np.ndarray]]:
    """Yield (rowid, vec) por cada fila de rag_chunks."""
    for rowid, blob in conn.execute("SELECT id, embedding FROM rag_chunks"):
        yield rowid, unpack_blob(blob, dim)