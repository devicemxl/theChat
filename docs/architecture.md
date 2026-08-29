# Architecture

| key             | value                                                                         |
|-----------------|-------------------------------------------------------------------------------|
| tipo            | technical document · system architecture                                      |
| tema            | software architecture · RAG · multi-project                                   |
| titulo          | Multi-Project RAG System Architecture                                         |
| parte           | VI — System Architecture                                                      |
| maturity        | draft for review                                                              |
| confidence      | high (concept) · medium (final implementation)                                |
| material origen | June 2026 conversation — integration of RAG pipeline with multi-provider chat |
| fecha           | 2026-06-08                                                                    |
| mantenedor      | David                                                                         |

## 1. Vision Overview

The system constitutes a retrieval augmented generation platform organized around the concept of isolated projects. Each project maintains its own vector index, relational database, and embedding configuration. The chat acts as a unified interface that queries the active project and enriches model responses with retrieved context.

The architecture separates three fundamental domains: the presentation layer built with Streamlit, the business logic layer that orchestrates ingestion and search operations, and the data layer that persists documents, vectors, and conversations.

## 2. Architectural Principles

Project isolation constitutes the central design principle. Each project operates as an independent unit with its own storage, index, and configuration. This decision allows horizontal scaling by adding projects without affecting existing ones, and facilitates work distribution among teams.

Separation of responsibilities guides code modularization. The user interface contains no business logic, business logic does not directly access the database, and external provider adapters are encapsulated behind common interfaces.

The system adopts a graceful degradation strategy. If the primary embedding engine fails, secondary alternatives are used. If semantic search does not produce sufficient results, tag-based filters are employed. This resilience guarantees service availability.

## 3. System Components

### 3.1 Presentation Layer

The Streamlit application presents three main functional areas: conversational chat, project management, and document ingestion. The chat allows the user to select the active project through a dropdown selector, visualize the sources used in each response through expandable panels, and control whether RAG search is active through a toggle switch.

Project management displays a list of existing projects with their statistics, allows creating new projects with their global tags, and facilitates deletion or archiving of obsolete projects.

Document ingestion provides a multi-file uploader, a destination project selector, quick or deep processing options, and a progress bar with real-time logs.

### 3.2 Business Logic Layer

The main orchestrator coordinates the query flow. It receives the user question, identifies the active project, invokes the search engine, builds the enriched context, and sends the request to the selected AI provider.

The project manager administers the lifecycle of each project. It creates the directory structure, initializes the database and index, updates metadata, and manages safe deletion.

The document processor implements two ingestion modes. Quick mode generates embeddings directly from text without additional processing. Deep mode uses a language model to extract semantic units, generate page summaries, and assign automatic tags.

The search engine executes hybrid queries. It generates the query embedding with the query prefix, searches nearest neighbors in the HNSW index, retrieves corresponding metadata from SQLite, applies tag filters if specified, and sorts results by similarity.

### 3.3 Data Layer

Each project's SQLite database stores documents with their embeddings as binary blobs, tags as serialized JSON, full textual content, and additional metadata. The conversations and messages table resides in a separate application-level database.

Each project's HNSW index is constructed with document embeddings. The similarity metric is cosine, the index dimension matches the embedding model dimension, and construction parameters such as ef\_construction and M are configured per project.

Index metadata files store the dimension, element count, index path, database path, and the ef value used.

## 4. Query Flow

The query flow starts when the user sends a message in the chat. The system detects the active project and verifies whether RAG search is enabled. If enabled, it generates the query embedding using the appropriate query prefix.

The search engine queries the active project's HNSW index with the generated embedding, requesting a configurable number of neighbors. The resulting identifiers are used to retrieve corresponding documents from SQLite.

The system builds the enriched context by inserting retrieved documents into the system prompt. Each document includes its similarity score and textual content. The prompt instructs the model to use only relevant information and to indicate when sufficient information is not found.

The request is sent to the selected AI provider with the enriched context. The response is streamed to the user. The system displays the sources used in expandable panels below the response.

## 5. Ingestion Flow

The ingestion flow starts when the user uploads documents to the active project. The processor detects the file type and extracts text using the appropriate adapter. Supported formats include plain text, markdown, PDF, DOCX, CSV, JSON, and code files.

In quick mode, the extracted text is sent directly to the embedding engine to generate the vector. In deep mode, the text is divided into configurable windows with overlap, each window is sent to a language model to extract semantic units, generate summaries, and assign tags.

The generated embeddings are inserted into the project's SQLite database and HNSW index. The system handles duplicate detection, index resizing when capacity is reached, and metadata updates.

## 6. Embedding Strategy

The primary embedding engine is Gleann with EmbeddingGemma, operating locally for speed and privacy. If Gleann is unavailable or fails, Mistral embedding API serves as the secondary alternative. DeepSeek embedding provides an economical fallback option.

Each embedding type uses appropriate prefixes. Documents use the document prefix, queries use the query prefix, and similarity comparisons use the similarity prefix. This asymmetric approach optimizes retrieval quality.

## 7. Configuration Management

All system parameters are centralized in a configuration module. This includes model parameters such as temperature and max tokens, RAG parameters such as top-k values and similarity thresholds, and path configurations for databases and indexes.

API keys are stored in Streamlit secrets and accessed through a secure retrieval function. No keys are hardcoded in source files.

## 8. Deployment Considerations

The system runs as a single Streamlit application. The project directory structure is created on first run. Models and DLLs are loaded lazily to minimize startup time.

For production deployment, the application can be containerized with Docker. The data directory should be mounted as a volume for persistence. Environment variables should be used for sensitive configuration.

## 9. Future Extensions

Potential extensions include multi-user support with authentication and project-level permissions, cross-project search capabilities, feedback mechanisms to improve retrieval quality, and advanced caching strategies for frequent queries.

The architecture supports incremental addition of new embedding providers and AI model providers through the adapter pattern.