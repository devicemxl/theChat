# Roadmap

## Metadata

| key | value |
|--|--|
| tipo | technical document · project roadmap |
| tema | software development · RAG · multi-project |
| titulo | Multi-Project RAG System Development Roadmap |
| parte | VI — System Architecture |
| maturity | draft for review |
| confidence | high (concept) · medium (final implementation) |
| material origen | June 2026 conversation — development phases for multi-project RAG integration |
| fecha | 2026-06-08 |
| mantenedor | David |

## 1. Roadmap Overview

The development roadmap defines five sequential phases for implementing the multi-project RAG system. Each phase builds upon the previous one, delivering incremental value and enabling continuous testing and feedback. The roadmap prioritizes foundational work first, followed by feature integration, and concludes with optimization and production readiness.

The estimated timeline spans approximately eight to ten weeks of focused development. Each phase includes specific milestones that serve as checkpoints for progress evaluation.

## 2. Phase 1: Foundation and Refactoring

### Duration: Week 1-2

### Objective

The foundation phase establishes the modular architecture and centralized configuration that subsequent phases depend upon. This phase addresses the technical debt in the existing chat application and creates the structural framework for multi-project support.

### Key Activities

The refactoring effort separates the monolithic chat application into distinct modules. The presentation layer handles Streamlit components and user interactions. The business logic layer orchestrates conversation flow and provider management. The data layer manages persistence and retrieval operations.

The configuration system centralizes all parameters including model settings, RAG parameters, and path configurations. API keys move to environment variables or Streamlit secrets. The configuration module provides typed access to all settings.

The project management foundation creates the directory structure for storing project data. This includes the base data directory, project subdirectories, and initialization logic for new projects.

### Milestones

| Milestone | Description | Acceptance Criteria |
|--|--|--|
| M1.1 | Modular chat architecture | Chat functionality works with separated presentation, logic, and data layers |
| M1.2 | Centralized configuration | All parameters accessible through configuration module; no hardcoded values in source |
| M1.3 | Project directory structure | System creates project directories with database and index files on project creation |
| M1.4 | API key security | All API keys stored in environment variables or Streamlit secrets; no keys in source code |
| M1.5 | Existing functionality preserved | All existing chat features (multi-provider, reformulation, export/import) work without regression |

## 3. Phase 2: Project Management System

### Duration: Week 3-4

### Objective

The project management phase implements the core multi-project architecture. This phase enables users to create, configure, and manage isolated projects with their own data stores.

### Key Activities

The project lifecycle management implements creation, activation, configuration, and deletion of projects. Each project receives a unique identifier, directory structure, and metadata file.

The project metadata schema defines the structure for storing project information including name, description, creation date, global tags, and statistics. The metadata file persists across sessions.

The project selector integrates into the chat interface, allowing users to switch between active projects. Switching projects loads the appropriate index and database connections.

The project statistics tracking monitors document counts, storage usage, and search activity for each project.

### Milestones

| Milestone | Description | Acceptance Criteria |
|--|--|--|
| M2.1 | Project CRUD operations | Users can create, read, update, and delete projects through the interface |
| M2.2 | Project metadata persistence | Project metadata survives application restarts and is correctly loaded |
| M2.3 | Project selector in chat | Users can switch active projects from the chat interface; switching loads correct data |
| M2.4 | Project statistics display | Statistics section shows accurate metrics for each project |
| M2.5 | Project isolation verification | Documents from one project are not accessible from another project |

## 4. Phase 3: Ingestion Pipeline

### Duration: Week 5-6

### Objective

The ingestion pipeline phase implements document processing and indexing for each project. This phase delivers the capability to upload files, generate embeddings, and populate the vector index.

### Key Activities

The file upload interface provides a multi-file uploader with project destination selection. The interface displays processing progress and logs in real-time.

The text extraction module handles various file formats including text, markdown, PDF, DOCX, CSV, JSON, and code files. Each format uses a dedicated extraction adapter.

The embedding generation integrates the Gleann engine as the primary embedding provider. The system implements fallback to Mistral and DeepSeek embeddings when Gleann is unavailable.

The database insertion and index update logic stores documents in SQLite and updates the HNSW index. The system handles index resizing when capacity is reached.

The duplicate detection identifies and removes redundant documents based on text links.

### Milestones

| Milestone | Description | Acceptance Criteria |
|--|--|--|
| M3.1 | File upload interface | Users can upload multiple files and select destination project |
| M3.2 | Text extraction for all formats | All supported file formats extract text correctly |
| M3.3 | Embedding generation with Gleann | Gleann generates embeddings for uploaded documents |
| M3.4 | Embedding fallback chain | System falls back to Mistral and DeepSeek when Gleann fails |
| M3.5 | Database and index population | Documents are correctly stored in SQLite and indexed in HNSW |
| M3.6 | Duplicate detection | Duplicate documents are identified and removed |

## 5. Phase 4: RAG Integration in Chat

### Duration: Week 7-8

### Objective

The RAG integration phase connects the search engine to the chat interface. This phase enables the model to retrieve relevant context and generate enriched responses.

### Key Activities

The search engine implementation provides hybrid search combining vector similarity with tag filtering. The search engine retrieves candidate documents from the active project's HNSW index and SQLite database.

The context construction module builds enriched prompts by inserting retrieved documents into the system prompt. The context includes document titles, similarity scores, and content snippets.

The model decision flow determines when RAG context is necessary and how to utilize retrieved documents. The model assesses relevance, extracts information, and constructs responses with source citations.

The source display in the chat interface shows which documents were used in each response. Users can expand sources to view full document content.

The RAG toggle in the chat interface allows users to enable or disable context retrieval for the current session.

### Milestones

| Milestone | Description | Acceptance Criteria |
|--|--|--|
| M4.1 | Hybrid search engine | Search engine retrieves relevant documents using vector similarity and optional tag filters |
| M4.2 | Context construction | System builds enriched prompts with retrieved documents and similarity scores |
| M4.3 | Model decision flow | Model correctly assesses document relevance and constructs responses with citations |
| M4.4 | Source display in chat | Users can view and expand sources used in each response |
| M4.5 | RAG toggle functionality | Users can enable or disable RAG retrieval per session |
| M4.6 | Response quality evaluation | Responses with RAG context are more accurate and informative than without |

## 6. Phase 5: Deep Processing and Optimization

### Duration: Week 9-10

### Objective

The deep processing and optimization phase enhances the ingestion pipeline with semantic analysis and optimizes system performance. This phase delivers advanced features for improved retrieval quality.

### Key Activities

The deep processing mode integrates a language model for semantic analysis. The model extracts semantic units from text chunks, generates page summaries, and assigns descriptive tags.

The sliding window implementation divides documents into overlapping chunks with configurable size and overlap parameters. The system processes each chunk independently.

The tag management system combines folder-based tags with model-generated tags. The system normalizes tags to ensure consistency and removes duplicates.

The caching system implements caching for query embeddings, search results, and response generation. This reduces latency for repeated queries.

The parallel processing capability processes multiple documents concurrently when resources allow. This reduces ingestion time for large document sets.

The performance monitoring tracks pipeline metrics including embedding time, search time, and response generation time.

### Milestones

| Milestone | Description | Acceptance Criteria |
|--|--|--|
| M5.1 | Deep processing mode | System extracts semantic units, generates summaries, and assigns tags using language model |
| M5.2 | Sliding window segmentation | Documents are divided into overlapping chunks with configurable parameters |
| M5.3 | Tag combination and normalization | Tags from folders and model are combined and normalized without duplicates |
| M5.4 | Caching implementation | Query embeddings and search results are cached; repeated queries have reduced latency |
| M5.5 | Parallel processing | Multiple documents process concurrently; ingestion time improves for large sets |
| M5.6 | Performance monitoring | System tracks and displays pipeline performance metrics |
| M5.7 | System optimization | Overall system performance meets target benchmarks for latency and throughput |

## 7. Timeline Summary

| Phase | Duration | Key Deliverables | Dependencies |
|--|--|--|--|
| Phase 1: Foundation | Week 1-2 | Modular architecture, centralized configuration | None |
| Phase 2: Project Management | Week 3-4 | Project CRUD, project selection | Phase 1 |
| Phase 3: Ingestion Pipeline | Week 5-6 | File upload, embedding generation, indexing | Phase 2 |
| Phase 4: RAG Integration | Week 7-8 | Search engine, context construction, source display | Phase 3 |
| Phase 5: Deep Processing | Week 9-10 | Semantic analysis, caching, optimization | Phase 4 |

## 8. Risk Management

### Technical Risks

The Gleann embedding engine may not function correctly on all systems. The fallback chain to Mistral and DeepSeek mitigates this risk. The system should test all embedding providers during Phase 3.

The HNSW index may experience performance degradation with large document sets. The index resizing and optimization mechanisms address this risk. The system should monitor index performance during Phase 5.

### Schedule Risks

The deep processing mode requires integration with a language model API. API availability and rate limits may affect development progress. The system should implement robust retry mechanisms and fallback strategies.

The parallel processing implementation may introduce concurrency issues. The system should implement proper synchronization and error handling.

### Mitigation Strategies

Each phase includes testing and validation milestones. The system should conduct integration testing after each phase to identify issues early.

The system should maintain backward compatibility with existing chat functionality throughout the development process. This ensures that users can continue using the application during development.

## 9. Success Criteria

The roadmap succeeds when the following criteria are met. The system supports multiple isolated projects with independent data stores. Users can upload documents to projects and search them through the chat interface. The model generates responses enriched with relevant context from the active project. The system maintains performance and reliability under expected usage patterns.

The final evaluation should compare system performance before and after RAG integration. Metrics include response accuracy, response completeness, and user satisfaction.