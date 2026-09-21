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

from agent.config import (
    INGEST_FALLBACK_ON_ERROR,
    INGEST_MAX_UNITS_PER_FRAGMENT,
    INGEST_MAX_OUTPUT_TOKENS,
)
from agent.ingest_agent import IngestAgent

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

def _call_deepseek_for_ingest(messages: list[dict]) -> str:
    """Llamada no-JSON a DeepSeek para el agente de ingesta.

    El output es tag-based, no JSON, así que json_mode=False. El tope de
    tokens es más alto que el default porque los fragmentos clasificados
    como index emiten muchas líneas EMIT_UNIT.
    """
    return call_deepseek(
        messages,
        temperature=0.0,
        json_mode=False,
        max_tokens=INGEST_MAX_OUTPUT_TOKENS,
    )

def call_deepseek(messages: List[dict],
                  temperature: float = 0.0,
                  json_mode: bool = True,
                  max_tokens: int = 2048) -> str:
    headers = {
        "Authorization": f"Bearer {_get_deepseek_key()}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model":       DEEPSEEK_MODEL,
        "messages":    messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
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

def split_by_sections(text: str, max_section_chars: int = 12000) -> List[str]:
    """Divide un documento en fragmentos por headers markdown de nivel 1.

    Un header de nivel 1 (`# `) o un separador horizontal (`---`) marca un
    límite natural. Si una sección excede max_section_chars, se subdivide
    con sliding_windows para que el LLM nunca reciba más de lo que puede
    procesar en una sola respuesta.

    Si el documento no tiene headers de nivel 1, se aplica sliding_windows
    directo (comportamiento legacy).
    """
    if not text:
        return []

    # Buscar headers de nivel 1 al inicio de línea. Solo cuentan los que
    # estén en la columna 0 (no los ### embebidos en texto).
    lines = text.split("\n")
    sections: List[str] = []
    current: List[str] = []

    for line in lines:
        is_l1_header = line.startswith("# ") and not line.startswith("## ")
        is_separator = line.strip() == "---" and len(current) > 20  # no partir en frontmatter

        if (is_l1_header or is_separator) and current:
            chunk = "\n".join(current).strip()
            # Descartar fragmentos sin contenido real: solo separadores,
            # solo espacios, o solo la línea "---".
            if chunk and len(chunk.strip("-\n \t")) > 20:
                sections.append(chunk)
            current = [line]
        else:
            current.append(line)

    if current:
        chunk = "\n".join(current).strip()
        if chunk and len(chunk.strip("-\n \t")) > 20: # Ese len(chunk.strip("-\n \t")) > 20 exige al menos 20 caracteres que no sean guiones, saltos de línea, espacios o tabs. Un fragmento que sea solo ---\n---\n no pasa. Un fragmento con contenido real sí.
            sections.append(chunk)

    # Si no se detectó ningún header, caer a sliding_windows sobre el todo.
    if len(sections) <= 1:
        return sliding_windows(text)

    # Subdividir secciones gigantes.
    out: List[str] = []
    for sec in sections:
        if len(sec) <= max_section_chars:
            out.append(sec)
        else:
            out.extend(sliding_windows(sec))
    return out

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
# Prompts de LLM
# ---------------------------------------------------------------------------

_PAGE_SYSTEM = (
    "You process a document fragment (roughly one page) and extract "
    "retrieval-oriented semantic units.\n\n"

    "Return a JSON object with EXACTLY these keys and no other text:\n"
    '  {"units": ["semantic unit 1", "semantic unit 2", ...],'
    '   "page_summary": "concise summary, max 4 sentences",'
    '   "tags": ["tag1", "tag2", ...]}\n\n'

    "A semantic unit is a self-contained piece of knowledge that is useful "
    "when retrieved independently.\n\n"

    "Prefer fewer, richer units over many small units.\n"
    "Do not split individual sentences, claims, explanations, or examples "
    "when they belong to the same subject.\n"
    "Merge related paragraphs that together express one concept, decision, "
    "argument, mechanism, procedure, or section.\n"
    "Split only when there is a meaningful change of subject or purpose.\n\n"

    "Preserve important terminology, names, version numbers, dates, "
    "relationships, section numbers, chapter numbers, and other identifiers "
    "from the source.\n\n"

    "Each unit must contain enough context to be understandable when "
    "retrieved without the original page.\n"
    "Do not invent information that is absent from the source fragment.\n\n"

    "tags = 2-5 concise conceptual labels."
)


_GLOBAL_SYSTEM = (
    "You produce a document-level summary from the supplied fragment summaries.\n\n"
    "Return a JSON object with EXACTLY these keys and no other text:\n"
    '  {"global_summary": "concise summary, max 6 sentences",'
    '   "tags": ["tag1", "tag2", ...]}\n\n'
    "Synthesize the fragment summaries into a coherent representation of the "
    "document. Do not concatenate them.\n"
    "Preserve document identity: title, version, date, status, scope, major "
    "sections, important changes.\n"
    "If the fragment summaries include metadata (version, date, maintainer), "
    "include those values explicitly in the summary.\n"
    "tags = 2-5 concise conceptual labels, lowercase."
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

        # Agente de ingesta
        ingest_agent = IngestAgent(
            llm_call=_call_deepseek_for_ingest,
            fallback_enabled=INGEST_FALLBACK_ON_ERROR,
        )

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

            # 4. Dividir en secciones (fallback a sliding_windows si no hay
            #    headers de nivel 1).
            windows = split_by_sections(text, max_section_chars=12000)
            print(f"  [RAG] {len(windows)} fragmento(s) a procesar")

            # Tags base: combinación de base_tags y extensión del archivo
            ext = Path(filename).suffix.lower().lstrip(".")
            base_tags_for_doc = base_tags + ([ext] if ext else [])

            fragment_summaries: List[str] = []
            unit_counter = 0

            for win_idx, window in enumerate(windows, start=1):
                if progress_callback:
                    progress_callback(
                        file_idx, len(files),
                        f"{filename} — ventana {win_idx}/{len(windows)}",
                    )

                # 5. Clasificar y trocear con el agente
                output = ingest_agent.process(window, filename)
                print(
                    f"    ventana {win_idx}: kind={output.kind}, "
                    f"{len(output.units)} units, "
                    f"whole={'yes' if output.whole else 'no'}, "
                    f"tags={output.tags}"
                )

                # Aplicar tope de seguridad
                units = output.units[:INGEST_MAX_UNITS_PER_FRAGMENT]
                if len(output.units) > INGEST_MAX_UNITS_PER_FRAGMENT:
                    print(
                        f"      ⚠ truncado de {len(output.units)} a "
                        f"{INGEST_MAX_UNITS_PER_FRAGMENT} units"
                    )

                # Combinar tags: los del agente + los base del doc
                merged_tags = normalize_tags(base_tags_for_doc + output.tags)

                # Insertar unidades
                for u_idx, unit_text in enumerate(units, start=1):
                    unit_counter += 1
                    kind = f"{output.kind}_unit"
                    link = f"{filename}#{kind}_{win_idx}_{u_idx}"
                    try:
                        vec = engine.embed_document(unit_text)
                        insert_atomic(
                            conn, index,
                            project_id=project_id,
                            text_link=link,
                            text=unit_text,
                            tags=merged_tags,
                            vec=vec,
                            dim=dim,
                            content_hash=content_hash(unit_text),
                            kind=kind,
                            source_path=filename,
                        )
                        stats["inserted"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        print(f"      {kind} FAIL: {e}")

                # Insertar whole (si aplica — solo index y diagram)
                if output.whole:
                    kind = f"{output.kind}_whole"
                    link = f"{filename}#{kind}_{win_idx}"
                    try:
                        vec = engine.embed_document(output.whole)
                        insert_atomic(
                            conn, index,
                            project_id=project_id,
                            text_link=link,
                            text=output.whole,
                            tags=merged_tags,
                            vec=vec,
                            dim=dim,
                            content_hash=content_hash(output.whole),
                            kind=kind,
                            source_path=filename,
                        )
                        stats["inserted"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        print(f"      {kind} FAIL: {e}")

                # Insertar resumen del fragmento
                if output.summary:
                    kind = f"{output.kind}_summary"
                    link = f"{filename}#{kind}_{win_idx}"
                    try:
                        vec = engine.embed_document(output.summary)
                        insert_atomic(
                            conn, index,
                            project_id=project_id,
                            text_link=link,
                            text=output.summary,
                            tags=merged_tags,
                            vec=vec,
                            dim=dim,
                            content_hash=content_hash(output.summary),
                            kind=kind,
                            source_path=filename,
                        )
                        stats["inserted"] += 1
                    except Exception as e:
                        stats["failed"] += 1
                        print(f"      {kind} FAIL: {e}")

                    fragment_summaries.append(output.summary)

            # 6. Resumen global del documento (solo si hay 2+ ventanas)
            if len(windows) > 1 and fragment_summaries:
                print("  [RAG] Generando resumen global...")
                doc_info = summarize_document(fragment_summaries)
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
                        kind="document_summary",
                        source_path=filename,
                    )
                    stats["inserted"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    print(f"      resumen global FAIL: {e}")

            if progress_callback:
                progress_callback(
                    file_idx, len(files),
                    f"Completado {filename}: {unit_counter} units",
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
