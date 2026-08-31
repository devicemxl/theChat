import sys, tempfile, os
sys.path.insert(0, '.')
class _Fake: pass
sys.modules['streamlit'] = _Fake()

from database import ChatDatabase
from llm.api_clients import build_context_with_reformulation_awareness

tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.dbx')
tmp.close()
db = ChatDatabase(tmp.name)

# Setup: 3 chats en 3 escenarios distintos
p_normal = db.create_project("Normal", system_prompt=None)  # proyecto SIN prompt
p_strict = db.create_project(
    "Pipeline",
    system_prompt="Eres parte de un pipeline. Solo responde en JSON válido. No opines."
)

c_orphan = db.create_conversation("Chat huérfano")     # sin proyecto
c_normal = db.create_conversation("Chat en Normal")    # proyecto sin prompt
c_strict = db.create_conversation("Chat en Pipeline")  # proyecto con prompt

db.assign_conversation_to_project(c_normal, p_normal)
db.assign_conversation_to_project(c_strict, p_strict)

def prompt_for(conv_id):
    project = db.get_conversation_project(conv_id)
    return project.get("system_prompt") if project else None

# --- Test 1: chat huérfano → prompt default (con reformulación) ---
ctx = build_context_with_reformulation_awareness(
    messages=[{"role":"user","content":"hola"}],
    is_reformulation=True, reformulation_count=2,
    project_system_prompt=prompt_for(c_orphan),
)
sys_msg = ctx[0]["content"]
assert "asistente experto" in sys_msg
assert "reformulando su pregunta (intento #2)" in sys_msg
print("✓ Chat sin proyecto: default + hint de reformulación")

# --- Test 2: chat en proyecto SIN prompt → default también ---
ctx = build_context_with_reformulation_awareness(
    messages=[{"role":"user","content":"hola"}],
    is_reformulation=False, reformulation_count=0,
    project_system_prompt=prompt_for(c_normal),
)
sys_msg = ctx[0]["content"]
assert "asistente experto" in sys_msg
print("✓ Chat en proyecto sin prompt: default aplica")

# --- Test 3: chat en proyecto CON prompt → project prompt (no default) ---
ctx = build_context_with_reformulation_awareness(
    messages=[{"role":"user","content":"analiza esto"}],
    is_reformulation=True, reformulation_count=5,  # reformulación aunque sea
    project_system_prompt=prompt_for(c_strict),
)
sys_msg = ctx[0]["content"]
assert "Solo responde en JSON válido" in sys_msg
assert "asistente experto" not in sys_msg, "default filtró el project prompt!"
assert "reformulando" not in sys_msg, "hint de reformulación se inyectó cuando no debía!"
print("✓ Chat en proyecto con prompt: reemplaza default, omite reformulación")

# --- Test 4: project_system_prompt vacío (string "") → cae al default ---
ctx = build_context_with_reformulation_awareness(
    messages=[{"role":"user","content":"x"}],
    is_reformulation=False, reformulation_count=0,
    project_system_prompt="",
)
sys_msg = ctx[0]["content"]
assert "asistente experto" in sys_msg
print("✓ project_system_prompt='' se trata como ausente (cae al default)")

# --- Test 5: get_conversation_project retorna None si no hay proyecto ---
p = db.get_conversation_project(c_orphan)
assert p is None
print("✓ get_conversation_project(huérfano) → None")

p = db.get_conversation_project(c_strict)
assert p is not None
assert p["name"] == "Pipeline"
assert "JSON válido" in p["system_prompt"]
print(f"✓ get_conversation_project(en proyecto) → {p['name']}")

os.unlink(tmp.name)
print("\n✅ Fase 4 validada: system-prompt del proyecto reemplaza al default y omite reformulación.")