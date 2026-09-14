# mock.py — solo UI, sin funcionalidad
import streamlit as st

st.set_page_config(page_title="KB Mock", layout="wide")

# ═════════════════════════════ SIDEBAR ═════════════════════════════

with st.sidebar:
    st.title("Project Name")
    st.caption("Persistent knowledge system for code, research and decisions")

    if st.button("+ Idea / Question", use_container_width=True, type="primary"):
        pass

    if st.button("Adjust Roadmap", use_container_width=True):
        pass

    st.divider()

    # ── New Object ──
    st.markdown("##### New Object")
    col_a, col_b = st.columns(2)
    with col_a:
        st.button("Question",   use_container_width=True)
        st.button("Research",   use_container_width=True)
        st.button("Document",   use_container_width=True)
        st.button("Artifact",   use_container_width=True)
    with col_b:
        st.button("Task",       use_container_width=True)
        st.button("Experiment", use_container_width=True)
        st.button("Decision",   use_container_width=True)

    st.divider()

    # ── Project Data ──
    st.markdown("##### Project Data")
    col_c, col_d = st.columns(2)
    with col_c:
        st.button("Questions", use_container_width=True)
        st.button("Decisions", use_container_width=True)
    with col_d:
        st.button("Findings",  use_container_width=True)
        st.button("Artifacts", use_container_width=True)

    st.divider()

    # ── Questions ──
    st.markdown("##### Questions")

    st.markdown(
        """
        ▸ **dimensionality**  
        &nbsp;&nbsp;&nbsp;&nbsp;● Investigating  
        &nbsp;&nbsp;&nbsp;&nbsp;4R · 2E · 3T  
        &nbsp;&nbsp;&nbsp;&nbsp;2F · 1D · 1A
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        ▸ **synchronization**  
        &nbsp;&nbsp;&nbsp;&nbsp;● Investigating  
        &nbsp;&nbsp;&nbsp;&nbsp;2R · 1E · 2T  
        &nbsp;&nbsp;&nbsp;&nbsp;1F · 1D · 0A
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        ▸ **source of truth**  
        &nbsp;&nbsp;&nbsp;&nbsp;○ Open  
        &nbsp;&nbsp;&nbsp;&nbsp;0R · 0E · 1T  
        &nbsp;&nbsp;&nbsp;&nbsp;0F · 0D · 0A
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Roadmap ──
    st.markdown("##### Roadmap")
    st.markdown("Phase 1 &nbsp;✓", unsafe_allow_html=True)
    st.markdown("Phase 2 &nbsp;●", unsafe_allow_html=True)
    st.markdown("Phase 3 &nbsp;○", unsafe_allow_html=True)
    st.markdown("Phase 4 &nbsp;○", unsafe_allow_html=True)


# ═════════════════════════════ MAIN AREA ═════════════════════════════

# Cabecera: PROBLEM / STATUS / ROADMAP en una sola fila
h_problem, h_status, h_roadmap = st.columns([4, 3, 1])

with h_problem:
    st.caption("PROBLEM")
    st.markdown("Build a persistent knowledge system for code and research")

with h_status:
    st.caption("STATUS")
    st.markdown("Framing → Exploration → Implementation")

with h_roadmap:
    st.caption("ROADMAP")
    st.markdown("Phase 2 / 4")

st.divider()

# Tres columnas epistemológicas: Questions / Findings / Decisions
col_q, col_f, col_d = st.columns(3)

with col_q:
    st.markdown("##### CURRENT QUESTIONS")
    st.markdown(
        """
        ● **Q1 · dimensionality**  
        &nbsp;&nbsp;&nbsp;&nbsp;├─ F12 · 512D sufficient for recall  
        &nbsp;&nbsp;&nbsp;&nbsp;└─ D8 · Use 512D for retrieval  

        ● **Q2 · synchronization**  
        &nbsp;&nbsp;&nbsp;&nbsp;├─ F11 · Sync after memory update  
        &nbsp;&nbsp;&nbsp;&nbsp;└─ D7 · Move sync layer downstream  

        ○ **Q3 · source of truth**  
        &nbsp;&nbsp;&nbsp;&nbsp;└─ open
        """,
        unsafe_allow_html=True,
    )

with col_f:
    st.markdown("##### RECENT FINDINGS")
    st.markdown(
        """
        - **F12** · 512D sufficient for recall  
        - **F11** · Sync after memory update  
        - **F10** · Token budget limits window
        """
    )

with col_d:
    st.markdown("##### RECENT DECISIONS")
    st.markdown(
        """
        - **D8** · Use 512D for retrieval  
        - **D7** · Move sync layer downstream  
        - **D6** · Defer artifacts to Phase 3
        """
    )

st.divider()

# Open Items (consecuencia de las preguntas abiertas)
st.markdown("##### OPEN ITEMS")
st.checkbox("Implement benchmark",       disabled=True)
st.checkbox("Run 3 configurations",      disabled=True)
st.checkbox("Select initial dimension",  disabled=True)