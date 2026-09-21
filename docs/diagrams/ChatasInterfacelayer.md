# Chat as interface layer

```mermaid
flowchart LR
    U[User] --> CH[Chat Interface Layer<br/>views/chat.py]

    CH --> UI[UI Controls<br/>toolbar / sidebar / components]
    CH --> DB[(Conversation State<br/>SQLite)]
    CH --> LLM[LLM Service Layer<br/>api_clients.py]
    CH --> RAG[RAG Module<br/>ingestor / retriever / store / engine]
    CH --> PRJ[Project Context<br/>projects + prompts]

    RAG --> IDX[(Knowledge Store<br/>chunks + embeddings + index)]
    LLM --> RESP[Generated answer]
    RAG --> CONTEXT[Relevant context]
    CONTEXT --> CH
    PRJ --> CH

    CH --> OUT[Answer + Sources + History]
    OUT --> U
```

### Interpretation
- The Chat layer is the main interaction boundary.
- It orchestrates:
  - user input
  - project context
  - conversation history
  - optional RAG retrieval
  - LLM generation
- RAG is a backend capability used by chat, not the UI itself.
