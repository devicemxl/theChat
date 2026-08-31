"""
test_ingestion.py - Prueba end-to-end de la ingesta RAG.

Ejecuta la ingesta semántica sobre un documento de ejemplo y verifica:
  - Que los chunks se insertan en la BD (rag_chunks.db).
  - Que el índice HNSW tiene el mismo número de elementos.
  - Que todos los chunks quedan asociados al project_id de prueba.
  - Que la BD y el índice son consistentes tras la operación.

Usa un directorio temporal para no afectar los datos reales del sistema.
Para ejecutar: python rag/test_ingestion.py (desde la raíz de theChat)
"""
import os
import sys
import tempfile
from pathlib import Path

# Ajustar variables de entorno ANTES de importar el módulo config
# para redirigir la salida a un directorio temporal.
_tmp = tempfile.TemporaryDirectory()
os.environ["RAG_DATA_DIR"] = _tmp.name
os.environ["RAG_DB_PATH"] = os.path.join(_tmp.name, "test_rag.db")
os.environ["RAG_INDEX_PATH"] = os.path.join(_tmp.name, "test_hnsw.bin")
os.environ["RAG_INDEX_META_PATH"] = os.path.join(_tmp.name, "test_hnsw_meta.json")

# Asegurarse de que el directorio raíz del proyecto esté en el path,
# no la carpeta test, para que 'rag' se resuelva como paquete.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag import ingestor, config

def main() -> int:
    print("=== Test de ingesta RAG ===\n")

    # 1. Verificar pre-requisitos
    print("[1] Verificando que el motor RAG esté disponible...")
    try:
        import importlib
        importlib.reload(config)  # recargar con las env vars temporales
        # Comprobar rutas
        paths = [
            config.RAG_ENGINE_LIB,
            config.RAG_SP_LIB,
            config.RAG_MODEL_DIR,
            config.RAG_SP_MODEL,
            config.RAG_PACK_JSON,
        ]
        for p in paths:
            if not p.exists():
                print(f"  ❌ No existe: {p}")
                print("Asegúrate de que la Fase 0 esté completa.")
                return 1
        print("  ✅ Motor RAG disponible.")
    except Exception as e:
        print(f"  ❌ Error al verificar: {e}")
        return 1

    # 2. Crear un documento de prueba (varias veces un texto largo)
    print("\n[2] Preparando documento de prueba...")
    doc_text = """
    La inteligencia artificial generativa está transformando la forma en que
    las empresas gestionan el conocimiento. Este documento explora el uso de
    modelos de lenguaje para construir asistentes internos capaces de
    recuperar información de grandes corpus de documentos técnicos.

    Para ello se utilizan técnicas de Retrieval-Augmented Generation (RAG),
    que combinan un índice vectorial con un modelo generativo. El proceso
    comienza con la ingestión de documentos: se extrae el texto, se divide
    en fragmentos semánticos, se generan resúmenes y etiquetas mediante un
    LLM, y finalmente se obtienen embeddings para cada fragmento.

    Los embeddings se almacenan en una base de datos vectorial junto con
    metadatos como el proyecto al que pertenecen, el origen del fragmento
    y las etiquetas asociadas. Cuando un usuario realiza una consulta,
    se calcula el embedding de la consulta y se buscan los fragmentos
    más similares dentro del mismo proyecto.

    La elección del modelo de embeddings es crucial. En este proyecto se
    utiliza EmbeddingGemma, un modelo ligero y rápido que produce vectores
    de 256 dimensiones mediante truncamiento MRL. Esto permite reducir el
    espacio de almacenamiento sin sacrificar calidad.

    El índice HNSW permite búsquedas aproximadas por similitud de coseno
    en tiempo logarítmico, incluso con millones de vectores. En la
    práctica, se combina con filtrado por proyecto para asegurar que la
    información recuperada pertenezca al contexto correcto.

    Este documento es solo un ejemplo para probar la ingesta de archivos
    de texto. Los resultados de la prueba no se añadirán a los datos
    reales del sistema.
    """
    demo_file = (doc_text.encode("utf-8"), "demo_rag_test.md")
    print(f"  Documento: {demo_file[1]} ({len(doc_text)} caracteres)")

    # 3. Ejecutar la ingesta
    print("\n[3] Ejecutando ingesta...")
    try:
        stats = ingestor.ingest_documents(
            [demo_file],
            project_id=123,  # ID de prueba; no necesita existir
            mode="semantic",
        )
        print(f"  Estadísticas: {stats}")
    except Exception as e:
        print(f"  ❌ Falló la ingesta: {e}")
        return 1

    if stats["inserted"] == 0:
        print("  ❌ No se insertó ningún chunk.")
        return 1

    # 4. Verificar BD
    print("\n[4] Verificando base de datos...")
    import sqlite3
    conn = sqlite3.connect(config.RAG_DB_PATH)
    try:
        count = conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]
        print(f"  Filas en rag_chunks: {count}")
        if count != stats["inserted"]:
            print("  ❌ El número de filas no coincide con los insertados.")
            return 1

        # Verificar que todos los chunks tienen project_id=123
        wrong_project = conn.execute(
            "SELECT COUNT(*) FROM rag_chunks WHERE project_id != 123"
        ).fetchone()[0]
        if wrong_project > 0:
            print(f"  ❌ Hay {wrong_project} chunks con project_id incorrecto.")
            return 1
        print("  ✅ Base de datos correcta (todos los chunks con project_id=123).")
    finally:
        conn.close()

    # 5. Verificar índice HNSW
    print("\n[5] Verificando índice HNSW...")
    import hnswlib, json
    try:
        with open(config.RAG_INDEX_META_PATH) as f:
            meta = json.load(f)
        index = hnswlib.Index(space="cosine", dim=meta["dim"])
        index.load_index(str(config.RAG_INDEX_PATH))
        idx_count = index.element_count
        print(f"  Elementos en índice: {idx_count}")
        if idx_count != count:
            print("  ❌ El índice no coincide con la BD.")
            return 1
        print("  ✅ Índice HNSW consistente con la BD.")
    except Exception as e:
        print(f"  ❌ Error al cargar índice: {e}")
        return 1

    print("\n=== Prueba completada con ÉXITO ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())