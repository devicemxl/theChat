# Índice de la documentación de arquitectura

Estructura propuesta: **capas** (estructura estática) + **procesos** (flujos dinámicos). Cada punto = un diagrama + su explicación. Marco también el tipo de diagrama y qué decisiones de lectura conviene fijar antes de dibujar.

---

## 0. Convenciones

**0.1** — Leyenda única para los 20 diagramas: qué significa cada tipo de flecha (import, llamada síncrona, escritura a disco, HTTP saliente), y qué NO se dibuja (widgets de Streamlit, llamadas internas de librerías). Sin esto los diagramas se contradicen entre sí en el trazo.

---

## A. Capas (estructura)

**A1. Capas globales** — `flowchart TD`. Entry → Views/UI → State → Dominio → Infra externa. Es el diagrama de portada; el resto son zooms.

**A2. Grafo de imports real** — `graph LR`. Quién importa a quién, módulo por módulo. Sirve para ver las violaciones de capa (ej.: `views` importando `rag` directo, `rag` importando `utils`, `database.py` importando `streamlit` sin usarlo).

**A3. Capa de estado** — `flowchart LR` + tabla de claves de `st.session_state`. Este es el punto que los documentos actuales no modelan y que explica la mitad del comportamiento de la app: qué claves existen, quién las inicializa, quién las escribe, quién las lee. `init_database()` es el bootstrap real del sistema.

**A4. Capa de persistencia física** — `flowchart LR`. Los **dos** SQLite (`chat_history.db`, `rag_chunks.db`), los dos archivos de índice (`hnsw_index.bin` + `hnsw_index_meta.json`), los assets del modelo y las DLLs. Énfasis en que son **ciclos de vida independientes**: migraciones distintas, dueños distintos, sin transacción cruzada.

**A5. Modelo ER de `chat_history.db`** — `erDiagram`. `conversations`, `messages`, `projects`. Incluye el self-loop de fork (`forked_from_conversation_id`, `fork_at_message_id`) y `messages.parent_message_id`, que **no están en ningún doc actual**. Marcar qué columnas están vivas y cuáles son reservadas.

**A6. Modelo de datos de `rag_chunks.db`** — `erDiagram`. Las 6 columnas tKE (`kind`, `status`, `source_*`, `parent_message_id`, `narrativa`) con su estado real: **escritas solo con defaults**, nunca pobladas por el ingestor.

**A7. Subsistema RAG interno** — `flowchart LR`. `config` → `engine` → `store` / `ingestor` / `retriever` / `discovery`. Este es el zoom que necesita el módulo para dejar de ser una caja negra; incluye que `discovery` **no participa del flujo de la app** (solo CLI).

**A8. Capa de generación LLM** — `flowchart LR`. Los 4 proveedores, sus diferencias de formato (system en campo aparte en Anthropic, `system_instruction` en Gemini, `role:model` en Gemini) y la normalización de streaming. Acá va el hallazgo importante: hay **dos clientes HTTP distintos a DeepSeek** (`llm/api_clients.py` para streaming del chat, `rag/ingestor.py::call_deepseek` para el troceo semántico, con retries y `json_object`).

**A9. Frontera de runtime nativo** — `flowchart LR`. `rag/engine.py` → `gleann_engine.dll` + `sp_wrap.dll` + EmbeddingGemma. Es la única capa que sale de Python puro y la que condiciona portabilidad (AVX2, Windows, `winmode=0`).

---

## B. Procesos (flujos)

### Chat

**B1. Arranque de la app** — `sequenceDiagram`. `app.py` → `set_page_config` → CSS → `st.navigation` → script de vista. Corto, pero fija dónde vive cada cosa.

**B2. Boot de la vista Chat** — `sequenceDiagram`. `init_database()` en detalle: crea DB, borra conversaciones vacías, crea la conversación, carga mensajes, lee secretos, **instancia `RAGRetriever` eager**. Después `render_sidebar()` → proyecto activo → loop de mensajes → `render_toolbar()`. Acá se ve que el orden de render **no coincide** con el orden lógico (toolbar abajo, no arriba).

**B3. Turno de chat sin RAG** — `sequenceDiagram`. `chat_input` → guardar parcial truncado previo → guardar usuario → render → construir contexto → streaming → guardar asistente → `uploader_key++` → `rerun`.

**B4. Turno de chat con RAG** — `sequenceDiagram`. El mismo flujo con el bloque condicional: `rag_enabled` ∧ `rag_available` ∧ proyecto → `search()` → inyección como texto en el system prompt. Marcar que **la inyección es textual, no estructurada**, y que el filtro por proyecto es post-HNSW.

**B5. Composición del system prompt** — `flowchart TD`. La bifurcación triple: `project_system_prompt` presente (reemplaza todo, anula reformulación) / default + hint de reformulación / + bloque RAG. Es la decisión de mayor impacto y hoy no está dibujada en ningún lado.

**B6. Adjuntos: ida y vuelta** — `sequenceDiagram`. Extracción con `extract_text_from_bytes` → serialización al `content` del mensaje con marcadores `--- Contenido de '...' ---` → persistencia → re-parseo en `load_conversation_messages`. Es un round-trip por string dentro de la columna de texto; conviene dibujarlo porque explica por qué el export/import pierde datos.

**B7. Interrupción y truncamiento** — `sequenceDiagram`. Qué pasa si el usuario recarga a mitad de stream: `partial_response` sobrevive en sesión, se persiste como `truncated=True` en el envío siguiente, y suma a `tokens_wasted`.

### Conversación

**B8. Fork** — `sequenceDiagram`. Botón 🌿 → `create_fork` → `switch_conversation` → `get_messages_for_context` reconstruye madre (hasta `fork_at_message_id`) + hija. Dejar claro que es **fork por referencia**, sin copia de mensajes.

**B9. Eliminar último turno** — `sequenceDiagram`. Validación (los dos últimos deben ser user+assistant) → borrado → ajuste de `message_count`.

**B10. Ciclo de vida de conversación** — `stateDiagram`. Crear (con herencia de proyecto) → cambiar → vaciar → soft delete → hard delete de vacías. Incluye la limpieza silenciosa al arranque y al switch, que es comportamiento no documentado.

**B11. CRUD de proyectos** — `sequenceDiagram`. Crear/editar/borrar con `IntegrityError` y la regla de no-cascade: los chats quedan huérfanos, nunca se borran.

### RAG — ingesta

**B12. Pipeline de ingesta completo** — `sequenceDiagram` largo. `check_rag_prerequisites` → init motor → abrir DB + schema → cargar índice → `verify_consistency` → por archivo: extraer / normalizar / dedup por hash / ventanas → por ventana: DeepSeek (unidades + resumen + tags) → embed + insert atómico por unidad y por página → resumen global → checkpoint. Es el proceso más complejo del sistema y el que más justifica un diagrama propio.

**B13. Inicialización del motor nativo** — `sequenceDiagram`. Orden real de `GleannEngine.__init__`: cargar DLL, tokenizer, resolver modelo, materializar `nxdeck.json`, `nxpy_create`, leer dims, validar `target_dim` contra `hidden_dim` y contra `BLOCK_SIZE`. Orden de fallo importa: cada paso cierra lo anterior.

**B14. HNSW: carga, recuperación, checkpoint** — `flowchart TD`. Las tres ramas de `_load_or_create_index` (cargar / reconstruir desde BD / crear vacío) y cuándo se escribe el checkpoint. Notable: `rebuild_index_from_db` tiene un loop que deserializa todo y lo descarta.

**B15. Inserción atómica** — `sequenceDiagram`. `BEGIN` SQLite → `INSERT` → `resize_if_needed` → `add_items` HNSW → `COMMIT`, con los tres modos de fallo y el `mark_deleted` compensatorio.

### RAG — consulta

**B16. Retrieval** — `sequenceDiagram`. `embed_query` (con prefijo asimétrico) → kNN con `k=min(50, element_count)` → filtro `project_id` en SQL → score `1-dist` → `top_n`. Anotar que el `k` es global, así que en proyectos chicos puede devolver menos de `top_n`.

### Cierre

**B17. Export / import** — `sequenceDiagram`. Qué se serializa y qué se pierde (proyecto, fork, adjuntos). Un diagrama con las pérdidas marcadas en rojo vale más que el código.

**B18. Modo agente (path muerto)** — `flowchart LR`. Radio del toolbar → `session_state.agent_mode` → mensaje de estado. **Y nada más.** Dibujarlo explícitamente como rama muerta evita que un lector futuro asuma que el loop existe.

---

## C. Cierre del documento

**C1. Deuda arquitectónica** — tabla, no diagrama. Acoplamientos, instanciación eager, FK no enforced, round-trip por string, errores no persistidos.

**C2. Contradicciones doc ↔ código** — la tabla que ya armé, cerrada contra el código real.

**C3. Non-goals reales** — no los que declara `architecture.md`, sino los que el código sostiene. Sin auth, single-process, un solo índice compartido entre proyectos, RAG manual.

---

## Orden sugerido de lectura

1. **A1, A2, A3** — dan el esqueleto y resuelven de una vez por qué la app se comporta como se comporta.
2. **B2, B3, B5** — el turno de chat es el corazón; sin esto el resto no se entiende.
3. **A4, A5, A6** — persistencia, ya con el flujo en la cabeza.
4. **A7, B12, B16** — RAG, el bloque más grande.
5. **El resto** — relleno y casos borde.
