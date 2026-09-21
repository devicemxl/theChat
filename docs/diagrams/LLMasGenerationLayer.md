# LLM API as the generation layer

```mermaid
flowchart LR
    U[User] --> CHAT[Chat Interface Layer<br/>views/chat.py]

    CHAT --> INPUT[User message<br/>project context<br/>conversation state]
    INPUT --> RAG[RAG Knowledge Layer]
    INPUT --> LLM[LLM Generation Layer<br/>llm/api_clients.py]

    RAG --> CTX[Relevant retrieved context]
    CTX --> LLM

    LLM --> API[LLM Providers<br/>DeepSeek / Gemini / Mistral / Anthropic]
    API --> RESPONSE[Generated answer]

    RESPONSE --> CHAT
    CHAT --> DB[(SQLite<br/>conversation state)]
    DB --> CHAT
    CHAT --> U
```

### Interpretation
- The chat layer orchestrates the request.
- The RAG layer provides grounding/context.
- The LLM API generates the actual response.
- SQLite stores the evolving conversation and project state.
