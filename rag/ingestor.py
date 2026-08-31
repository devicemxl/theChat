"""
ingestor.py - Ingesta de documentos para theChat RAG.

Este módulo adapta la lógica de ingesta semántica del prototipo CogNeu
(ingest_folder_semantic.py) para trabajar con archivos subidos desde la
interfaz de Streamlit.

Flujo por documento:
  1. Extraer texto (soporta txt, md, pdf, docx, csv, json, código).
  2. Normalizar a NFC.
  3. Dividir en ventanas deslizantes (chunking).
  4. Por cada ventana:
       - DeepSeek genera unidades semánticas, resumen de página y tags.
       - Se embeden e insertan las unidades y el resumen.
  5. Resumen global del documento, se embebe e inserta.
  6. Checkpoint final del índice HNSW.

La base de datos de chunks es `rag_chunks.db` dentro de `rag_data/`.
Cada chunk queda asociado a un `project_id`.

Requiere:
  - Las DLLs y el modelo EmbeddingGemma configurados en `rag/config.py`.
  - La API key de DeepSeek disponible en `st.secrets` o variable de entorno.

Copyright (c) 2026 CogNeu / David Ochoa.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import random
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Callable, List, Tuple, Optional

import hnswlib
import numpy as np
import requests

from utils.file_handler import extract_text_from_bytes

import rag.config as cfg
from rag.engine import GleannEngine
from rag.store import (
    ensure_schema,
    insert_atomic,
    checkpoint,
    verify_consistency,
    rebuild_index_from_db,  # nueva
)

# ---------------------------------------------------------------------------
# Cliente DeepSeek
# ---------------------------------------------------------------------------

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL   = "deepseek-chat"

DEEPSEEK_REQUEST_TIMEOUT = (10, 120)  # (connect, read) seconds
DEEPSEEK_MAX_RETRIES     = 3
DEEPSEEK_BACKOFF_BASE    = 2.0        # seconds; exp * jitter

def _get_deepseek_key() -> str:
    """Obtiene la API key de DeepSeek desde st.secrets o variable de entorno.

    Se intenta primero `st.secrets["DEEPSEEK_API_KEY"]`; si no está disponible,
    se usa la variable de entorno `DEEPSEEK_API_KEY`. Si ninguna existe, se
    lanza un error claro.
    """
    key = ""
    try:
        import streamlit as st
        key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except Exception:
        pass
    if not key:
        key = os.getenv("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY no está configurada. "
            "Añádela a .streamlit/secrets.toml o como variable de entorno."
        )
    return key


def call_deepseek(messages: List[dict],
                  temperature: float = 0.0,
                  json_mode: bool = True) -> str:
    """
    Llama a DeepSeek con reintentos y timeout.
    Si json_mode=True, pide explícitamente response_format json_object.
    """
    headers = {
        "Authorization": f"Bearer {_get_deepseek_key()}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model":       DEEPSEEK_MODEL,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  2048,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_exc: Exception | None = None
    for attempt in range(DEEPSEEK_MAX_RETRIES):
        try:
            resp = requests.post(
                DEEPSEEK_API_URL,
                json=payload,
                headers=headers,
                timeout=DEEPSEEK_REQUEST_TIMEOUT,
            )
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.Timeout, requests.ConnectionError,
                requests.HTTPError) as e:
            last_exc = e
            if attempt == DEEPSEEK_MAX_RETRIES - 1:
                break
            sleep = DEEPSEEK_BACKOFF_BASE * (2 ** attempt) + random.random()
            print(f"    DeepSeek retry {attempt+1}/{DEEPSEEK_MAX_RETRIES} in "
                  f"{sleep:.1f}s ({e})")
            time.sleep(sleep)
    raise RuntimeError(f"DeepSeek call failed after retries: {last_exc}")


# ---------------------------------------------------------------------------
# Pipeline de texto
# ---------------------------------------------------------------------------

CHUNK_SIZE = cfg.RAG_CHUNK_SIZE
OVERLAP    = cfg.RAG_CHUNK_OVERLAP
STRIDE     = CHUNK_SIZE - OVERLAP


def normalize_text(raw: str) -> str:
    """Normaliza a NFC, forma usada por SentencePiece de EmbeddingGemma."""
    return unicodedata.normalize("NFC", raw)


def sliding_windows(text: str) -> List[str]:
    """Divide `text` en ventanas deslizantes de CHUNK_SIZE con OVERLAP."""
    if not text:
        return []
    out = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start += STRIDE
    return out


def normalize_tags(tags: List[str], min_count: int = 2) -> List[str]:
    """Limpia, deduplica y limita los tags; añade 'general' si son muy pocos."""
    seen: set[str] = set()
    out: List[str] = []
    for t in tags or []:
        t = str(t).strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
            if len(out) == 5:
                break
    if len(out) < min_count and "general" not in out:
        out.append("general")
    return out


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Extracción de texto desde bytes
# ---------------------------------------------------------------------------

# ELIMINADA

# ---------------------------------------------------------------------------
# Prompts de DeepSeek
# ---------------------------------------------------------------------------

_PAGE_SYSTEM = (
    "You process document fragments. For the given text fragment (roughly "
    "one page), return a JSON object with EXACTLY these keys and no other "
    "text:\n"
    '  {"units": ["semantic unit 1", "semantic unit 2", ...],'
    '   "page_summary": "concise summary, max 4 sentences",'
    '   "tags": ["tag1", "tag2", ...]}\n'
    "units = coherent paragraphs or complete ideas. "
    "tags = 2-5 concise descriptive labels."
)

_GLOBAL_SYSTEM = (
    "You produce document-level summaries. Given a list of per-page "
    "summaries, return a JSON object with EXACTLY these keys and no other "
    "text:\n"
    '  {"global_summary": "concise summary, max 6 sentences",'
    '   "tags": ["tag1", "tag2", ...]}\n'
    "tags = 2-5 labels describing the overall document."
)


def process_page(page_text: str, page_num: int) -> dict:
    """Llama a DeepSeek para extraer unidades, resumen y tags de una página."""
    messages = [
        {"role": "system", "content": _PAGE_SYSTEM},
        {"role": "user",   "content": f"Fragment (page {page_num}):\n\n{page_text}"},
    ]
    try:
        content = call_deepseek(messages, temperature=0.0)
        result = json.loads(content)
        if not all(k in result for k in ("units", "page_summary", "tags")):
            raise ValueError("JSON missing required keys")
        result["tags"] = normalize_tags(result["tags"])
        return result
    except Exception as e:
        print(f"    page {page_num} fallback: {e}")
        return {
            "units": [page_text],
            "page_summary": "[FALLBACK] " + page_text[:200],
            "tags": ["fallback", "unprocessed"],
        }


def summarize_document(page_summaries: List[str]) -> dict:
    """Genera un resumen global y tags del documento a partir de resúmenes de página."""
    joined = "\n\n".join(f"Page {i+1}: {s}" for i, s in enumerate(page_summaries))
    messages = [
        {"role": "system", "content": _GLOBAL_SYSTEM},
        {"role": "user",   "content": joined},
    ]
    try:
        content = call_deepseek(messages, temperature=0.0)
        result = json.loads(content)
        if "global_summary" not in result or "tags" not in result:
            raise ValueError("JSON missing required keys")
        result["tags"] = normalize_tags(result["tags"])
        return result
    except Exception as e:
        print(f"    global summary fallback: {e}")
        return {
            "global_summary": "[FALLBACK] " + (" ".join(page_summaries))[:500],
            "tags": ["fallback"],
        }


# ---------------------------------------------------------------------------
# Carga / creación del índice HNSW
# ---------------------------------------------------------------------------

def _load_or_create_index(dim: int, conn: Optional[sqlite3.Connection] = None):
    """Carga el índice HNSW existente, lo reconstruye si falta/corrompe,
    o crea uno vacío si no hay datos.

    Nunca lanza por un bin ausente: el peor caso es índice vacío que se
    completará con la ingesta actual y el checkpoint final.
    """
    index_path = str(cfg.RAG_INDEX_PATH)
    meta_path  = str(cfg.RAG_INDEX_META_PATH)

    # 1) Ambos archivos existen → intentar carga normal.
    if Path(index_path).exists() and Path(meta_path).exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("dim") != dim:
                raise ValueError(f"dim mismatch: meta={meta.get('dim')}, motor={dim}")
            idx = hnswlib.Index(space="cosine", dim=dim)
            idx.load_index(index_path)
            idx.set_ef(meta.get("ef", 50))
            print(f"[RAG] Índice HNSW cargado: {idx.element_count} elementos")
            return idx
        except (RuntimeError, OSError, json.JSONDecodeError, ValueError) as e:
            print(f"[RAG] Índice corrupto o incompatible ({e}). Reconstruyendo...")
    else:
        print("[RAG] No hay índice HNSW previo.")

    # 2) Hay conexión a BD y existe data → reconstruir desde BD.
    if conn is not None:
        try:
            row = conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()
            count = row[0] if row else 0
            if count > 0:
                print(f"[RAG] Reconstruyendo índice desde {count} chunks...")
                return rebuild_index_from_db(
                    conn,
                    dim,
                    index_path,
                    meta_path,
                    str(cfg.RAG_DB_PATH),
                )
        except sqlite3.Error as e:
            print(f"[RAG] No se pudo leer la BD para reconstruir: {e}")

    # 3) Sin datos → crear vacío.
    print("[RAG] Creando índice vacío (capacidad 10000).")
    idx = hnswlib.Index(space="cosine", dim=dim)
    idx.init_index(max_elements=10_000, ef_construction=200, M=16)
    idx.set_ef(50)
    return idx

# ---------------------------------------------------------------------------
# Función principal de ingesta
# ---------------------------------------------------------------------------

def ingest_documents(
    files: List[Tuple[bytes, str]],
    project_id: int,
    mode: str = "semantic",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    base_tags: Optional[List[str]] = None,
) -> dict:
    """
    Ingiere una lista de documentos y los asocia a un proyecto.

    Args:
        files: Lista de tuplas (contenido_bytes, nombre_archivo).
        project_id: ID del proyecto al que se asociarán los chunks.
        mode: Modo de procesamiento. Actualmente solo "semantic".
        progress_callback: Función opcional para reportar progreso.
            Recibe (archivo_actual, total_archivos, mensaje).
        base_tags: Tags base a combinar con los generados por el LLM.

    Returns:
        Un dict con estadísticas:
        {
            "inserted": int,   # chunks insertados
            "failed": int,      # chunks fallidos
            "skipped": int,     # documentos saltados por duplicado
            "total_documents": int,
        }
    """
    if mode not in ("semantic",):
        raise ValueError(f"Modo '{mode}' no soportado. Solo 'semantic'.")

    cfg.ensure_dirs()

    engine = None
    conn = None
    try:
        if progress_callback:
            progress_callback(0, len(files), "Inicializando motor de embeddings...")
        engine = GleannEngine(
            engine_lib=str(cfg.RAG_ENGINE_LIB),
            sp_lib=str(cfg.RAG_SP_LIB),
            sp_model=str(cfg.RAG_SP_MODEL),
            model_dir=str(cfg.RAG_MODEL_DIR),
            pack_json=str(cfg.RAG_PACK_JSON),
            target_dim=cfg.RAG_TARGET_DIM,
        )
        dim = engine.target_dim

        # Con esto, si falla la inicialización, la última línea visible en la UI te dirá exactamente el paso que falló.
        if progress_callback:
            progress_callback(0, len(files), "Abriendo base de datos de chunks...")
        conn = sqlite3.connect(str(cfg.RAG_DB_PATH))
        ensure_schema(conn)

        if progress_callback:
            progress_callback(0, len(files), "Cargando índice HNSW...")
        index = _load_or_create_index(dim, conn=conn)

        # Verificación de consistencia al inicio
        db_n, idx_n, ok = verify_consistency(conn, index)
        if not ok:
            print(f"[RAG] ADVERTENCIA: BD={db_n} != índice={idx_n}. "
                  f"Considera reconstruir el índice.")

        stats = {"inserted": 0, "failed": 0, "skipped": 0,
                 "total_documents": len(files)}

        base_tags = base_tags or []

        for file_idx, (data, filename) in enumerate(files, start=1):
            if progress_callback:
                progress_callback(file_idx, len(files), f"Procesando {filename}")

            print(f"\n[RAG] Documento {file_idx}/{len(files)}: {filename}")

            # 1. Extraer texto
            #raw_text = _extract_text_from_bytes(data, filename)
            raw_text = extract_text_from_bytes(data, filename)

            if not raw_text.strip() or raw_text.startswith("[Error"):
                print("  [RAG] Sin texto válido, se omite.")
                stats["skipped"] += 1
                continue

            # 2. Normalizar y hash
            text = normalize_text(raw_text)
            doc_hash = content_hash(text)

            # 3. Verificar duplicado por content_hash dentro del proyecto
            row = conn.execute(
                "SELECT 1 FROM rag_chunks WHERE project_id=? AND content_hash=? LIMIT 1",
                (project_id, doc_hash),
            ).fetchone()
            if row:
                print("  [RAG] Documento ya indexado (hash coincidente), se omite.")
                stats["skipped"] += 1
                continue

            # 4. Dividir en ventanas
            windows = sliding_windows(text)
            print(f"  [RAG] {len(windows)} ventanas de ~{CHUNK_SIZE} caracteres")

            # Tags base: combinación de base_tags y extensión del archivo
            ext = Path(filename).suffix.lower().lstrip(".")
            base_tags_for_doc = base_tags + ([ext] if ext else [])

            page_summaries: List[str] = []
            unit_counter = 0

            for page_num, window in enumerate(windows, start=1):
                # 5. Procesar página con DeepSeek
                page = process_page(window, page_num)
                units = page["units"]
                page_summaries.append(page["page_summary"])
                page_tags = normalize_tags(base_tags_for_doc + page["tags"])
                print(f"    página {page_num}: {len(units)} unidades, tags={page['tags']}")

                # Insertar cada unidad semántica
                for unit_text in units:
                    unit_counter += 1
                    link = f"{filename}#unidad{unit_counter}"
                    try:
                        vec = engine.embed_document(unit_text)
                        insert_atomic(
                            conn, index,
                            project_id=project_id,
                            text_link=link,
                            text=unit_text,
                            tags=page_tags,
                            vec=vec,
                            dim=dim,
                            content_hash=content_hash(unit_text),
                        )
                        stats["inserted"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        print(f"      unidad FAIL: {e}")

                # Insertar resumen de página
                page_link = f"{filename}#pagina{page_num}"
                try:
                    vec = engine.embed_document(page["page_summary"])
                    insert_atomic(
                        conn, index,
                        project_id=project_id,
                        text_link=page_link,
                        text=page["page_summary"],
                        tags=page_tags,
                        vec=vec,
                        dim=dim,
                        content_hash=content_hash(page["page_summary"]),
                    )
                    stats["inserted"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    print(f"      resumen página FAIL: {e}")

            # 6. Resumen global del documento
            print("  [RAG] Generando resumen global...")
            doc_info = summarize_document(page_summaries)
            combined_tags = normalize_tags(base_tags_for_doc + doc_info["tags"])
            try:
                vec = engine.embed_document(doc_info["global_summary"])
                insert_atomic(
                    conn, index,
                    project_id=project_id,
                    text_link=filename,
                    text=doc_info["global_summary"],
                    tags=combined_tags,
                    vec=vec,
                    dim=dim,
                    content_hash=doc_hash,
                )
                stats["inserted"] += 1
            except Exception as e:
                stats["failed"] += 1
                print(f"      resumen global FAIL: {e}")

            if progress_callback:
                progress_callback(
                    file_idx, len(files),
                    f"Completado {filename}: {unit_counter} unidades"
                )
        # 7. Checkpoint final del índice
        print("\n[RAG] Guardando índice HNSW...")
        checkpoint(
            index,
            index_path=str(cfg.RAG_INDEX_PATH),
            meta_path=str(cfg.RAG_INDEX_META_PATH),
            dim=engine.target_dim,
            db_path=str(cfg.RAG_DB_PATH),
        )
        print(f"[RAG] Checkpoint completado. Total elementos en índice: {index.element_count}")

    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass

    return stats


# ---------------------------------------------------------------------------
# Prueba manual (opcional)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Uso: python -m rag.ingestor <project_id> <archivo1> [archivo2 ...]")
        sys.exit(1)

    project_id = int(sys.argv[1])
    files_to_ingest = []

    for path in sys.argv[2:]:
        with open(path, "rb") as f:
            data = f.read()
        files_to_ingest.append((data, Path(path).name))

    result = ingest_documents(
        files_to_ingest,
        project_id=project_id,
        mode="semantic",
    )
    print(f"Resultado: {result}")
