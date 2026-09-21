# SQLite as the conversation state

```mermaid
flowchart LR
    U[User] --> CHAT[Chat Interface Layer<br/>views/chat.py]

    CHAT --> MSG[New user message]
    CHAT --> HIST[Conversation history]
    CHAT --> PRJ[Project context]
    CHAT --> RAG[RAG Knowledge Layer]

    subgraph STATE[Conversation State Layer]
        DB[(SQLite<br/>chat_history.db)]
        CONV[conversations]
        MESSAGES[messages]
        PROJECTS[projects]
    end

    MSG --> DB
    HIST --> DB
    PRJ --> DB

    DB --> CONV
    DB --> MESSAGES
    DB --> PROJECTS

    DB --> CHAT
    RAG --> CONTEXT[Relevant knowledge]
    CONTEXT --> CHAT

    CHAT --> LLM[LLM Generation Layer]
    LLM --> RESP[Assistant answer]
    RESP --> DB
    RESP --> U
```

### What SQLite stores here
- conversations
- messages
- project metadata
- conversation state and history
- chat/session persistence

So conceptually:
- Chat = interface / orchestration
- RAG = knowledge retrieval
- SQLite = session/conversation memory
- LLM = generation engine
