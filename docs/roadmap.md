# Roadmap

| key             | value                                                              |
|-----------------|--------------------------------------------------------------------|
| tipo            | technical document · project roadmap                               |
| tema            | development phases · current status · next steps                   |
| titulo          | theChat Roadmap                                                    |
| maturity        | living document                                                    |
| confidence      | high (completed phases) · medium (next phase) · low (later ones)   |
| material origen | development log through August 2026                                |
| fecha           | 2026-08-31                                                         |
| mantenedor      | David                                                              |

## 1. Approach

theChat evolves in small, testable phases. Each phase changes the running
application without breaking what came before. Migrations are additive.
UI additions are opt-in. Nothing is refactored unless the refactor pays
for itself immediately or unlocks a concrete next step.

Timeline estimates are approximate. Personal-project pace, no external
deadlines.

## 2. Completed phases

### Phase 0 — Base chat (pre-existing)

Streamlit chat interface with three providers (DeepSeek, Gemini, Mistral),
SQLite-backed conversation history, streaming responses, and export/import.

### Phase 1 — Anthropic provider + modularization

- Added Anthropic (Claude) as a fourth provider with streaming.
- Extracted the top expander into a dedicated `ui/toolbar.py`.
- Extracted `get_secret` into `utils/config.py`, ending duplication across
  `002.py` and `sidebar.py`.
- Added a `@st.dialog` confirmation modal for the destructive "clear
  conversation" action.

### Phase 2 — Empty-conversation cleanup + projects data model

- Added `ChatDatabase.delete_empty_conversations(exclude_ids=...)` that
  runs on startup (before creating the new session's conversation) and
  on switch (with the incoming ID protected).
- Introduced the `projects` table with idempotent migration.
- Added CRUD methods: `create_project`, `get_projects`, `get_project`,
  `update_project`, `delete_project`, `assign_conversation_to_project`,
  `get_conversations_grouped`.
- Hard-delete for projects (chats survive as unassigned).

### Phase 3 — Multi-view navigation

- Introduced `st.navigation` in a new `app.py` entry point.
- Moved chat from `002.py` to `views/chat.py`.
- Added `views/projects.py` with full CRUD UI (create/edit/delete via
  `@st.dialog` modals, curated 8-color palette in `utils/constants.py`).
- Added `views/ingest.py` as a stub for the future RAG page.
- Moved `set_page_config` and CSS to `app.py` so they run once per session.

### Phase 4 — Project-aware UI + system prompt integration

- **Toolbar**: project selector as a new column in the top expander. Changing
  the selector calls `assign_conversation_to_project`.
- **Sidebar**: history now grouped by project via `get_conversations_grouped`.
  Empty project sections still show their header. The group containing the
  active chat auto-expands. Chats render as compact rows with modals for
  rename and delete (the old `editing_conv_id` inline flow is gone).
- **New chat inheritance**: "New Conversation" inherits the current chat's
  project.
- **System prompt substitution**: `build_context_with_reformulation_awareness`
  accepts a `project_system_prompt` argument. When set, it replaces the
  default entirely and skips the reformulation hint. The active project's
  prompt is fetched via a new `get_conversation_project` JOIN.
- **Toolbar indicator**: when a project prompt is active and no more urgent
  message is showing, the toolbar's `st.info` line displays which project
  prompt is in effect.

### Phase 4b — RAG schema preparation

- Added `conversations.indexed_at` (TIMESTAMP, NULL) and
  `conversations.pending_reindex` (INTEGER, default 0).
- Added a partial index on `(pending_reindex)` restricted to `WHERE
  pending_reindex = 1`, so the future reindex worker polls at near-zero cost.
- No code writes to these columns yet. They exist only to avoid a schema
  migration on live data when the RAG pipeline lands.

## 3. Current state (as of this document)

The chat is fully functional, four providers work, projects organize
conversations, project system prompts affect the LLM, the sidebar reflects
the project structure, and the schema is ready for RAG. The Data view is
still a stub. Nothing depends on any external service beyond the LLM APIs.

Bug fixes and small ergonomics still land as needed. There is no "release"
concept.

## 4. Next phase: RAG ingestion

### Objective

Turn `views/ingest.py` into a real ingestion page and populate a vector
index that queries in the chat can retrieve from.

### Scope

- **Ingestion UI**: multi-file uploader, destination project selector,
  quick/deep processing choice, live progress log.
- **Text extraction**: reuse `utils/file_handler.py` for the file formats
  already supported in chat attachments.
- **Chunking**: sliding window over character count, configurable per
  ingestion.
- **Embedding**: gleann + EmbeddingGemma as the target. API fallback if
  gleann is not available on the platform.
- **Storage**: chunks table with embedding BLOB, tags JSON, and content.
  HNSW index shared across projects.
- **Chunk lifecycle**: mark the parent conversation `pending_reindex = 1`
  when chunks are added, removed, or reassigned.

### Non-goals for this phase

- Retrieval from the chat. Ingestion produces data; consumption comes next.
- Deep processing with an LLM (extraction of semantic units, tag
  generation). Quick mode first, deep mode later.
- Cross-project search.

## 5. Phase after RAG ingestion: RAG retrieval

### Objective

Connect the chat flow to the vector index. Retrieved chunks enrich the
system prompt when the active conversation belongs to a project with
indexed documents.

### Scope

- **Retrieval integration** in `llm/api_clients.py`: extend the context
  builder with an optional retrieved-context argument.
- **RAG toggle** in the toolbar (per-session opt-in).
- **Query embedding + HNSW search** with adaptive over-retrieval to
  compensate for post-filtering selectivity (see architecture §4.1).
- **Source display**: an expander below each RAG-informed response listing
  the chunks used with their similarity scores.

### Non-goals

- Reranking, learning-to-rank, personalization.
- Automatic RAG-on decisions by the model. The user controls the toggle.

## 6. Phase after RAG retrieval: deep processing + optimization

### Objective

Improve retrieval quality with semantic pre-processing and cache the hot
paths.

### Scope

- **Deep mode ingestion**: pass chunks through a small local LLM to
  extract semantic units, summaries, and tags.
- **Tag-based filtering** at query time.
- **Query embedding cache** (in-memory).
- **Search result cache** keyed by (project_id, query_hash) with short TTL.
- **Reindex worker**: consume the `pending_reindex = 1` rows in the
  background, reindex their chunks, clear the flag.

## 7. Uncommitted future

Items that are on the mental list but not scheduled:

- **Agent loop for code mode**: fill in what the "code" toggle does today
  (nothing) with a filesystem/git tool-calling loop. See `agentloop.md` for
  the design plan.
- **Backup-to-zip on project delete**: currently `delete_project` warns
  about no undo. Snapshot the project (metadata + associated chats + eventual
  chunks) to a zip before hard-deleting.
- **Import projects from zip**: symmetric restore path.
- **Provider-specific effort mapping**: the `bajo/medio/alto` selector currently
  maps to `temperature` for three providers and to `reasoning_effort` for
  DeepSeek. Anthropic supports extended thinking; wiring that in would give
  the "alto" setting more meaning there.

## 8. Explicit non-goals

These will not happen unless the reason for their exclusion changes:

- Multi-user authentication.
- Remote-hosted deployment as a service.
- Cross-project search from the chat UI.
- Automatic RAG-on decisions by the model based on query classification.
- A plugin system.

## 9. Risks

- **RAG design assumptions are unverified**: the post-filtering / adaptive
  over-retrieval strategy has never been measured against a real corpus.
  If it degrades badly, the fallback is namespace partitioning inside the
  graph, which is more work.
- **gleann portability**: the primary embedder is a personal project that
  is not yet packaged. If it's not ready in time, the RAG ingestion phase
  starts against API embeddings, which is slower and less private.
- **UI creep**: adding RAG UI, source expanders, RAG toggle, deep-mode
  options, and eventually agent-loop step visibility will pressure the
  toolbar and chat view. Some of it will need to move somewhere else
  before it becomes crowded.
