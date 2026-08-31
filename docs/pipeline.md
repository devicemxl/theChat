# RAG Pipeline

| key             | value                                                             |
|-----------------|-------------------------------------------------------------------|
| tipo            | technical document · pipeline design + implementation status      |
| tema            | RAG · ingestion pipeline · query pipeline                         |
| titulo          | RAG Pipeline for theChat                                          |
| maturity        | implemented (semantic mode) + planned (fast mode, reindex worker) |
| confidence      | high (implemented) · medium (planned)                             |
| material origen | D002 + código actual `rag/`                                        |
| fecha           | 2026 (actualizado en Fase 0)                                      |
| mantenedor      | David                                                             |

## 1. Status

El pipeline RAG está **implementado y funcional**:

- Ingesta semántica (DeepSeek) → chunks + embeddings + HNSW.
- Retrieval en el chat con toggle RAG y panel de fuentes.
- Motor local `gleann_engine.dll` + `sp_wrap.dll` + EmbeddingGemma.
- BD: `rag_data/rag_chunks.db`; índice: `rag_data/hnsw_index.bin`.

Lo que sigue siendo diseño: modo rápido sin LLM, reindex worker,
memoria de conversaciones (chunks `kind='conversation'`), herramientas y
código (tKE).

## 2. Flujo de ingesta (implementado)

1. **Adquisición**: `views/ingest.py` sube múltiples archivos y asigna proyecto.
2. **Extracción**: `utils/file_handler.py::extract_text_from_bytes` (única
   implementación, compartida con chat).
3. **Normalización**: NFC.
4. **Chunking**: sliding window, 2000 chars, overlap 500.
5. **Análisis semántico** (por ventana, DeepSeek):
   - `units`: unidades semánticas
   - `page_summary`: resumen de la ventana
   - `tags`: 2-5 etiquetas
   - Fallback: si DeepSeek falla, se guarda la ventana cruda con tag `fallback`.
6. **Embedding**: por unidad, resumen de página y resumen global, con prefijo de
   documento.
7. **Inserción atómica**: SQLite + HNSW en una transacción lógica.
8. **Checkpoint**: `hnsw_index.bin` + `meta.json` al final.
9. **Deduplicación**: si el hash de contenido ya existe en el proyecto, se omite.

Estadísticas: D002 reporta 218 chunks, 0 fallos en pruebas con datos reales.

## 3. Flujo de consulta (implementado)

1. El usuario activa RAG en el toolbar.
2. `views/chat.py` detecta que el chat pertenece a un proyecto con chunks.
3. `retriever.search(query, project_id, top_n=5)`:
   - `engine.embed_query(query)` con prefijo de consulta
   - HNSW kNN con k=50 (over-fetch)
   - Filtrado en SQLite por `project_id`
   - Score = 1 - distancia
4. Los chunks se formatean como contexto en el system prompt.
5. La UI muestra un expander "Fuentes utilizadas" con score y `text_link`.

## 4. Decisiones implementadas

- **BD separada** `rag_chunks.db`, no convive con el historial de chat.
- **Filtrado post-HNSW por proyecto**: sobre-recuperación con k=50.
- **Conexiones SQLite efímeras** en search: se abren y cierran por operación.
- **Prefijos asimétricos**: `task: search result | query:` vs `title: none | text:`.
- **Índice HNSW compartido** entre proyectos; `project_id` en cada chunk.

## 5. Mejoras pendientes (siguientes pasos)

- **Modo rápido** sin DeepSeek (chunking + embed directo).
- **Caché de queries** (evitar re-embedir la misma pregunta).
- **Reindex worker** usando `pending_reindex` para mover chats de proyecto.
- **Memoria de conversaciones**: worker que indexa mensajes como
  `kind='conversation'`, con `parent_message_id` y regla de no indexar el
  último turno.
- **Herramientas como conocimiento**: catálogo + function calling (solo DeepSeek
  primero).
- **Código por narrativa**: clasificador contextual + descifrado agéntico.

## 6. Failure modes (implementados)

- Embeber falla → retry + fallback; si todo falla, el documento se omite y se
  reporta en `stats['failed']`.
- DeepSeek falla en análisis → ventana cruda como fallback, tags `["fallback"]`.
- Índice HNSW no existe/corrompe → reconstrucción desde BD o creación vacía.
- Sin candidatos → la consulta va al LLM sin RAG y la UI avisa.
