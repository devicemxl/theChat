import sys, tempfile, os
sys.path.insert(0, '.')
class _Fake: pass
sys.modules['streamlit'] = _Fake()

from database import ChatDatabase

tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
tmp.close()

# --- Test 1: creación inicial ---
db = ChatDatabase(tmp.name)
print("✓ init + migración inicial")

# --- Test 2: idempotencia (segundo arranque) ---
db2 = ChatDatabase(tmp.name)
print("✓ migración idempotente (segunda pasada no explota)")

# --- Test 3: crear proyectos ---
p_raitec = db.create_project("Raitec", icon="🌱", color="#22c55e",
                              system_prompt="Eres parte de un pipeline agrobiotech. Solo responde.")
p_cogneu = db.create_project("CogNeu", icon="🧠", color="#8b5cf6")
p_music  = db.create_project("Music arranger", icon="🎼", color="#f59e0b")
print(f"✓ 3 proyectos creados: {p_raitec}, {p_cogneu}, {p_music}")

# --- Test 4: UNIQUE en name ---
import sqlite3
try:
    db.create_project("Raitec")
    print("✗ debería haber fallado por UNIQUE")
except sqlite3.IntegrityError:
    print("✓ UNIQUE en name funciona")

# --- Test 5: validación de nombre vacío ---
try:
    db.create_project("   ")
    print("✗ debería haber fallado por nombre vacío")
except ValueError:
    print("✓ nombre vacío rechazado")

# --- Test 6: crear chats y asignar a proyectos ---
c1 = db.create_conversation("Chat sobre trazabilidad")
c2 = db.create_conversation("Diseño de VivaceGraph")
c3 = db.create_conversation("Chat huérfano")
c4 = db.create_conversation("Otro sobre pipeline")

db.assign_conversation_to_project(c1, p_raitec)
db.assign_conversation_to_project(c2, p_cogneu)
db.assign_conversation_to_project(c4, p_raitec)
# c3 queda con project_id = NULL
print("✓ chats asignados")

# Insertar un mensaje en cada chat para que get_conversations no los filtre por vacíos
for cid in [c1, c2, c3, c4]:
    db.save_message(cid, {"role":"user","content":"x"})

# --- Test 7: get_projects con conteo ---
projects = db.get_projects()
counts = {p['name']: p['conversation_count'] for p in projects}
print(f"✓ conteos por proyecto: {counts}")
assert counts == {'CogNeu': 1, 'Music arranger': 0, 'Raitec': 2}, "conteo incorrecto"

# --- Test 8: get_conversations_grouped ---
grouped = db.get_conversations_grouped()
print(f"✓ grouped tiene {len(grouped)} secciones (3 proyectos + sin-proyecto)")
for section in grouped:
    pname = section['project']['name'] if section['project'] else '(Sin proyecto)'
    convs = [c['title'] for c in section['conversations']]
    print(f"    · {pname}: {convs}")

# --- Test 9: update_project ---
db.update_project(p_music, name="Music Arranger", color="#eab308")
p = db.get_project(p_music)
assert p['name'] == 'Music Arranger'
assert p['color'] == '#eab308'
print("✓ update_project (name + color)")

# --- Test 10: update_project rechaza campos no whitelisted ---
db.update_project(p_music, malicious_field="X", name="MA v2")
p = db.get_project(p_music)
assert 'malicious_field' not in p
assert p['name'] == 'MA v2'
print("✓ whitelist de campos en update")

# --- Test 11: delete_project — chats se desasignan ---
orphaned = db.delete_project(p_raitec)
print(f"✓ delete_project → {orphaned} chats desasignados")
assert orphaned == 2

# Verificar que los chats sobreviven
assert db.get_conversation(c1) is not None
assert db.get_conversation(c4) is not None
# Y que ya no tienen project_id
import sqlite3 as s
with s.connect(tmp.name) as conn:
    row = conn.execute("SELECT project_id FROM conversations WHERE id = ?", (c1,)).fetchone()
    assert row[0] is None, f"c1 debería tener project_id=NULL, tiene {row[0]}"
print("✓ chats desasignados, no borrados")

# --- Test 12: proyecto ya no existe ---
assert db.get_project(p_raitec) is None
print("✓ proyecto eliminado físicamente")

# --- Test 13: nombre reutilizable después de borrado ---
p_raitec_v2 = db.create_project("Raitec")
print(f"✓ nombre reutilizable tras hard delete (nuevo id: {p_raitec_v2})")

os.unlink(tmp.name)
print("\n✅ Todos los tests pasan.")