# RAG as the knowledge layer

```mermaid
flowchart LR
    U[User] --> CHAT[Chat Interface Layer<br/>views/chat.py]

    CHAT --> INPUT[User message + project context + history]
    INPUT --> RAG[RAG Knowledge Layer<br/>rag/]
    INPUT --> LLM[LLM Generation Layer<br/>llm/api_clients.py]

    subgraph RAG
        D[Discovery<br/>rag/discovery.py]
        I[Ingestion<br/>rag/ingestor.py]
        E[Embedding / Engine<br/>rag/engine.py]
        S[Storage<br/>rag/store.py]
        RET[Retrieval<br/>rag/retriever.py]
    end

    D --> I
    I --> E
    E --> S
    S --> IDX[(Knowledge Base<br/>chunks + embeddings + index)]
    IDX --> RET
    RET --> CONTEXT[Relevant chunks / context]
    CONTEXT --> CHAT
    CHAT --> LLM
    LLM --> ANSWER[Generated answer]
    ANSWER --> U
```

### Meaning
- Chat is the interaction shell.
- RAG is the knowledge subsystem that turns files/data into searchable context.
- The LLM still does the reasoning and answer generation, but it can be grounded by retrieved knowledge.

This is the most accurate “layered” interpretation:
- Interface layer: chat
- Knowledge layer: RAG
- Generation layer: LLM
- Persistence layer: SQLite + indexed knowledge store
