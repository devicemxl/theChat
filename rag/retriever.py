"""
retriever.py - Recuperación de chunks relevantes para una consulta.

Clase RAGRetriever:
  * Carga el motor GleannEngine, el índice HNSW y la BD de chunks.
  * Dado un query y un project_id, devuelve los chunks más relevantes
    dentro de ese proyecto, con su texto, link, tags y score de similitud.
  * Se puede usar directamente en la vista de chat (manteniéndolo en
    session_state) o de forma puntual.

Uso desde CLI (prueba):
  python rag/retriever.py --query "¿Qué es RAG?" --project-id 1
  python rag/retriever.py --query "embeddings"    # lista proyectos y usa el primero

Requiere que existan datos ingestados (rag_chunks.db + hnsw_index.bin).

Copyright (c) 2026 CogNeu / David Ochoa.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

import hnswlib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import rag.config as cfg
from rag.engine import GleannEngine


class RAGRetriever:
    """Recuperador RAG: motor + índice HNSW + BD de chunks."""

    def __init__(self):
        cfg.ensure_dirs()

        # 1. Inicializar motor de embeddings
        self.engine = GleannEngine(
            engine_lib=str(cfg.RAG_ENGINE_LIB),
            sp_lib=str(cfg.RAG_SP_LIB),
            sp_model=str(cfg.RAG_SP_MODEL),
            model_dir=str(cfg.RAG_MODEL_DIR),
            pack_json=str(cfg.RAG_PACK_JSON),
            target_dim=cfg.RAG_TARGET_DIM,
        )
        self.dim = self.engine.target_dim

        # 2. Cargar índice HNSW (debe existir ya)
        meta_path = cfg.RAG_INDEX_META_PATH
        index_path = cfg.RAG_INDEX_PATH
        if not meta_path.exists() or not index_path.exists():
            raise FileNotFoundError(
                f"No se encontró el índice HNSW en {index_path}. "
                "Ingesta documentos primero."
            )
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        self.index = hnswlib.Index(space="cosine", dim=meta["dim"])
        self.index.load_index(str(index_path))
        self.index.set_ef(meta.get("ef", 50))

        # 3. Conectar a la BD de chunks
        self.conn = sqlite3.connect(str(cfg.RAG_DB_PATH))

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        project_id: Optional[int] = None,
        top_n: int = 5,
        k_hnsw: int = 50,
    ) -> List[Dict]:
        """
        Busca los `top_n` chunks más relevantes para `query`.

        Args:
            query: Texto de consulta del usuario.
            project_id: Filtrar por proyecto. Si None, busca en todos.
            top_n: Número de resultados a devolver.
            k_hnsw: Over-fetch inicial del índice (50 por defecto).

        Returns:
            Lista de dicts con keys:
                id, project_id, text_link, text, tags, score
            Ordenados por score descendente (mayor = más relevante).
        """
        # 1. Embedding de la consulta con prefijo de query
        q_vec = self.engine.embed_query(query)

        # 2. kNN con over-fetch
        k = min(k_hnsw, self.index.element_count)
        if k <= 0:
            return []

        labels, distances = self.index.knn_query(q_vec, k=k)
        candidate_ids = labels[0].tolist()
        dist_by_id = {
            int(i): float(d) for i, d in zip(candidate_ids, distances[0])
        }

        # 3. Recuperar filas candidatas desde SQLite
        placeholders = ",".join("?" for _ in candidate_ids)
        sql = (
            "SELECT id, project_id, text_link, text, tags "
            "FROM rag_chunks "
            f"WHERE id IN ({placeholders})"
        )
        params: List = candidate_ids

        if project_id is not None:
            sql += " AND project_id = ?"
            params = candidate_ids + [project_id]

        rows = self.conn.execute(sql, params).fetchall()

        # 4. Convertir a resultados con score (similitud = 1 - distancia)
        results = []
        for rowid, pid, link, text, tags_json in rows:
            if project_id is not None and pid != project_id:
                continue  # defensivo, aunque el filtro SQL ya lo limita
            tags = json.loads(tags_json) if tags_json else []
            results.append({
                "id": rowid,
                "project_id": pid,
                "text_link": link,
                "text": text,
                "tags": tags,
                "score": 1 - dist_by_id[rowid],
            })

        # 5. Ordenar por score y recortar a top_n
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def list_projects(self) -> List[int]:
        """Devuelve los project_id que tienen chunks indexados."""
        rows = self.conn.execute(
            "SELECT DISTINCT project_id FROM rag_chunks"
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def close(self):
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
        if hasattr(self, "engine"):
            self.engine.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# ---------------------------------------------------------------------------
# CLI de prueba
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--query", type=str, default="¿Qué es RAG?",
                   help="Texto de la consulta")
    p.add_argument("--project-id", type=int, default=None,
                   help="ID del proyecto (si no se indica, lista disponibles)")
    p.add_argument("--top-n", type=int, default=5,
                   help="Número de resultados a mostrar")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    try:
        with RAGRetriever() as retriever:
            # 1. Determinar proyecto
            projects = retriever.list_projects()
            if not projects:
                print("No hay chunks indexados. Ingiesta documentos primero.")
                return 1

            if args.project_id is None:
                print("Proyectos disponibles con chunks:", projects)
                project_id = projects[0]
                print(f"Usando el primero: {project_id}")
            else:
                if args.project_id not in projects:
                    print(f"El proyecto {args.project_id} no tiene chunks. "
                          f"Disponibles: {projects}")
                    return 1
                project_id = args.project_id

            # 2. Buscar
            print(f"\nConsulta: '{args.query}'")
            print(f"Proyecto: {project_id}\n")

            results = retriever.search(args.query, project_id=project_id,
                                       top_n=args.top_n)

            if not results:
                print("No se encontraron resultados.")
                return 0

            for i, r in enumerate(results, 1):
                print(f"\n--- Resultado {i} (score={r['score']:.4f}) ---")
                print(f"Origen: {r['text_link']}")
                print(f"Tags: {r['tags']}")
                print(f"Texto: {r['text'][:300]}...")

            return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())