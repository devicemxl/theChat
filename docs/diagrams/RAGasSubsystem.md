# RAG as a separate subsystem
RAG should be treated as a separate subsystem/module in the app, not just a checkbox in the chat UI. In this project, it has its own flow:

- ingestion
- storage
- embedding generation
- retrieval
- context injection into chat

A cleaner diagram is:

```mermaid
flowchart LR
    U[User] --> A[app.py<br/>Streamlit entry]
    A --> NAV[Navigation]
    NAV --> C[views/chat.py]
    NAV --> P[views/projects.py]
    NAV --> I[views/ingest.py]

    C --> UI[ui/]
    P --> UI
    I --> UI

    C --> DB[(SQLite<br/>chat_history.db)]
    P --> DB
    I --> DB

    subgraph RAG["RAG Module"]
        D[rag/discovery.py]
        ING[rag/ingestor.py]
        ENG[rag/engine.py]
        STO[rag/store.py]
        RET[rag/retriever.py]
    end

    I --> D
    I --> ING
    ING --> ENG
    ENG --> STO
    STO --> IDX[(Vector index + chunk DB)]
    C --> RET
    RET --> CTX[Retrieved context]
    CTX --> C

    C --> LLM[llm/api_clients.py]
    LLM --> RESP[Model answer]
    RESP --> U
```

### In short
- Chat is the interface layer.
- RAG is the knowledge layer.
- SQLite is the conversation state.
- LLM API is the generation layer.

The diagram is much clearer when RAG is drawn as its own module, with its own input/output pipeline.