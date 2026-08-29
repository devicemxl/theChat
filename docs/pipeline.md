# Pipeline and Model Decision Flow[](#pipeline-and-model-decision-flow)

| key             | value                                                                      |
|-----------------|----------------------------------------------------------------------------|
| tipo            | technical document · system architecture                                   |
| tema            | software architecture · RAG · pipeline design                              |
| titulo          | RAG Pipeline and Model Decision Flow                                       |
| parte           | VI — System Architecture                                                   |
| maturity        | draft for review                                                           |
| confidence      | high (concept) · medium (final implementation)                             |
| material origen | June 2026 conversation — pipeline design for multi-project RAG integration |
| fecha           | 2026-06-08                                                                 |
| mantenedor      | David                                                                      |

## 1. Pipeline Overview[](#1-pipeline-overview)

The system implements a retrieval augmented generation pipeline that transforms user queries into context-enriched responses. The pipeline operates in two distinct phases: the ingestion phase, which prepares documents for retrieval, and the query phase, which retrieves relevant context and generates responses.

The pipeline is designed to be modular and configurable. Each stage operates independently, allowing for individual optimization and replacement. The system maintains clear interfaces between stages to facilitate testing and debugging.

## 2. Ingestion Pipeline[](#2-ingestion-pipeline)

### 2.1 Document Acquisition[](#2-1-document-acquisition)

The ingestion pipeline begins with document acquisition. Users upload files through the Streamlit interface or place files in designated project directories. The system supports multiple file formats including plain text, markdown, PDF, DOCX, CSV, JSON, and source code files.

The acquisition stage validates file integrity, checks for duplicates, and assigns unique identifiers to each document. Files are stored temporarily before processing begins.

### 2.2 Text Extraction[](#2-2-text-extraction)

The text extraction stage converts uploaded files into plain text. Each file type uses a dedicated extraction adapter. PDF files use a PDF reader library, DOCX files use a document processing library, and text-based formats use direct decoding.

The extraction stage handles encoding detection and normalization. Unicode normalization ensures consistent text representation across different source formats.

### 2.3 Text Segmentation[](#2-3-text-segmentation)

The segmentation stage divides extracted text into manageable chunks. The system uses a sliding window approach with configurable chunk size and overlap parameters. This approach preserves contextual continuity between adjacent chunks.

For deep processing mode, each chunk represents a semantic unit for further analysis. For quick processing mode, chunks are used directly for embedding generation.

### 2.4 Semantic Analysis (Deep Mode)[](#2-4-semantic-analysis-deep-mode)

In deep processing mode, each chunk is sent to a language model for semantic analysis. The model performs three tasks: extracting semantic units, generating page summaries, and assigning descriptive tags.

The semantic unit extraction identifies coherent ideas or paragraphs within each chunk. The page summary provides a concise overview of the chunk content. The tag assignment generates 2-5 descriptive labels that capture the key concepts.

The system implements a retry mechanism for failed analyses. After three attempts, the system falls back to using the raw text as the semantic unit with generic tags.

### 2.5 Embedding Generation[](#2-5-embedding-generation)

The embedding generation stage converts text chunks into vector representations. The primary embedding engine is Gleann with EmbeddingGemma, operating locally for speed and privacy.

Each text chunk is prefixed appropriately before embedding. Documents use the document prefix, queries use the query prefix, and similarity comparisons use the similarity prefix. This asymmetric approach optimizes retrieval quality.

If the primary engine fails, the system falls back to Mistral embedding API. DeepSeek embedding serves as a final alternative.

### 2.6 Storage and Indexing[](#2-6-storage-and-indexing)

The storage stage inserts documents into the project's SQLite database and HNSW index. Each document record includes the embedding as a binary blob, the text link, tags as serialized JSON, and full content.

The HNSW index is updated incrementally. When the index reaches capacity, the system resizes it by doubling the maximum elements. The index metadata is updated after each modification.

### 2.7 Deduplication[](#2-7-deduplication)

The deduplication stage removes redundant documents. The system identifies duplicates based on text links and retains only the most recent version. This prevents index bloat and ensures search quality.

## 3. Query Pipeline[](#3-query-pipeline)

### 3.1 Query Reception[](#3-1-query-reception)

The query pipeline begins when the user submits a message in the chat interface. The system captures the query text, identifies the active project, and determines whether RAG search is enabled.

### 3.2 Query Preprocessing[](#3-2-query-preprocessing)

The preprocessing stage cleans and normalizes the query text. The system detects whether the query is a reformulation of a previous question. Reformulation detection uses keyword matching to identify phrases like "rephrase," "try again," or "make it clearer."

### 3.3 Embedding Generation[](#3-3-embedding-generation)

The embedding generation stage converts the query into a vector representation. The query uses the query prefix to ensure compatibility with document embeddings. The resulting vector has the same dimensionality as the document embeddings.

### 3.4 Vector Search[](#3-4-vector-search)

The vector search stage queries the active project's HNSW index. The system requests a configurable number of nearest neighbors, typically 50-100 candidates. The search uses cosine similarity to measure vector proximity.

The HNSW index returns the identifiers and distances of the nearest neighbors. These identifiers correspond to document IDs in the SQLite database.

### 3.5 Metadata Retrieval[](#3-5-metadata-retrieval)

The metadata retrieval stage fetches document records from SQLite using the identifiers returned by the vector search. The system constructs a SQL query with the appropriate placeholders and retrieves the text links, tags, and content for each candidate.

### 3.6 Filtering[](#3-6-filtering)

The filtering stage applies optional filters to the candidate set. If the user specified a tag filter, the system retains only documents containing that tag. If a similarity threshold is configured, documents below the threshold are discarded.

The filtering stage also removes duplicate documents and documents that were previously used in the conversation to avoid repetition.

### 3.7 Ranking[](#3-7-ranking)

The ranking stage sorts the filtered candidates by similarity score. Documents with higher similarity scores appear first. The system applies a cutoff to retain only the top-N documents for context construction.

### 3.8 Context Construction[](#3-8-context-construction)

The context construction stage builds the enriched prompt for the language model. The system inserts the retrieved documents into the system prompt with their similarity scores and content.

The context format includes document titles, similarity scores, and content snippets. The system limits the total context size to prevent exceeding the model's token limit.

### 3.9 Response Generation[](#3-9-response-generation)

The response generation stage sends the enriched prompt to the selected AI provider. The system supports multiple providers including DeepSeek, Gemini, and Mistral. Each provider uses a dedicated streaming adapter.

The response is streamed to the user in real-time. The system displays partial responses as they arrive, providing immediate feedback.

## 4. Model Decision Flow[](#4-model-decision-flow)

### 4.1 Query Classification[](#4-1-query-classification)

The model first classifies the query to determine whether RAG context is necessary. The classification considers query complexity, domain specificity, and the presence of technical terms.

If the query is a simple factual question, the model may answer directly without context. If the query requires domain knowledge or references specific documents, the model requests RAG context.

### 4.2 Relevance Assessment[](#4-2-relevance-assessment)

When RAG context is provided, the model assesses the relevance of each retrieved document. The model evaluates whether the document content addresses the query intent and provides useful information.

Documents that are irrelevant or redundant are ignored. The model focuses on the most relevant documents to construct the response.

### 4.3 Context Utilization[](#4-3-context-utilization)

The model determines how to utilize the retrieved context. It may extract specific facts, synthesize information from multiple documents, or use the context to structure the response.

The model indicates when the context is insufficient to answer the query. In such cases, the model states that the information was not found in the available documents.

### 4.4 Response Construction[](#4-4-response-construction)

The model constructs the response using the relevant context. The response structure adapts to the query type. Factual questions receive direct answers. Analytical questions receive structured explanations with supporting evidence.

The model cites the sources used in the response. Source citations appear as references to the document titles and similarity scores.

### 4.5 Reformulation Handling[](#4-5-reformulation-handling)

If the query is a reformulation, the model incorporates the reformulation context. The model reviews the previous response and the user's requested changes. It generates a revised response that addresses the specific concerns raised.

## 5. Error Handling and Fallbacks[](#5-error-handling-and-fallbacks)

### 5.1 Embedding Failures[](#5-1-embedding-failures)

If embedding generation fails, the system attempts alternative embedding providers. The fallback chain is Gleann, Mistral, then DeepSeek. If all providers fail, the system returns an error message to the user.

### 5.2 Search Failures[](#5-2-search-failures)

If the vector search returns no results, the system attempts a tag-based search. If tag-based search also returns no results, the system informs the user that no relevant documents were found.

### 5.3 Provider Failures[](#5-3-provider-failures)

If the selected AI provider fails, the system attempts to switch to an alternative provider. The fallback chain is DeepSeek, Gemini, then Mistral. The system preserves the conversation context during provider switching.

### 5.4 Timeout Handling[](#5-4-timeout-handling)

The system implements configurable timeouts for all external calls. If a timeout occurs, the system retries the operation up to three times with exponential backoff. After three failures, the system returns an error message.

## 6. Performance Considerations[](#6-performance-considerations)

### 6.1 Caching[](#6-1-caching)

The system implements caching at multiple levels. Query embeddings are cached to avoid redundant computation. Search results are cached for repeated queries. Response generation may be cached for identical queries.

### 6.2 Parallel Processing[](#6-2-parallel-processing)

The ingestion pipeline supports parallel processing of multiple documents. The system processes documents concurrently when resources allow. This reduces ingestion time for large document sets.

### 6.3 Lazy Loading[](#6-3-lazy-loading)

The system implements lazy loading for expensive resources. The embedding engine loads on first use. The HNSW index loads when a project is activated. This minimizes startup time and memory usage.

### 6.4 Index Optimization[](#6-4-index-optimization)

The system periodically optimizes the HNSW index. Optimization includes rebuilding the index with updated parameters and removing deleted documents. This maintains search quality over time.

## 7. Monitoring and Logging[](#7-monitoring-and-logging)

### 7.1 Query Logging[](#7-1-query-logging)

The system logs all queries with their embeddings, search results, and response metadata. This provides an audit trail and enables analysis of search quality.

### 7.2 Performance Metrics[](#7-2-performance-metrics)

The system tracks pipeline performance metrics including embedding time, search time, and response generation time. These metrics are displayed in the statistics section.

### 7.3 Error Logging[](#7-3-error-logging)

The system logs all errors with contextual information including the operation, the input, and the error message. This facilitates debugging and system improvement.