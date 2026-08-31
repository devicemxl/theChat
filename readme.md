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

## What works today

- **Chat with four providers**: DeepSeek, Gemini, Mistral, Anthropic. Streaming
  responses. Provider is switchable per turn from the toolbar.
- **Project organization**: conversations can be grouped into projects. Each
  project has a name, emoji, color, description, and optional system prompt.
- **System prompt per project**: when set, replaces the default prompt for
  every chat in that project (and disables the reformulation hint). Useful for
  pipeline-style roles where you want the model to behave in a very specific
  way.
- **Conversation management**: create, rename, delete, export to JSON, import
  from JSON. Empty conversations get cleaned up on startup and on switch.
- **Reformulation detection**: keyword-based signal to the model that the user
  is asking for a revised answer, when no project prompt is active.
- **Confirmation modals** for destructive actions (clear conversation, delete
  project, delete chat).
- **File attachments in chat**: text, markdown, PDF, DOCX, CSV, JSON, and code
  files can be pasted as attachments; their text content is inlined into the
  user turn.
- **Persistent SQLite backend** with idempotent migrations.

## What is planned but not built

- **RAG pipeline**: document ingestion, embeddings, HNSW vector search, hybrid
  retrieval. Schema hooks (`indexed_at`, `pending_reindex` columns) already
  exist in the database as silent preparation, but no code produces or consumes
  them yet.
- **The Data view** (`views/ingest.py`): currently a stub page. Will host the
  document upload and indexing pipeline when RAG is implemented.
- **Agent loop for the Code mode**: the toolbar has a "chat / code" toggle, but
  the code mode currently changes nothing about the request. The planned
  behavior is a tool-calling loop over a filesystem with a git-backed
  approval flow.
- **Integration with the CogNeu stack**: eventually the RAG layer will use
  [gleann](https://github.com/) (my quantized vector engine) and VivaceGraph
  as the vector/graph substrate. Today the code depends on no CogNeu component.

Design documents for the planned pieces live in `docs/` and are labeled as
draft plans, not descriptions of shipped behavior.

## Project structure

```
theChat/
├── app.py                    # Entry point: st.navigation + global config
├── database.py               # ChatDatabase: SQLite persistence + migrations
├── views/
│   ├── chat.py               # Chat view (main interaction)
│   ├── projects.py           # Projects CRUD
│   └── ingest.py             # Data & RAG (stub — planned)
├── ui/
│   ├── sidebar.py            # Sidebar: grouped history, export/import, stats
│   ├── toolbar.py            # Top toolbar: provider, mode, effort, project
│   └── components.py         # Reusable pieces (CSS, copy button)
├── utils/
│   ├── config.py             # get_secret helper
│   ├── constants.py          # PROJECT_COLORS palette
│   ├── file_handler.py       # File text extraction
│   └── data_export.py        # Conversation import/export
├── llm/
│   └── api_clients.py        # Streaming clients + context builder
├── docs/                     # Design documents (current + planned)
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml          # API keys, not committed
└── chat_history.db           # SQLite file, created on first run
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