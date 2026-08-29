# theChat

A multi-provider chat interface with integrated retrieval augmented generation (RAG) capabilities for project-based knowledge management.

## Overview

theChat is a Streamlit-based conversational AI platform that combines a multi-provider chat interface with a retrieval augmented generation pipeline. The system organizes knowledge into isolated projects, each with its own vector index and document database, enabling users to upload documents, search them through natural language queries, and receive responses enriched with relevant context.

The architecture supports multiple AI providers including DeepSeek, Google Gemini, and Mistral AI. The embedding pipeline uses Gleann with EmbeddingGemma as the primary engine, with fallback options to Mistral and DeepSeek embeddings for resilience.

## Features

- **Multi-Provider Chat**: Seamless switching between DeepSeek, Google Gemini, and Mistral AI for response generation.
- **Project-Based Knowledge Management**: Isolated projects with independent databases and vector indexes.
- **RAG-Enhanced Responses**: Automatic context retrieval from project documents to enrich model responses.
- **Document Ingestion**: Support for multiple file formats including text, markdown, PDF, DOCX, CSV, JSON, and source code.
- **Hybrid Search**: Combines vector similarity with tag-based filtering for precise retrieval.
- **Streaming Responses**: Real-time token-by-token response generation.
- **Conversation Management**: Full history with export, import, and reformulation support.
- **Source Attribution**: Transparent display of documents used in each response.

## Architecture

The system follows a modular architecture with clear separation of concerns. The codebase is organized into distinct layers that isolate responsibilities and facilitate maintainability, testing, and future extension.

### Presentation Layer

The Streamlit interface provides three main functional areas: conversational chat, project management, and document ingestion. The chat interface includes a project selector, RAG toggle, and source display panels. The project management area handles project CRUD operations and metadata configuration. The ingestion area provides file upload with processing options and progress tracking.

### Business Logic Layer

The orchestration layer manages conversation flow, project lifecycle, document processing, and search operations. It coordinates the interaction between the user interface, the AI providers, and the data layer.

### Data Layer

Each project maintains its own SQLite database and HNSW vector index. The database stores document embeddings as binary blobs, tags as serialized JSON, and full content. The HNSW index enables efficient nearest neighbor search for semantic retrieval.

## Project Structure

```
thechat/
├── app.py                        # Main Streamlit application entry point
├── database.py                   # Chat database management
├── config/
│   ├── __init__.py
│   ├── settings.py               # Centralized configuration
│   └── constants.py              # System constants
├── core/
│   ├── __init__.py
│   ├── embeddings.py             # Embedding engine wrapper
│   ├── vector_store.py           # HNSW index management
│   └── document_processor.py     # Document processing pipeline
├── rag/
│   ├── __init__.py
│   ├── search.py                 # Search engine
│   ├── context_builder.py        # Context construction
│   └── deepseek_processor.py     # DeepSeek integration
├── chat/
│   ├── __init__.py
│   ├── providers.py              # AI provider management
│   ├── session.py                # Session management
│   └── ui_components.py          # UI components
├── llm/
│   ├── __init__.py
│   └── api_clients.py            # AI provider API clients
├── ui/
│   ├── __init__.py
│   ├── sidebar.py                # Sidebar rendering and configuration
│   └── components.py             # Reusable UI components
├── utils/
│   ├── __init__.py
│   ├── file_handler.py           # File extraction utilities
│   ├── data_export.py            # Import/export functionality
│   └── validators.py             # Input validation
├── data/
│   └── projects/                 # Project data directory
├── .streamlit/
│   ├── config.toml               # Streamlit configuration
│   └── secrets.toml              # API keys (not committed)
├── requirements.txt
└── README.md
```

## Module Responsibilities

### app.py

The main entry point orchestrates the application. It initializes the session state, renders the sidebar, displays chat messages, processes user input, and coordinates the response generation flow. The main script imports functions from the various modules and keeps the application flow readable and maintainable.

### database.py

Manages the chat history database. This module handles conversation creation, message storage, retrieval, and deletion. It provides the data persistence layer for the chat interface.

### utils/file_handler.py

Handles all file processing operations. This module extracts text from uploaded files in various formats including PDF, DOCX, CSV, JSON, and source code files. It also parses messages that contain embedded file content.

### utils/data_export.py

Manages conversation export and import functionality. This module converts conversation history to JSON format for download and parses uploaded JSON files to restore previous conversations.

### llm/api_clients.py

Isolates all AI provider integration. This module contains the streaming clients for DeepSeek, Google Gemini, and Mistral AI. It also includes reformulation detection and context building with reformulation awareness. Adding a new AI provider only requires modifying this file.

### ui/components.py

Contains reusable visual components. This module includes custom CSS styling, copy buttons, and other UI elements that are used across the application.

### ui/sidebar.py

Manages the sidebar rendering and session state initialization. This module handles conversation history display, project selection, export/import controls, statistics, and API configuration.

### core/embeddings.py

Wraps the embedding engine. This module provides a unified interface for generating embeddings using Gleann with EmbeddingGemma, with fallback to Mistral and DeepSeek embeddings.

### core/vector_store.py

Manages the HNSW vector index. This module handles index creation, loading, saving, and querying for each project.

### rag/search.py

Implements the hybrid search engine. This module combines vector similarity search with tag-based filtering to retrieve relevant documents.

### rag/context_builder.py

Constructs enriched prompts for the language model. This module formats retrieved documents with similarity scores and content snippets for inclusion in the system prompt.

## Installation

### Prerequisites

- Python 3.10 or higher
- Streamlit
- SQLite3
- HNSWLib
- NumPy

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/thechat.git
cd thechat

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
# Edit .streamlit/secrets.toml with your API keys
```

### Configuration

Create a `.streamlit/secrets.toml` file with the following structure:

```toml
DEEPSEEK_API_KEY = "your-deepseek-api-key"
GEMINI_API_KEY = "your-gemini-api-key"
MISTRAL_API_KEY = "your-mistral-api-key"
```

Configure the embedding engine paths in the configuration module:

```python
# config/settings.py
GLEANN_ENGINE_LIB = "./gleann_engine.dll"  # or .so on Linux
SP_LIB = "./sp_wrap.dll"                    # or .so on Linux
SP_MODEL = "/path/to/tokenizer.model"
MODEL_DIR = "/path/to/model"
PACK_JSON = "/path/to/pack.json"
```

## Usage

### Starting the Application

```bash
streamlit run app.py
```

### Chat Interface

1. Select the active project from the dropdown in the header.
2. Toggle RAG search on or off as needed.
3. Type your question in the chat input.
4. View sources used in the response by expanding the "Sources" panel.

### Project Management

1. Navigate to the "Projects" tab.
2. Click "New Project" to create a new project.
3. Configure project name, description, and global tags.
4. Select a project to load its index and database.

### Document Ingestion

1. Navigate to the "Ingestion" tab.
2. Select the destination project.
3. Upload files using the multi-file uploader.
4. Choose processing mode (Quick or Deep).
5. Monitor progress and logs in real-time.

## Dependencies

- `streamlit`: Web application framework
- `hnswlib`: Approximate nearest neighbor search
- `numpy`: Numerical computing
- `sqlite3`: Database management
- `requests`: HTTP client for API calls
- `pypdf`: PDF text extraction
- `python-docx`: DOCX text extraction
- `pandas`: CSV processing

## Roadmap

The development roadmap is organized into five phases:

1. **Phase 1: Foundation** - Modular architecture and centralized configuration
2. **Phase 2: Project Management** - Project CRUD operations and isolation
3. **Phase 3: Ingestion Pipeline** - Document processing and indexing
4. **Phase 4: RAG Integration** - Search engine and context enrichment
5. **Phase 5: Deep Processing** - Semantic analysis and optimization

See the full roadmap in `docs/roadmap.md`.

## License

theChat is dual-licensed software, following the xTuple licensing model.

### Open Source License (CPAL-1.0)

For individuals and organizations that wish to use theChat without commercial restrictions, the software is available under the **Common Public Attribution License Version 1.0 (CPAL-1.0)**. This license permits free use, modification, and distribution for non-commercial purposes, provided that:

- Attribution is given to the original authors.
- Modifications are shared under the same license.
- The software is not sold or used in commercial products without separate commercial licensing.

### Commercial License

For organizations that wish to use theChat in commercial products, embed it in proprietary applications, or provide it as part of a paid service, a **Commercial License** is required. The commercial license provides:

- Unlimited commercial use and distribution.
- The right to modify, customize, and integrate the software.
- No obligation to share modifications or source code.
- Priority support and maintenance.
- Custom development and consulting services.

### Licensing Options

| Feature | CPAL-1.0 (Open Source) | Commercial License |
|--|--|--|
| Non-commercial use | Allowed | Allowed |
| Commercial use | Not allowed | Allowed |
| Modify and distribute | Allowed with attribution | Allowed without attribution |
| Share modifications | Required | Not required |
| Embed in proprietary products | Not allowed | Allowed |
| Priority support | Not included | Included |
| Custom development | Not included | Available |

### How to Obtain a Commercial License

For commercial licensing inquiries, please contact:

- Email: licensing@thechat.dev
- Website: https://thechat.dev/licensing

### Third-Party Components

theChat includes third-party components that may be subject to their own licensing terms:

- Streamlit: Apache License 2.0
- HNSWLib: Apache License 2.0
- NumPy: BSD License
- pypdf: BSD License
- python-docx: MIT License
- pandas: BSD License

## Contributing

Contributions are welcome. Please follow these guidelines:

1. Fork the repository.
2. Create a feature branch.
3. Implement your changes.
4. Add tests for new functionality.
5. Submit a pull request with a clear description.

For contributions to be accepted, contributors must agree to the **Contributor License Agreement (CLA)**. This agreement ensures that contributions can be dual-licensed and that the project maintains the ability to offer both open source and commercial licensing options.

## Contact

- **Project Maintainer**: David
- **Email**: david@thechat.dev
- **Website**: https://thechat.dev
- **Issues**: https://github.com/yourusername/thechat/issues

For questions, support, or licensing inquiries, please open an issue on the GitHub repository or contact the maintainer directly.