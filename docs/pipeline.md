# RAG Pipeline (planned)

| key             | value                                                             |
|-----------------|-------------------------------------------------------------------|
| tipo            | technical document · planned pipeline design                      |
| tema            | RAG · ingestion pipeline · query pipeline                         |
| titulo          | RAG Pipeline for theChat                                          |
| maturity        | design plan — no implementation exists yet                        |
| confidence      | medium (concept) · low (final implementation)                     |
| material origen | design discussions through August 2026                            |
| fecha           | 2026-08-31                                                        |
| mantenedor      | David                                                             |

## 1. Status

This document describes the retrieval-augmented pipeline planned for theChat.
As of this writing, none of it is implemented. The `views/ingest.py` page is
a stub. No embedding, no indexing, no retrieval code exists in the
repository. The database schema already carries two columns (`indexed_at`,
`pending_reindex`) as silent preparation, but nothing writes to them yet.

Numbers, sequencing, and specific library choices are working hypotheses
that will be validated when implementation starts.

## 2. Design intent

The pipeline handles two flows:

- **Ingestion**: user uploads documents to a project → text is extracted,
  chunked, optionally analyzed by a small LLM, embedded, and stored.
- **Query**: user asks a question in a chat → the question is embedded, the
  vector index returns candidate chunks, metadata filters narrow them by
  project (and optionally by tag), the top-K are formatted into a system
  prompt and passed to the chat's provider.

Design principles carry over from the main architecture: local storage, no
service layer, no queue. The pipeline is a set of functions that run inside
the same Streamlit process.

## 3. Ingestion pipeline

### 3.1 Acquisition

Files arrive through a multi-file uploader in `views/ingest.py`. The user
selects the destination project explicitly. Supported formats mirror the
chat attachment set: text, markdown, PDF, DOCX, CSV, JSON, code files.

Duplicate detection uses a content hash. If a document already exists in
the target project with the same hash, the upload is skipped and the user
is told.

### 3.2 Text extraction

One adapter per format. PDFs via `pypdf`, DOCX via `python-docx`, CSV/JSON
as plain text, code files as plain text with encoding detection. Extraction
adapters live in `utils/file_handler.py` alongside the ones already used
for chat attachments — same code path.

Unicode normalization is applied uniformly. Extracted text is not stored
raw at document level — it is stored as chunks (see below).

### 3.3 Chunking

Sliding window over character count, with configurable size and overlap.
Starting point: 1000 characters with 200 overlap. These numbers will be
tuned against real corpora, not chosen up front.

Each chunk records:

- source document ID
- position (offset in the source)
- text
- content hash (for deduplication and change detection)

### 3.4 Deep analysis (optional)

When "deep mode" is selected, each chunk is passed through a small local
LLM to produce:

- a one-sentence summary
- 2-5 descriptive tags

Candidate models: Qwen3-0.6B, OpenELM-270M, or another small model exposed
via nxDeck. Failures fall back to storing the chunk with an empty summary
and no tags — no ingestion is blocked because of an analysis failure.

Deep mode is opt-in per ingestion because it multiplies processing time
significantly.

### 3.5 Embedding

Primary target: gleann + EmbeddingGemma, 512-dim vectors with block-wise
int8 quantization. Documents use the document prefix; queries use the query
prefix. This asymmetric prefixing is standard for embedding models trained
that way and is not optional.

If gleann is unavailable on the current platform, an API-based fallback
(Mistral or DeepSeek embed) is used. The fallback is for portability, not
for a resilience story.

### 3.6 Storage and indexing

Each chunk is inserted into SQLite with its embedding as a BLOB and its
tags as JSON. The chunk's ID is added to the HNSW index. The index is
shared across projects; project isolation happens through metadata
filtering at query time (see §5.1).

Index resizing follows the standard HNSW pattern: double `max_elements`
when the index reaches capacity.

## 4. Query pipeline

### 4.1 Query intake

The user types a question in `views/chat.py`. Before the request goes to
the LLM, the pipeline checks whether RAG is enabled for the current
session and whether the active conversation belongs to a project that has
any indexed documents.

If either check fails, the request goes to the LLM without retrieval — the
existing chat flow, unchanged.

### 4.2 Query embedding

The question is embedded with the query prefix, producing a 512-dim vector
compatible with the document embeddings.

### 4.3 Vector search

The HNSW index returns K candidates. K starts at 50 and adjusts based on
how selective the project filter is (adaptive over-retrieval, see §5.1).

### 4.4 Metadata retrieval and filtering

Candidate IDs are used to fetch chunk rows from SQLite. The rows are then
filtered:

- **Project**: keep only chunks belonging to the active project.
- **Tag** (optional): if the user specified a tag filter, keep only chunks
  carrying that tag.
- **Recency of use** (optional): drop chunks already surfaced earlier in
  the same conversation to reduce repetition.

### 4.5 Ranking and cutoff

Filtered candidates are sorted by cosine similarity. The top N (starting
point: 5) survive to context construction.

### 4.6 Context construction

Retrieved chunks are inlined into the system prompt, each with a header
containing the source document name and similarity score. The prompt
instructs the model to prefer the provided context and to say so when the
context is insufficient.

Total context size is capped at a fraction of the model's window (target:
~4000 tokens of retrieval context, adjustable per provider).

### 4.7 Response

The enriched prompt is sent to the selected chat provider through the
existing streaming client. The UI shows the sources used in an expander
below the response.

## 5. Cross-cutting decisions

### 5.1 Shared index with metadata filtering

One HNSW index across projects, with `project_id` as a filter applied after
retrieval, is the starting design. The trade-off is post-filtering recall
on selective filters (a project with 100 chunks inside a corpus of 1M).

Mitigation for the first iteration: adaptive over-retrieval — start with
K=50, expand up to K=1000 if the filtered set is too small. This costs
bandwidth (up to 1000 IDs transferred and metadata-joined) but keeps the
index architecture simple.

If this proves insufficient in practice, two escalation paths exist:

- **Namespace partitioning inside the graph** (chunks from different
  projects are never neighbors)
- **Filtered HNSW** (filter evaluated during graph traversal)

Both are non-trivial to implement well. Neither is scoped for the first
iteration.

### 5.2 Move-a-chat semantics

Reassigning a chat to a different project today is a single-column UPDATE.
When chunks and embeddings exist per-conversation, the reassignment must
propagate to the vector index.

Two planned UX flows:

- Bloqueante with confirmation modal (like "clear conversation").
- Instant + background reindex, using the `pending_reindex = 1` flag and
  the partial index that already exist in the schema.

The second option is preferred by default because the reindex latency for
a single chat can be significant. The first option remains available for
users who want RAG consistency immediately after a move.

### 5.3 Caching

Query embedding: cache by hash of the query text. Same question in
sequence should not re-embed.

Search results: cache by (project_id, query_hash) for a short TTL, so
provider retries and reformulations don't re-search.

Both caches are in-memory (Python dict + `functools.lru_cache`). No
external cache.

## 6. Failure modes

### 6.1 Embedding failures

If the primary embedder fails on a document, retry twice, then fall back
to an API-based embedder. If all fail, the document is stored without
embedding and marked for later retry. Ingestion of the rest continues.

### 6.2 Search failures

If the index returns no candidates, the request goes to the LLM without
retrieval (as if RAG were off), and the UI notes that no context was
found.

### 6.3 Provider failures

Unchanged from the current architecture: failures are surfaced to the
user with the raw error message. There is no automatic provider failover.

## 7. What this pipeline is not

It is not a search engine, not a knowledge management platform, not a
service. It has no query optimization layer, no learning-to-rank, no
personalization, no multi-user semantics. Every document belongs to a
project owned by one user (me), and retrieval respects that boundary.
