import streamlit as st
from openai import OpenAI
from typing import List, Dict, Optional
import time
from datetime import datetime, timedelta
# Importar la base de datos
# from database import ChatDatabase

# ============================================
# CONFIGURACIÓN Y ESTADO INICIAL
# ============================================

st.set_page_config(
    page_title="🤖 DeepSeek Chat con Reformulación Inteligente",
    page_icon="🤖",
    layout="wide"
)

# Configurar cliente
client = OpenAI(
    api_key=st.secrets["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com/v1"
)


# Inicializar estado de sesión
def init_session_state():
    """Inicializa todas las variables de sesión necesarias"""

    if "openai_model" not in st.session_state:
        st.session_state["openai_model"] = "deepseek-chat"

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "system", "content": "Eres un asistente experto. Si el usuario reformula una pregunta, prioriza siempre la versión más reciente."}
        ]

    if "stop_generation" not in st.session_state:
        st.session_state.stop_generation = False

    if "last_truncated" not in st.session_state:
        st.session_state.last_truncated = False

    if "reformulation_count" not in st.session_state:
        st.session_state.reformulation_count = 0

    if "interrupt_stats" not in st.session_state:
        st.session_state.interrupt_stats = {
            'total_interruptions': 0,
            'reformulations_detected': 0,
            'tokens_estimated_wasted': 0,
            'last_interruption_time': None
        }

    if "current_stream" not in st.session_state:
        st.session_state.current_stream = None

    if "generation_start" not in st.session_state:
        st.session_state.generation_start = None

    if "partial_response" not in st.session_state:
        st.session_state.partial_response = ""

    # ✅ NUEVO: Inicializar mensaje truncado pendiente
    if "pending_truncated_message" not in st.session_state:
        st.session_state.pending_truncated_message = None

init_session_state()


# ============================================
# CLASES Y FUNCIONES DE CONTROL
# ============================================

class SmartStreamController:
    """Controlador de streaming con detección de interrupciones"""

    def __init__(self):
        self.should_stop = False
        self.max_time = 30  # Segundos máximos por respuesta

    def stop(self):
        """Detiene la generación actual"""
        self.should_stop = True
        if st.session_state.current_stream:
            st.session_state.current_stream.close()
        st.session_state.stop_generation = True

    def reset(self):
        """Resetea el controlador para nueva generación"""
        self.should_stop = False
        st.session_state.stop_generation = False
        st.session_state.generation_start = datetime.now()

    def timeout_reached(self) -> bool:
        """Verifica si se alcanzó el tiempo máximo"""
        if st.session_state.generation_start:
            elapsed = datetime.now() - st.session_state.generation_start
            return elapsed > timedelta(seconds=self.max_time)
        return False

    def should_abort(self) -> bool:
        """Determina si se debe abortar la generación"""
        return self.should_stop or st.session_state.stop_generation or self.timeout_reached()

def detect_reformulation(messages: List[Dict]) -> bool:
    """
    Detecta si hubo reformulación en la última interacción.
    Ahora verifica la metadata 'truncated' en el historial.
    """

    if len(messages) < 3:
        return False

    # Buscar el último mensaje del usuario
    last_user_idx = None
    for i in range(len(messages)-1, -1, -1):
        if messages[i]["role"] == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        return False

    # Verificar si hay una respuesta truncada antes
    # (puede ser inmediatamente antes o antes de otra pregunta)
    for j in range(last_user_idx-1, -1, -1):
        if messages[j]["role"] == "assistant":
            # Verificar metadata de truncamiento
            return messages[j].get('truncated', False)
        elif messages[j]["role"] == "user":
            break  # Llegamos a otra pregunta del usuario

    return False

def build_context_with_reformulation_awareness(messages: List[Dict]) -> List[Dict]:
    """
    Construye el contexto para la API con conocimiento de reformulaciones.

    Esta es la función clave que le dice al modelo:
    "El usuario reformuló su pregunta, prioriza la nueva versión"
    """

    context = []
    reformulation_count = 0

    for i, msg in enumerate(messages):
        # Si encontramos una respuesta truncada seguida de una nueva pregunta
        if (i > 0 and 
            messages[i]["role"] == "user" and 
            messages[i-1].get("truncated", False)):

            reformulation_count += 1

            # Obtener el contenido de la respuesta truncada (primeros 200 caracteres)
            truncated_content = messages[i-1].get("content", "")[:200]

            # Agregar hint del sistema ANTES de la nueva pregunta
            context.append({
                "role": "system",
                "content": f"⚠️ [Reformulación #{reformulation_count} detectada] "
                          f"El usuario interrumpió la respuesta anterior porque estaba incompleta. "
                          f"La respuesta parcial fue: \"{truncated_content}...\"\n"
                          f"La siguiente pregunta tiene PRIORIDAD ABSOLUTA. "
                          f"Usa la nueva pregunta como la única válida."
            })

            # Marcar la pregunta reformulada
            context.append({
                "role": "user",
                "content": f"🎯 [PREGUNTA REFORMULADA - PRIORIDAD MÁXIMA]: {messages[i]['content']}"
            })
        else:
            # Copiar mensaje normal
            context.append(msg)

    # Resumen final de reformulaciones
    if reformulation_count > 0:
        context.append({
            "role": "system",
            "content": f"📋 Resumen: El usuario ha reformulado {reformulation_count} vez(ces). "
                      f"Ignora las preguntas anteriores truncadas. "
                      f"Concéntrate SOLO en la última pregunta del usuario."
        })

    return context

def track_interruption(partial_response: str):
    """Registra estadísticas de interrupción"""

    stats = st.session_state.interrupt_stats
    stats['total_interruptions'] += 1
    stats['last_interruption_time'] = datetime.now().strftime('%H:%M:%S')

    # Estimación aproximada de tokens (4 chars ~ 1 token)
    estimated_tokens = len(partial_response) // 4
    stats['tokens_estimated_wasted'] += estimated_tokens

    # Si hay reformulación (habrá otra pregunta)
    if detect_reformulation(st.session_state.messages):
        stats['reformulations_detected'] += 1

def stream_with_enhanced_control(controller: SmartStreamController, messages: List[Dict]):
    """
    Streaming con control total y capacidad de detección de interrupción.
    """

    stream = client.chat.completions.create(
        model=st.session_state["openai_model"],
        messages=messages,
        stream=True,
        temperature=0.3,
        max_tokens=2000
    )

    # Guardar referencia para poder cancelar
    st.session_state.current_stream = stream

    full_response = ""

    try:
        for chunk in stream:
            # Verificar condiciones de parada
            if controller.should_abort():
                # Cerrar la conexión con la API
                stream.close()
                break

            if chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield token, full_response, False  # (token, respuesta_acumulada, es_final)

        yield None, full_response, True  # Final normal completo

    except Exception as e:
        # Error o cancelación
        if "canceled" in str(e).lower() or "aborted" in str(e).lower():
            st.warning("🗑️ Generación cancelada")
        else:
            st.error(f"Error durante streaming: {e}")
        yield None, full_response, True

@st.cache_data(ttl=3600)
def get_embedding(text):
    return client.embeddings.create(model="text-embedding-ada-002", input=text)

def limit_context(messages, max_context_length=3000):
    """
    Limita el contexto preservando:
    - Mensaje del sistema (siempre)
    - Mensajes de reformulación (pregunta original + reformulada)
    - Metadata de truncamiento
    - Últimos mensajes de la conversación
    """

    if not messages:
        return messages

    # Preservar mensaje del sistema
    system_msg = None
    if messages[0]["role"] == "system":
        system_msg = messages.pop(0)

    # Identificar índices de reformulación
    # (pares de mensajes donde hay truncado + nueva pregunta)
    reformulation_indices = set()
    for i in range(1, len(messages)):
        if (messages[i]["role"] == "user" and 
            i > 0 and 
            messages[i-1].get("truncated", False)):
            # Marcar la respuesta truncada y la nueva pregunta
            reformulation_indices.add(i-1)
            reformulation_indices.add(i)

    # Calcular longitud actual
    total_length = sum(len(m["content"].split()) for m in messages)

    # Si no excede el límite, devolver todo
    if total_length <= max_context_length:
        if system_msg:
            messages.insert(0, system_msg)
        return messages

    # Si excede, eliminar mensajes antiguos
    # pero NUNCA los de reformulación
    while total_length > max_context_length and len(messages) > 1:
        # Encontrar el primer mensaje que NO es de reformulación
        # y NO es el último mensaje
        removed = False
        for i in range(len(messages)):
            if i not in reformulation_indices and i < len(messages) - 1:
                removed_msg = messages.pop(i)
                total_length -= len(removed_msg["content"].split())
                removed = True
                break

        # Si no se pudo eliminar nada más, romper
        if not removed:
            break

    # Reinsertar mensaje del sistema
    if system_msg:
        messages.insert(0, system_msg)

    return messages

def debug_context_status():
    """Muestra el estado del contexto en el sidebar"""

    with st.sidebar:
        st.subheader("🔍 Diagnóstico de Contexto")

        # Métricas de contexto
        full_len = sum(len(m["content"].split()) for m in st.session_state.messages)
        limited = limit_context(st.session_state.messages.copy())
        limited_len = sum(len(m["content"].split()) for m in limited)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Mensajes totales", len(st.session_state.messages))
        with col2:
            st.metric("Palabras totales", full_len)
        with col3:
            st.metric("Palabras limitadas", limited_len)

        # Mostrar metadata de truncamiento
        st.subheader("🔄 Estado de truncamiento")
        truncated_msgs = [m for m in st.session_state.messages if m.get('truncated', False)]
        if truncated_msgs:
            st.warning(f"⚠️ {len(truncated_msgs)} mensajes truncados en historial")
            for msg in truncated_msgs:
                st.text(f"🛑 {msg['role']}: {msg['content'][:50]}...")
        else:
            st.success("✅ No hay mensajes truncados")

        # Mostrar qué mensajes se eliminarían
        if full_len > limited_len:
            st.warning(f"⚠️ Se eliminarían {full_len - limited_len} palabras del contexto")

            # Mostrar qué mensajes se eliminan
            eliminated = [m for m in st.session_state.messages if m not in limited]
            if eliminated:
                st.write("**Mensajes que se eliminarían:**")
                for msg in eliminated:
                    if msg["role"] != "system":
                        trunc = "🛑" if msg.get('truncated', False) else ""
                        st.text(f"{trunc} {msg['role']}: {msg['content'][:50]}...")
        else:
            st.success("✅ Todo el contexto se mantiene")

# ============================================
# INTERFAZ DE USUARIO
# ============================================

# Sidebar con métricas y controles
with st.sidebar:
    st.header("🎛️ Controles")

    # Métricas de interrupciones
    st.subheader("📊 Métricas")
    stats = st.session_state.interrupt_stats
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Interrupciones", stats['total_interruptions'])
        st.metric("Tokens desperdiciados", f"~{stats['tokens_estimated_wasted']}")
    with col2:
        st.metric("Reformulaciones", stats['reformulations_detected'])
        st.metric("Modelo", "DeepSeek-chat")

    # Botón de reset
    if st.button("🔄 Limpiar conversación", key="clear_btn", use_container_width=True):
        st.session_state.messages = [
            {"role": "system", "content": "Eres un asistente experto. Si el usuario reformula una pregunta, prioriza siempre la versión más reciente."}
        ]
        st.session_state.reformulation_count = 0
        st.session_state.last_truncated = False
        st.session_state.partial_response = ""
        st.session_state.pending_truncated_message = None
        st.rerun()

    # DEBUG: Mostrar estado del contexto
    debug_context_status()

    st.subheader("🔍 Debug")
    if st.checkbox("Mostrar historial completo"):
        st.json(st.session_state.messages)

    if st.checkbox("Mostrar contexto limitado"):
        limited = limit_context(st.session_state.messages.copy())
        st.json(limited)

    st.subheader("🔄 Reformulaciones preservadas")
    limited = limit_context(st.session_state.messages.copy())

    # Contar reformulaciones en el contexto limitado
    reform_count = 0
    for i in range(1, len(limited)):
        if (limited[i]["role"] == "user" and 
            i > 0 and 
            limited[i-1].get("truncated", False)):
            reform_count += 1

    st.metric("Reformulaciones en contexto", reform_count)

# Título principal
st.title("🤖 DeepSeek Chat con Reformulación Inteligente")

# Mostrar historial
for message in st.session_state.messages:
    # Skip system messages in display
    if message["role"] == "system":
        continue

    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Mostrar badge de truncamiento
        if message.get('truncated', False):
            st.warning("⚠️ Respuesta interrumpida por el usuario")
        elif message.get('reformulated', False):
            st.info("🔄 Pregunta reformulada desde una respuesta interrumpida")

# Chat input
if prompt := st.chat_input("¿Qué deseas preguntar?"):
    # --- INTERRUPCIÓN AUTOMÁTICA SI HAY RESPUESTA EN CURSO ---
    if st.session_state.partial_response:
        # Guardar la respuesta parcial como truncada
        st.session_state.messages.append({
            "role": "assistant",
            "content": st.session_state.partial_response,
            "truncated": True,
            "interrupted_at": datetime.now().isoformat(),
            "reformulation_count": st.session_state.reformulation_count
        })
        st.session_state.last_truncated = True
        
        # Detener el stream si está activo
        if hasattr(st.session_state, 'controller'):
            st.session_state.controller.stop()
        
        # Actualizar estadísticas
        st.session_state.interrupt_stats['total_interruptions'] += 1
        estimated_tokens = len(st.session_state.partial_response) // 4
        st.session_state.interrupt_stats['tokens_estimated_wasted'] += estimated_tokens
        
        # Limpiar respuesta parcial para que no se vuelva a interrumpir con el mismo prompt
        st.session_state.partial_response = ""
    # --- FIN DE INTERRUPCIÓN AUTOMÁTICA ---

    # Inicializar controlador para la nueva generación
    controller = SmartStreamController()
    st.session_state.controller = controller

    # Detectar reformulación ANTES de agregar el nuevo mensaje
    had_reformulation = detect_reformulation(st.session_state.messages)

    # Agregar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Si hubo reformulación, actualizar contador
    if had_reformulation and st.session_state.last_truncated:
        st.session_state.reformulation_count += 1
        st.session_state.interrupt_stats['reformulations_detected'] += 1

    # Resetear flags
    st.session_state.last_truncated = False

    # Mostrar mensaje del usuario
    with st.chat_message("user"):
        if had_reformulation:
            st.markdown(f"🔄 **Reformulación #{st.session_state.reformulation_count}:** {prompt}")
        else:
            st.markdown(prompt)

    # Generar respuesta
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        was_interrupted = False

        # Inicializar respuesta parcial en session_state
        st.session_state.partial_response = ""

        # Limitar contexto SOLO para la API (copia)
        limited_messages = limit_context(st.session_state.messages.copy())
        # Construir contexto inteligente con la copia limitada
        api_messages = build_context_with_reformulation_awareness(limited_messages)

        # Resetear controlador
        controller.reset()

        try:
            # Stream con control
            for token, response_so_far, is_final in stream_with_enhanced_control(
                controller, api_messages
            ):
                if token:
                    full_response += token
                    st.session_state.partial_response = full_response
                    placeholder.markdown(full_response + "▌")
                elif is_final:
                    break

            # Determinar si fue interrumpida
            was_interrupted = st.session_state.stop_generation or controller.timeout_reached()

            if was_interrupted:
                st.session_state.last_truncated = True
                st.warning("⏹️ La respuesta fue interrumpida")
                track_interruption(full_response)
            else:
                st.session_state.last_truncated = False

            # Mostrar respuesta final
            placeholder.markdown(full_response)

        except Exception as e:
            st.error(f"Error en la generación: {e}")
            was_interrupted = True
            full_response = f"⚠️ Error: {e}"
            st.session_state.partial_response = full_response

        # GUARDAR EN HISTORIAL (solo si no se guardó ya por interrupción automática)
        # Verificar si el último mensaje ya es un asistente truncado con el mismo contenido
        if not (was_interrupted and st.session_state.messages and 
                st.session_state.messages[-1]["role"] == "assistant" and
                st.session_state.messages[-1].get("truncated", False) and
                st.session_state.messages[-1]["content"] == full_response):
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "truncated": was_interrupted,
                "interrupted_at": datetime.now().isoformat() if was_interrupted else None,
                "reformulation_count": st.session_state.reformulation_count if was_interrupted else None
            })

        # Limpiar respuesta parcial
        st.session_state.partial_response = ""

        # Limpiar referencia al stream
        st.session_state.current_stream = None


# Footer con explicación
st.markdown("---")
with st.expander("ℹ️ ¿Cómo funciona este sistema de reformulación?"):
    st.write("""
    **El sistema detecta reformulaciones inteligentemente:**

    1. **Si el usuario interrumpe** una respuesta → se marca como 'truncada'
    2. **Si hace otra pregunta** después de truncar → se detecta reformulación
    3. **El modelo recibe contexto** de que hubo reformulación
    4. **Prioriza la nueva pregunta** completamente

    **Beneficios:**
    - 💰 Los tokens desperdiciados NO se pierden (se usan como contexto)
    - 🎯 El modelo entiende la frustración del usuario
    - 🚀 Las respuestas nuevas son más relevantes
    - 📊 Tienes métricas de interrupción para optimizar
    """)