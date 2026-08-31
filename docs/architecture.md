# Architecture

| key             | value                                                              |
|-----------------|--------------------------------------------------------------------|
| tipo            | technical document · system architecture                           |
| tema            | software architecture · personal chat interface                    |
| titulo          | theChat Architecture                                               |
| maturity        | current implementation + planned RAG extension                     |
| confidence      | high (current) · medium (planned)                                  |
| material origen | development log through August 2026                                |
| fecha           | 2026-08-31                                                         |
| mantenedor      | David                                                              |

## 1. Scope

This document describes the current architecture of theChat as of August 2026
and the planned RAG extension. The RAG section is a design plan — no RAG code
exists yet in the repository. Schema-level hooks are already in place, but no
ingestion, embedding, or retrieval logic is implemented.

Everything under "Current architecture" reflects code that ships and runs.
Everything under "Planned RAG extension" is intent, subject to revision when
it becomes real.

## 2. Design principles

**Simplicity over abstraction.** The application is a single Streamlit process
against a local SQLite file. There is no service layer, no daemon, no queue.
When RAG lands, the vector index lives beside the SQLite file as another local
artifact.

**Separation of concerns without over-engineering.** The code splits into
`views/` (Streamlit pages), `ui/` (reusable sidebar/toolbar/components),
`utils/` (config, constants, file I/O, import/export), `llm/` (API adapters),
and a single `database.py` for persistence. No dependency injection framework,
no repository pattern — just modules with clear names.

**Idempotent migrations.** The database evolves through additive migrations
that run on every startup. Adding a column or an index never depends on
knowing the previous state. Data is never destroyed by a migration.

**Personal scope.** No authentication, no multi-tenant model, no remote
storage, no permissions. The user is one person on one machine.

## 3. Current architecture

### 3.1 Component layout

```
Streamlit process
├── app.py                    entry point, st.navigation
│
├── views/                    top-level pages
│   ├── chat.py               conversation flow
│   ├── projects.py           project CRUD
│   └── ingest.py             stub (RAG placeholder)
│
├── ui/                       cross-view components
│   ├── sidebar.py            history grouped by project
│   ├── toolbar.py            provider/mode/effort/project selector
│   └── components.py         CSS + copy button
│
├── llm/api_clients.py        streaming clients: DeepSeek, Gemini,
│                             Mistral, Anthropic + context builder
│
├── utils/                    config, constants, file I/O, import/export
│
└── database.py               ChatDatabase over SQLite
        │
        └── chat_history.db   local file
```

### 3.2 Data model

Three tables in `chat_history.db`:

**conversations**

| column           | type      | notes                                          |
|------------------|-----------|------------------------------------------------|
| id               | INTEGER   | primary key                                    |
| title            | TEXT      | user-editable                                  |
| created_at       | TIMESTAMP |                                                |
| updated_at       | TIMESTAMP | updated on each message                        |
| message_count    | INTEGER   |                                                |
| is_active        | INTEGER   | soft-delete flag                               |
| project_id       | INTEGER   | nullable — NULL means "no project"             |
| indexed_at       | TIMESTAMP | reserved for RAG (currently NULL)              |
| pending_reindex  | INTEGER   | reserved for RAG (currently 0)                 |

**messages**

| column                | type      | notes                                     |
|-----------------------|-----------|-------------------------------------------|
| id                    | INTEGER   | primary key                               |
| conversation_id       | INTEGER   | foreign key (not enforced)                |
| role                  | TEXT      | user / assistant / system                 |
| content               | TEXT      |                                           |
| truncated             | INTEGER   | 1 if streaming was interrupted            |
| interrupted_at        | TEXT      | timestamp of interruption                 |
| reformulation_count   | INTEGER   |                                           |
| created_at            | TIMESTAMP |                                           |

**projects**

| column         | type      | notes                                         |
|----------------|-----------|-----------------------------------------------|
| id             | INTEGER   | primary key                                   |
| name           | TEXT      | UNIQUE                                        |
| description    | TEXT      | nullable                                      |
| system_prompt  | TEXT      | nullable — if set, replaces default in chat   |
| icon           | TEXT      | emoji, default "📁"                            |
| color          | TEXT      | hex, from a curated palette of 8              |
| created_at     | TIMESTAMP |                                               |

Projects are hard-deleted (no `is_active` flag) because they carry no message
history themselves. When a project is deleted, its conversations are
reassigned to `project_id = NULL` — never cascaded away.

Indexes: `idx_conversations_project` on `(project_id)`, plus a partial index
`idx_conversations_pending_reindex` on `(pending_reindex)` restricted to rows
where `pending_reindex = 1`. The partial index costs almost nothing until
RAG starts using it.

### 3.3 Query flow (chat)

1. User types in the chat input and optionally attaches files.
2. `views/chat.py` extracts file text via `utils/file_handler.py` and appends
   it to the user turn.
3. The turn is persisted to `messages` via `ChatDatabase.save_message`.
4. `llm/api_clients.py::build_context_with_reformulation_awareness` composes
   the request:
   - If the active conversation belongs to a project with a `system_prompt`,
     that prompt replaces the default and the reformulation hint is skipped.
   - Otherwise, the default prompt is used, extended with a reformulation
     hint when detected.
5. The correct provider's streaming function is called with the composed
   messages. The response is streamed token by token to the UI and, on
   completion, persisted.

### 3.4 Multi-provider adapter

Each provider has a `stream_<provider>_completion` function in
`llm/api_clients.py`. All follow the same shape: take `(messages, api_key,
**provider_kwargs)`, return a generator of text chunks.

Provider-specific quirks are handled inside the function:

- **DeepSeek / Mistral**: OpenAI-compatible schema, SSE streaming.
- **Gemini**: system message extracted from the array into a `system_instruction` field; roles remapped (`assistant` → `model`).
- **Anthropic**: `system` extracted to a top-level field; SSE stream carries
  `content_block_delta` events with `text_delta` payloads.

Provider selection is stored in `session_state.api_provider` and mapped to
its key. Adding a fifth provider is one function plus one branch in
`toolbar.configure_api_key`.

### 3.5 Navigation

Streamlit's `st.navigation` (available from 1.36) drives page selection.
`app.py` declares three `st.Page` entries and delegates rendering via
`pg.run()`. Each view is a standalone script that runs top-to-bottom when
selected.

`set_page_config` and CSS injection live in `app.py` so they run once per
session, not once per page.

### 3.6 State management

All shared state lives in `st.session_state`. The critical keys:

- `db` — the `ChatDatabase` instance (initialized once)
- `current_conversation_id` — the active chat
- `messages` — in-memory copy of the current chat's messages
- `api_provider`, `api_key`, `api_brainer` — provider selection and effort
- `agent_mode` — "chat" or "code" (code mode currently does nothing extra)

`session_state` survives view switches. This is what makes the multi-view
navigation coherent: you can browse to Projects, come back, and pick up
where you left off.

### 3.7 Cleanup logic

Empty conversations (zero messages) are hard-deleted on two occasions:

- **On startup** in `ChatDatabase.__init__`, before creating the new
  conversation for this session. The order matters — sweeping before creation
  means the new one is never exposed to the delete.
- **On switch** in `sidebar.switch_conversation`, with the incoming
  conversation ID excluded from the sweep. This protects a conversation the
  user is deliberately loading even if it happens to be empty.

Both use `ChatDatabase.delete_empty_conversations(exclude_ids=...)`.

## 4. Planned RAG extension

Everything below is a design plan. None of it is implemented as of this
document's date.

### 4.1 Retrieval strategy

The core idea: a single HNSW index shared across projects, with `project_id`
as a filter column in the metadata database. Because HNSW returns IDs (not
data), filtering by project happens in SQLite after the graph traversal, at
zero index-lookup cost.

Trade-off: naive post-filtering degrades recall when a filter is very
selective. Mitigations under consideration:

1. **Over-retrieval with adaptive expansion**: request K far larger than
   needed and stop when the filtered set is large enough.
2. **Namespace partitioning inside the graph**: chunks from different projects
   are never neighbors, so search inside a project skips the rest of the graph
   naturally.
3. **Filtered HNSW**: filter evaluation during graph traversal (as in Qdrant
   and Weaviate). Best recall/latency but complex to implement well.

Option 1 is the plan for the first iteration. Option 2 or 3 is a later
optimization if it becomes necessary.

### 4.2 Move-a-chat semantics

Moving a conversation between projects is currently a single-column UPDATE.
When RAG exists, the same operation must also update the vector index
association. Two possible UX flows:

- **Blocking with confirmation**: modal warns "N chunks will be re-associated
  (~T seconds)". OK triggers a synchronous operation with a spinner.
- **Instant + background reindex**: the UPDATE is immediate; a
  `pending_reindex = 1` flag is set; a worker processes it later. The chat is
  temporarily inconsistent for RAG queries.

The database schema is already prepared for the second flow: `indexed_at`
and `pending_reindex` columns exist, and the partial index on
`pending_reindex = 1` makes worker polling trivially cheap.

### 4.3 Embedding provider chain

Primary target: [gleann](https://github.com) (my quantized vector engine)
with EmbeddingGemma at 512 dims (MRL truncation, block-wise int8). Local,
private, fast.

Fallbacks under consideration if gleann is unavailable on a given platform:
Mistral embed API, DeepSeek embed API. This chain is a plan, not a
resilience feature — the primary is expected to work.

### 4.4 Ingestion

The `views/ingest.py` page will host the ingestion UI: multi-file uploader,
destination project selector, quick/deep processing choice, progress log.

- **Quick**: extract text → chunk with sliding window → embed → insert.
- **Deep**: same, but each chunk is first passed through a small LLM
  (candidates: Qwen3-0.6B, OpenELM-270M via nxDeck) to extract semantic
  units, generate a summary, and assign tags. The tags feed hybrid search.

### 4.5 What does not extend

Multi-user support, authentication, permissions, remote deployment,
container orchestration, cross-project search UI. These are explicitly out
of scope.
