# theChat

A personal chat interface with multiple LLM providers and per-project organization.

## What this is

theChat is a Streamlit app I built for my own daily use. It wraps four LLM APIs
(DeepSeek, Google Gemini, Mistral AI, and Anthropic Claude) behind a single
chat interface, and organizes conversations into projects that can carry their
own system prompt.

It is not a platform, a product, or something designed for multiple users. It
runs locally against a SQLite file. If it happens to be useful for someone
else, good — but that is not the point.

It runs locally against SQLite. No multi-user, no cloud.

## What works today

- **Chat with four providers**: streaming responses, provider switchable per turn.
- **Projects**: name, emoji, color, description, optional system prompt that
  replaces the default.
- **RAG pipeline (implemented)**:
  - Ingest documents (txt, md, pdf, docx, csv, json, code) from the Data view.
  - Semantic chunking + summaries + tags via DeepSeek.
  - Local embeddings (EmbeddingGemma 256d, INT8) via ctypes DLLs.
  - HNSW vector index + SQLite chunk store.
  - Chat retrieval: toggle RAG, search within the active project, show sources.
- **Conversation management**: create, rename, delete, export/import, cleanup.
- **File attachments in chat**: same extraction engine as RAG.
- **Persistent SQLite backend** with idempotent migrations.

## What is planned but not built

- **Fork conversations** and delete last turn (schema ready: `parent_message_id`).
- **Memory of conversations** (index chats as RAG chunks).
- **Tool calling / agent loop**: the `chat/code` toggle currently has no effect.
- **Code indexing by narrative** and full Code Mode with git approval.
- **Fast ingestion mode** (without DeepSeek) and query caching.

## Project structure

```
theChat/
├── app.py                    # entry point: st.navigation + CSS
├── database.py               # ChatDatabase: SQLite + migraciones idempotentes
├── views/
│   ├── chat.py               # chat + integración RAG
│   ├── projects.py           # CRUD proyectos
│   └── ingest.py             # Data & RAG: ingesta con progreso
├── ui/
│   ├── sidebar.py            # historial agrupado, init_database
│   ├── toolbar.py            # toolbar + toggle RAG
│   └── components.py         # CSS, copy button
├── llm/
│   └── api_clients.py        # streaming: DeepSeek, Gemini, Mistral, Anthropic
├── rag/
│   ├── config.py             # rutas y parámetros RAG
│   ├── engine.py             # GleannEngine: ctypes + SentencePiece
│   ├── store.py              # schema rag_chunks + inserción atómica
│   ├── ingestor.py           # ingesta semántica (DeepSeek + embeddings)
│   ├── retriever.py          # búsqueda HNSW + filtro por proyecto
│   └── discovery.py          # scanner de archivos
├── agent/
│   └── config.py             # constantes para Code Mode (futuro)
├── utils/
│   ├── config.py             # get_secret
│   ├── constants.py          # colores
│   ├── extensions.py         # única fuente de extensiones/exclusiones
│   ├── file_handler.py       # extracción de texto central (chat + RAG)
│   └── data_export.py        # export/import
├── rag_data/                 # rag_chunks.db, hnsw_index.bin, meta
├── models/                   # EmbeddingGemma (no commiteado)
├── runtime/                  # DLLs gleann/sp_wrap (no commiteado)
└── chat_history.db           # SQLite, creado en primer arranque
```

## Installation

Requirements: Python 3.10+, Streamlit 1.35+.

```bash
git clone <repo-url>
cd theChat

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` with the keys you plan to use:

```toml
DEEPSEEK_API_KEY   = "..."
GEMINI_API_KEY     = "..."
MISTRAL_API_KEY    = "..."
ANTHROPIC_API_KEY  = "..."
```

Any of them can be omitted. The app only fails if the provider selected in
the toolbar has no key configured.

## Usage

```bash
streamlit run app.py
```

Then in the browser:

- **Chat** (default view): pick a provider, optionally attach files, type. Use
  the project selector in the toolbar to move the current conversation into a
  project.
- **Projects**: create projects with a name, emoji, color, and (optionally) a
  custom system prompt.
- **Data**: placeholder for now.

## Database

A single SQLite file (`chat_history.db`) in the project root holds
conversations, messages, and projects. The `_migrate()` method in
`ChatDatabase` runs on every startup and is idempotent — it adds new columns
and indexes without touching existing rows. Backwards compatibility with
older schemas is preserved (legacy chats survive the migration).

## Dependencies

Actual runtime dependencies:

- `streamlit` — UI framework
- `requests` — HTTP for LLM API calls
- `pypdf`, `python-docx`, `pandas` — file extraction (only loaded when
  processing those formats)

Planned but not yet used:

- `hnswlib` / `gleann` — vector index for RAG
- Embedding libraries — for document indexing

## License

Personal project. No public license is offered at this time. If you want to
use the code, open an issue and let's talk.
.