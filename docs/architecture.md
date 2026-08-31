# Architecture

| key             | value                                                              |
|-----------------|--------------------------------------------------------------------|
| tipo            | technical document · system architecture                           |
| tema            | software architecture · personal chat interface + RAG              |
| titulo          | theChat Architecture                                               |
| maturity        | current implementation (chat + RAG) + planned tKE layers           |
| confidence      | high (current) · medium (planned)                                  |
| material origen | development log through 2026 + integración RAG real                |
| fecha           | 2026 (actualizado en Fase 0)                                       |
| mantenedor      | David                                                              |

## 1. Scope

theChat es una app Streamlit de chat multi-proveedor con historial SQLite,
proyectos y un motor RAG funcional. Este documento describe la arquitectura
actual (chat + RAG) y las capas planeadas del modelo tKE (conversaciones,
herramientas, código).

Todo lo marcado como "implementado" corre hoy. Lo marcado como "planeado"
es diseño sujeto a revisión.

## 2. Design principles

- **Simplicidad sobre abstracción**: un solo proceso Streamlit, SQLite local,
  índice vectorial HNSW como archivo local.
- **Separación por módulos claros**: `views/`, `ui/`, `utils/`, `llm/`, `rag/`,
  `database.py`.
- **Migraciones idempotentes**: `_migrate()` escribe solo columnas/índices que
  faltan, nunca destruye datos.
- **Referencias, no copias**: fork de conversaciones y RAG de memoria usan
  `parent_message_id` (Fase 1+).
- **Seguridad por plan, no por paso**: en Code Mode el agente propone un plan,
  el usuario lo aprueba, git da red de seguridad (Fase 5+).

## 3. Component layout

```
Streamlit process
├── app.py                    entry point, st.navigation
├── views/
│   ├── chat.py               conversación + integración RAG
│   ├── projects.py           CRUD proyectos
│   └── ingest.py             Data & RAG: subida, ingesta, progreso
├── ui/
│   ├── sidebar.py            historial agrupado, init_database, estado RAG
│   ├── toolbar.py            provider/modo/esfuerzo/proyecto + toggle RAG
│   └── components.py         CSS, copy button, helpers
├── llm/
│   └── api_clients.py        streaming: DeepSeek, Gemini, Mistral, Anthropic
├── rag/
│   ├── config.py             rutas de modelo, BD, índice
│   ├── engine.py             wrapper ctypes GleannEngine + SentencePiece
│   ├── store.py              schema rag_chunks + inserciones atómicas + HNSW
│   ├── ingestor.py           ingesta semántica (chunking + DeepSeek + embed)
│   ├── retriever.py          búsqueda HNSW + filtrado por proyecto
│   └── discovery.py          scanner de archivos del proyecto
├── agent/
│   └── config.py             constantes para Code Mode (futuro)
├── utils/
│   ├── config.py             get_secret
│   ├── constants.py          paleta de colores
│   ├── extensions.py         ÚNICA fuente de verdad de extensiones/exclusiones
│   ├── file_handler.py       extracción central de texto (chat + RAG)
│   └── data_export.py        import/export
├── database.py               ChatDatabase sobre SQLite
└── chat_history.db           SQLite (conversaciones, mensajes, proyectos)
```

## 4. Data model

### 4.1 `chat_history.db`

**conversations**

| columna           | tipo      | notas                                   |
|-------------------|-----------|-----------------------------------------|
| id                | INTEGER   | PK                                      |
| title             | TEXT      |                                         |
| created_at        | TIMESTAMP |                                         |
| updated_at        | TIMESTAMP |                                         |
| message_count     | INTEGER   |                                         |
| is_active         | INTEGER   | soft-delete                             |
| project_id        | INTEGER   | NULL = sin proyecto                     |
| indexed_at        | TIMESTAMP | reservado para memoria de conversaciones|
| pending_reindex   | INTEGER   | reservado para worker de reindexado     |

**messages**

| columna            | tipo      | notas                                  |
|--------------------|-----------|----------------------------------------|
| id                 | INTEGER   | PK                                     |
| conversation_id    | INTEGER   | FK lógico                              |
| role               | TEXT      | user / assistant / system              |
| content            | TEXT      |                                        |
| truncated          | INTEGER   |                                        |
| interrupted_at     | TEXT      |                                        |
| reformulation_count| INTEGER   |                                        |
| created_at         | TIMESTAMP |                                        |
| parent_message_id  | INTEGER   | NUEVO — para fork por referencia (Fase 1) |

**projects**

| columna        | tipo      | notas                          |
|----------------|-----------|--------------------------------|
| id             | INTEGER   | PK                             |
| name           | TEXT      | UNIQUE                         |
| description    | TEXT      |                                |
| system_prompt  | TEXT      | reemplaza al default si no vacío|
| icon           | TEXT      | emoji                          |
| color          | TEXT      | hex                            |
| created_at     | TIMESTAMP |                                |

### 4.2 `rag_data/rag_chunks.db`

**rag_chunks** (esquema ampliado tKE)

| columna            | tipo      | notas                                     |
|--------------------|-----------|-------------------------------------------|
| id                 | INTEGER   | PK                                        |
| project_id         | INTEGER   | filtro obligatorio en retrieval           |
| text_link          | TEXT      | formato estable (documento, o `conv:...`) |
| text               | TEXT      | contenido del chunk                       |
| embedding          | BLOB      | vector INT8 cuantizado                    |
| tags               | TEXT      | JSON array                                |
| content_hash       | TEXT      | deduplicación                             |
| created_at         | TIMESTAMP |                                           |
| kind               | TEXT      | `document`, `conversation`, `tool`, `code`|
| status             | TEXT      | `indexed`, `pending`, `needs_user_input`  |
| source_path        | TEXT      | ruta del archivo original (código/docs)   |
| source_message_id  | INTEGER   | mensaje de origen (conversación)          |
| parent_message_id  | INTEGER   | cadena de fork (conversación)             |
| narrativa          | TEXT      | descripción semántica (código descifrado) |

Índices: project_id, text_link, content_hash, kind, status, source_message_id.

## 5. Flujo de chat actual

1. El usuario escribe y opcionalmente adjunta archivos.
2. `views/chat.py` extrae el texto con `utils/file_handler.py::extract_text_from_bytes`
   (única implementación compartida con RAG).
3. El mensaje se guarda en `messages`.
4. Si RAG está activo (`st.session_state.rag_enabled`) y el chat pertenece a un
   proyecto con chunks, `RAGRetriever.search()` obtiene los top-N y se inyectan
   como contexto adicional al system prompt.
5. `build_context_with_reformulation_awareness` arma el contexto (system prompt
   del proyecto o default + contexto RAG + historial).
6. El streaming del proveedor elegido se ejecuta y la respuesta se persiste.
7. Si hubo fuentes RAG, se muestran en un expander con score y `text_link`.

## 6. RAG pipeline (implementado)

- **Ingesta** (`rag/ingestor.py`): modo `semantic` — extraer texto, normalizar NFC,
  sliding window (2000 chars, overlap 500), DeepSeek extrae unidades/resumen/tags,
  embeddings con GleannEngine (EmbeddingGemma 256d, INT8), inserción atómica
  SQLite + HNSW, checkpoint final.
- **Retrieval** (`rag/retriever.py`): embed query con prefijo, HNSW kNN (k=50),
  filtrado por `project_id` en SQLite, top_n por score.
- **Almacenamiento**: `rag_data/rag_chunks.db` + `hnsw_index.bin` +
  `hnsw_index_meta.json`.
- **Motor**: `rag/engine.py` — ctypes sobre `gleann_engine.dll` y `sp_wrap.dll`,
  prefijos de tarea (query/document), cuantización bloque-wise int8.
- **Robustez**: si el índice no existe o está corrupto, se reconstruye desde la BD
  o se crea vacío. La ingesta nunca se bloquea por un bin faltante.
- **Duplicados**: hash de contenido (unidad, página, documento) para evitar
  re-embedir.

## 7. Estado de capas tKE

| Capa               | Estado        | Notas                             |
|--------------------|---------------|-----------------------------------|
| Documents          | ✅ Implementada| chunks con kind='document'        |
| Conversations      | 🔲 Preparada   | columnas y parent_message_id listos; falta worker |
| Tools              | 🔲 Diseño      | catálogo Python + function calling|
| Code               | 🔲 Diseño      | narrativa/descifrado, Fase 4      |

## 8. Non-goals

Sin autenticación multi-usuario, sin despliegue remoto, sin búsqueda
cross-proyecto en la UI, sin RAG-on automático (el usuario controla el toggle).