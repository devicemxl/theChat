
import streamlit as st
import streamlit.components.v1 as components
from streamlit_arborist import tree_view # tree


print("""Vista de gestión de proyectos.

## Project Map

### Points

    Points
        |-- Objectives
        |-- Scope
        |-- Constrains
        |-- Requirements
        |-- Success Criteria

### Roadmap

    Roadmap
        |-- phase1
        |-- ***
        |-- Outcome

### Phase's Scheme

    ===================
    |    QUESTION     |
    ===================
             | investigated by
    ===================
    |    RESEARCH     |
    ===================
             | produces
    ===================
    |     FINDING     |
    ===================
             | motivates
    ===================
    |    DECISION     |
    ===================
             | how do it
    ===================
    |     SOLVED      |
    ===================
             | implemented by
    ===================
    |    ARTIFACT     |
    ===================
             
##

1. Los chats se asignan a proyectos desde la vista Chat (Fase 3 del refactor).
2. Nunca se puede borrar un proyecto, los chats nunca se eliminan.

""")

def ChangeButtonColour(widget_label, font_color, background_color='transparent'):
    # https://discuss.streamlit.io/t/struggling-with-buttons-colors/39296/3
    htmlstr = f"""
        <script>
            var elements = window.parent.document.querySelectorAll('button');
            for (var i = 0; i < elements.length; ++i) {{ 
                if (elements[i].innerText == '{widget_label}') {{ 
                    elements[i].style.color ='{font_color}';
                    elements[i].style.background = '{background_color}'
                }}
            }}
        </script>
        """
    components.html(f"{htmlstr}", height=0, width=0)

st.set_page_config(layout="wide")
PROJECT_NAME =          "Project Mock"
PROJECT_DESCRIPTION =   "Project Mock to build the project interface"
HEAD_TAGS =             {
                        "PROBLEM":PROJECT_DESCRIPTION, 
                        "STATUS": "Framing → Exploration",
                        "ROADMAP": "Phase 2 / 4"
                        }

data =  [
        {"id":"q1","name":"Dimensionality",
            "children":[
                        {"id":"a0","name":"Question: Can the representation survive dimensional reduction?"},
                        {"id":"a1","name":"Finding: 512D preserves sufficient recall"},
                        {"id":"a2","name":"Decision: Use 512D for retrieval"}
                        ]},
        {"id":"q2","name":"Synchronization",
            "children":[
                        {"id":"b1","name":"Question: When should synchronization occur?"},
                        {"id":"b2","name":"Finding: After memory update"},
                        {"id":"b3","name":"Decision: Move synchronization downstream"}
                        ]},
        {"id":"q3","name":"source of truth",
            "children":[
                        {"id":"c1","name":"Question: What is the canonical source of truth?"},
                        {"id":"c2","name":"Open"}
                        ]}
        ]

open_questions =        {
                        1:"dimensionality",
                        2:"synchronization",
                        3:"source of truth"
                        }
latest_findings =       {
                        1:"Finding 12 512D sufficient",
                        2:"Finding 11 sync after update",
                        3:"unresolved"
                        }
recent_decisions =      {
                        1:"Decision 8 use 512D",
                        2:"Decision 7 ove sync layer",
                        3:"unresolved"
                        }
open_findings =         {
                        1: ("dimensionality","Finding 12 512D sufficient", "use 512D"),
                        2: ("synchronization", "Finding 11 sync after update", "ove sync layer"),
                        3: ("source of truth", None, None)
                        }
with st.sidebar:
    st.sidebar.title(PROJECT_NAME)
    st.sidebar.caption(PROJECT_DESCRIPTION)
   # 
    if st.button("➕ + Idea", use_container_width=True, type="secondary"):
            pass
    if st.button("➕ Adjust Roadmap", use_container_width=True, type="secondary"):
            pass
    #
    with st.expander("New Objects", expanded=False):
        if st.button("Task", use_container_width=True, type="secondary"):
                pass
        if st.button("Question", use_container_width=True, type="secondary"):
                pass
        if st.button("Document", use_container_width=True, type="secondary"):
                pass
        if st.button("Experiment", use_container_width=True, type="secondary"):
                pass
        if st.button("Decision", use_container_width=True, type="secondary"):
                pass
        if st.button("Artifact", use_container_width=True, type="secondary"):
                pass
    #
    with st.expander("Ideas", expanded=True):
        with st.expander("dimensionality", expanded=True):
            "Can the representation survive dimensional reduction?"
            "\ninvestigated by:"
            "Research Name 1"
            "Research Name 2"
            "Research Name 3"
            "Research Name 4"
        with st.expander("When should sincronization occur"[:32], expanded=False):
            None
        with st.expander("What is the canonical source of truth"[:32], expanded=False):
            None
    with st.expander("Roadmap", expanded=False):
        None

#* ============================== VISTA === *
#
#^ Project Description
#^ ---------------------------
# Data Tags
empty1, tag_tag, describe_tag, empty2 = st.columns([1, 1, 3, 1])
for key in HEAD_TAGS.keys():
    with empty1: 
        ""
    with tag_tag:
        st.markdown(f"*{key}*")
    with describe_tag:
        st.caption(HEAD_TAGS[key])
    with empty2: 
        ""

# Roadmap Advance
#empty1, tag_tag, describe_tag, empty2 = st.columns([1, 1, 3, 1])
#with empty1: 
#        ""
#with tag_tag:
#    st.caption("ROADMAP")
#with describe_tag:
#    st.progress(50)
#with empty2: 
#        ""
#
st.html("""
        <style>
        .st-ag {
                display: flex;
                flex-direction: row;
                flex-wrap: nowrap;
                justify-content: center;
            }
        .st-ag button {
                padding-left:15px;
                padding-right:15px;
            }
        [data-baseweb="tab-panel"],
        .st-tabs,
        .st-tabs .element-container,
        .st-tabs .stElementContainer {
            background-color: transparent;
            height: 550px;
            max-height:35vh;
            overflow-y:hidden;
            overflow-x:hidden;
        }
        </style>
        """
)
start, tabX, ending = st.columns([1, 7, 1], gap="small")
with start:
    ""
with tabX:
    # 1. Create the tabs by providing a list of labels
    tab1, tab2, tab3 = st.tabs(["Current Questions", "Findings", "Decisions"])

    # 2. Add content to the first tab
    with tab1:
        st.caption("#### Open Questions")
        tree_view(
            data,
            icons={'open': '📂', 'closed': '📁', 'leaf': '📄'},
            padding=20,
            height=250,
            #children_accessor="nodo",
            open_by_default=True,
            selection=None,
            select_internal_nodes=True,
            search_term='',
        )

    # 3. Add content to the second tab
    with tab2:
        st.header("Visualizations")
        # Your charts go here

    # 4. Add content to the third tab
    with tab3:
        st.header("Configuration")
        # Your interactive widgets go here
with ending:
            ""
st.caption("")

start, captions, ending = st.columns([1, 7, 1], gap="small")
with captions:
    st.caption("#### Open Items")
start, kb_q0, kb_q1, kb_q2, kb_q3, ending = st.columns([1, 1, 2, 2, 2, 1], gap="small")
with start:
            ""
with kb_q0:
    st.markdown("**Id**")
with kb_q1:
    st.markdown("**Question**")
with kb_q2:
    st.markdown("**Answers**")
with kb_q3:
    st.markdown("**Decisions**")
with ending:
            ""
for key in open_findings.keys():
    start, kb_q0, kb_q1, kb_q2, kb_q3, ending = st.columns([1, 1, 2, 2, 2, 1], gap="small")
    with start:
            ""
    with kb_q0:
            st.caption(key)
    with kb_q1:
            st.caption(open_findings[key][0])
    with kb_q2:
            st.caption(open_findings[key][1])
    with kb_q3:
            st.caption(open_findings[key][2])
    with ending:
            ""

st.divider()

st.caption("#### Open Items")

st.subheader("")
st.header("")

# make a small space
st.title(" ")
"MOVER A SIDEBAR"
#
#^ Tooling Presentation
#^ ---------------------------
c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    # Generate New Object
    "Moved to sidebar"
with c2:
    # Project Deep Review
    with st.expander("Project Data", expanded=False):
            if st.button("Tasks", use_container_width=True, type="secondary"):
                pass
            if st.button("Questions", use_container_width=True, type="secondary"):
                pass
            if st.button("Documents", use_container_width=True, type="secondary"):
                pass
            if st.button("Experiments", use_container_width=True, type="secondary"):
                pass
            if st.button("Decision", use_container_width=True, type="secondary"):
                pass
            if st.button("Artifacts", use_container_width=True, type="secondary"):
                pass
with c3:
    # Caution: Danger Zone
    with st.expander("Project Tools", expanded=False):
            if st.button("➕ Toughs", use_container_width=True, type="secondary"):
                pass
            if st.button("➕ Config", use_container_width=True, type="secondary"):
                pass
            st.subheader("\n")
            if st.button("➕ Archive the Project", use_container_width=False, type="secondary"):
                pass
