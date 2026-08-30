"""Vista Data / RAG — pendiente de implementación."""
import streamlit as st

st.title("🔧 Data & RAG")
st.info(
    "Página en construcción. Aquí vivirá el pipeline de ingestión, "
    "indexación y RAG."
)

st.markdown("""
**Componentes planeados:**

- **Chunker** — sliding window por caracteres (~1 página); local via Qwen3-0.6B / OpenELM-270M sobre nxDeck.
- **Embedder** — EmbeddingGemma sobre nxDeck.
- **Store** — SQLite permanente (migración futura a nxFossil); HNSW como acotador del espacio de búsqueda.
- **Retriever** — top-k por cosine (k=3-5) + rerank con Qwen3-0.6B / OpenELM-270M.
""")
