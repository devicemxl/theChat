# layered system

```mermaid
flowchart LR
    U[User] --> CHAT[Interface Layer<br/>Chat UI<br/>views/chat.py]

    subgraph STATE["Conversation State Layer"]
        DB[(SQLite<br/>chat_history.db)]
        CONV[conversations]
        MSG[messages]
        PRJ[projects]
    end

    subgraph KNOWLEDGE["Knowledge Layer"]
        RAG[RAG Module<br/>rag/]
        IDX[(Knowledge Base<br/>chunks + embeddings + index)]
    end

    subgraph GENERATION["Generation Layer"]
        LLM[LLM API Layer<br/>DeepSeek / Gemini / Mistral / Anthropic]
    end

    CHAT --> INPUT[User message<br/>project context<br/>conversation history]
    INPUT --> DB
    DB --> CONV
    DB --> MSG
    DB --> PRJ

    CHAT --> RAG
    RAG --> IDX
    IDX --> RETRIEVAL[Relevant context]
    RETRIEVAL --> LLM

    INPUT --> LLM
    DB --> CHAT
    LLM --> ANSWER[Generated answer]
    ANSWER --> CHAT
    CHAT --> OUTPUT[Response + sources + state update]
    OUTPUT --> U
```

### Interpretation
- Chat is the interface layer: it coordinates the interaction.
- SQLite is the conversation state: it stores messages, chats, and project metadata.
- RAG is the knowledge layer: it retrieves relevant information from indexed content.
- LLM API is the generation layer: it turns the combined prompt and retrieved context into the answer.
