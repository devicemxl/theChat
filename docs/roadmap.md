# Roadmap

| key             | value                                                              |
|-----------------|--------------------------------------------------------------------|
| tipo            | technical document · project roadmap                               |
| tema            | development phases · current status · next steps                   |
| titulo          | theChat Roadmap                                                    |
| maturity        | living document                                                    |
| confidence      | high (completed) · medium (next) · low (later)                     |
| material origen | D001, D002, roadmap integrado tKE                                   |
| fecha           | 2026 (actualizado en Fase 0)                                       |
| mantenedor      | David                                                              |

## 1. Approach

Fases pequeñas y probables. Migraciones aditivas. Refactor solo cuando
desbloquea el siguiente paso o paga por sí mismo.

## 2. Completed

### Phase 0 — Base chat (pre-existing)

Streamlit + DeepSeek/Gemini/Mistral, SQLite, streaming, export/import.

### Phase 1 — Anthropic + modularización

Claude, toolbar extraído, get_secret centralizado, modal de confirmación.

### Phase 2 — Cleanup + projects

`delete_empty_conversations`, tabla `projects`, CRUD, safe-delete de chats
(quedan sin proyecto).

### Phase 3 — Multi-view

`st.navigation`, `views/chat.py`, `views/projects.py`, `views/ingest.py` stub.

### Phase 4 — Proyectos en la UI + system prompt

Toolbar con selector de proyecto, sidebar agrupado, herencia de proyecto en
nuevo chat, system prompt del proyecto con reemplazo completo.

### Phase 4b — Preparación RAG (schema hooks)

`indexed_at`, `pending_reindex`, índice parcial.

### Phase R1 — RAG implementado (D002)

- `rag/` completo: config, engine, store, ingestor, retriever, discovery.
- Vista Data con uploader, selector de proyecto, progreso.
- Ingesta semántica con DeepSeek (unidades, resumen, tags).
- Embeddings EmbeddingGemma (256d INT8) vía ctypes.
- HNSW + SQLite atómico, checkpoint.
- Integration en chat: toggle RAG, retrieval por proyecto, expander de fuentes.
- Pruebas: 218 chunks, 0 fallos.

### Fase 0 — Saneamiento (en curso / casi completa)

Realizado:

- ✅ Extracción de texto unificada en `utils/file_handler.py`; `rag/ingestor.py`
  ya no duplica.
- ✅ Parsing de adjuntos unificado en el chat (`display_content` + `files` en
  `views/chat.py`).
- ✅ `_migrate()` limpio (sin doble commit, migraciones separadas por método).
- ✅ `messages.parent_message_id` añadido.
- ✅ `rag_chunks` ampliado con `kind`, `status`, `source_path`,
  `source_message_id`, `parent_message_id`, `narrativa`.
- ✅ Central de extensiones `utils/extensions.py` (única fuente).
- ✅ Índice HNSW autorreparable: si falta, se reconstruye desde la BD.
- ✅ Documentación actualizada.

Pendiente / a decidir:

- Modelo por defecto de DeepSeek (`deepseek-chat` vs `deepseek-reasoner`).
- Reinterpretar `indexed_at` / `pending_reindex` para memoria de conversaciones.

## 3. Next phases (roadmap integrado tKE)

### Fase 1 — Fork y eliminación del último turno

- `forked_from_conversation_id` y `fork_at_message_id`.
- Carga por referencia (sin copiar mensajes).
- Eliminar solo el último turno no indexado.
- UI: botones en el último mensaje, ramas en sidebar.

### Fase 2 — RAG de conversaciones

- Worker síncrono que indexa mensajes como `kind='conversation'`.
- `text_link` con formato `conv:{id}:msg:{id}`.
- Regla: no indexar el último turno.
- Las ramas indexan desde su punto de fork.

### Fase 3 — RAG de herramientas v0

- Catálogo en Python con JSON schema.
- Tools: `rag_search`, `list_projects`, `get_project_info`.
- Function calling solo DeepSeek.
- Ejecución con middleware de validación.

### Fase 4 — RAG de código

- 4a: clasificador contextual (texto vs código).
- 4b: descifrado agéntico con `rag_search` y narrativa guardada en `rag_chunks`.

### Fase 5 — Modo Code completo

- Plan aprobado por el usuario, snapshot git, ejecución sin aprobación por paso.
- Git como middleware (subcomandos permitidos).
- Reindexación tras modificar código.

## 4. Deuda técnica aceptada

- Docs antiguos decían "no RAG": corregidos en Fase 0.
- Dependencia de DeepSeek para ingesta semántica (API externa).
- Carga de recursos por sesión (`GleannEngine` + HNSW): pendiente
  `@st.cache_resource`.
- `indexed_at` / `pending_reindex` aún sin reinterpretar.

## 5. Non-goals

Multi-usuario, despliegue remoto, cross-project search UI, RAG-on automático,
plugin system.