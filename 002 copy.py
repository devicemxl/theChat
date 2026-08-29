import streamlit as st
import time
import json
import re
import requests
import io
from typing import Any, List, Dict, Generator, Literal, Optional
from datetime import datetime
from database import ChatDatabase

# Definir constantes para los límites de tokens de cada modelo
MAX_TOKENS_DEEPSEEK = 8192
MAX_TOKENS_MISTRAL = 2000
MAX_TOKENS_GEMINI = None  # Sin límite en Gemini

# ========== FUNCIONES PARA LEER ARCHIVOS ==========
def extract_text_from_file(uploaded_file) -> str:
    """
    Extrae el texto de un archivo subido según su extensión.
    Soporta: .txt, .md, .pdf, .docx, .csv, .json, .py, .js, .html, .css, .xml, .sql
    """
    # Si no tiene extensión, intentamos leer como texto
    if '.' not in uploaded_file.name:
        try:
            return uploaded_file.getvalue().decode("utf-8", errors="ignore")
        except:
            return "[Contenido binario no legible]"

    file_extension = uploaded_file.name.split('.')[-1].lower()
    content = ""

    try:
        if file_extension in ["txt", "md"]:
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        elif file_extension == "pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                for page in reader.pages:
                    content += page.extract_text() + "\n"
            except ImportError:
                content = "[Error: pypdf no está instalado. Instálalo con 'pip install pypdf']"
        elif file_extension == "docx":
            try:
                from docx import Document
                doc = Document(io.BytesIO(uploaded_file.getvalue()))
                for para in doc.paragraphs:
                    content += para.text + "\n"
            except ImportError:
                content = "[Error: python-docx no está instalado. Instálalo con 'pip install python-docx']"
        elif file_extension == "csv":
            try:
                import pandas as pd
                df = pd.read_csv(io.BytesIO(uploaded_file.getvalue()))
                content = df.to_string()
            except ImportError:
                content = "[Error: pandas no está instalado. Instálalo con 'pip install pandas']"
        elif file_extension in ["json", "py", "js", "html", "css", "xml", "sql"]:
            content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        else:
            # Intento genérico como texto
            try:
                content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            except:
                content = "[Contenido binario no legible]"
    except Exception as e:
        content = f"[Error al leer el archivo: {str(e)}]"

    return content.strip()

# ========== FUNCIÓN PARA EXTRAER ARCHIVOS DE MENSAJES ==========
def extract_files_from_message(content: str) -> tuple[str, List[Dict]]:
    """Extrae el prompt y los archivos de un mensaje completo"""
    if "--- Contenido de '" not in content:
        return content, []

    parts = content.split("--- Contenido de '")
    prompt = parts[0].strip()
    files = []

    for part in parts[1:]:
        if "' ---" in part:
            filename = part.split("' ---")[0]
            file_content = part.split("' ---")[1].strip()
            files.append({
                "name": filename,
                "content": file_content
            })

    return prompt, files

# ========== INICIALIZACIÓN DE BASE DE DATOS ==========

def get_secret(key: str) -> str:
    """Intenta obtener un secreto de forma segura."""
    try:
        return st.secrets[key] if key in st.secrets else ""
    except Exception:
        return ""

def init_database():
    """Inicializa la base de datos y la conversación actual"""
    if "db" not in st.session_state:
        st.session_state.db = ChatDatabase("chat_history.db")

    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = st.session_state.db.create_conversation(
            f"Conversación {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

    if "messages" not in st.session_state:
        st.session_state.messages = load_conversation_messages(st.session_state.current_conversation_id)

    if "reformulation_count" not in st.session_state:
        st.session_state.reformulation_count = 0

    if "last_user_message" not in st.session_state:
        st.session_state.last_user_message = ""

    if "last_assistant_response" not in st.session_state:
        st.session_state.last_assistant_response = ""

    if "tokens_wasted" not in st.session_state:
        st.session_state.tokens_wasted = 0

    if "total_reformulations" not in st.session_state:
        st.session_state.total_reformulations = 0

    if "conversation_start_time" not in st.session_state:
        st.session_state.conversation_start_time = datetime.now()

    # --- VARIABLES PARA MÚLTIPLES APIS ---
    if "api_provider" not in st.session_state:
        st.session_state.api_provider = "DeepSeek"

    if "deepseek_api_key" not in st.session_state:
        st.session_state.deepseek_api_key = get_secret("DEEPSEEK_API_KEY")

    if "gemini_api_key" not in st.session_state:
        st.session_state.gemini_api_key = get_secret("GEMINI_API_KEY")

    if "mistral_api_key" not in st.session_state:
        st.session_state.mistral_api_key = get_secret("MISTRAL_API_KEY")

    if "api_key" not in st.session_state:
        st.session_state.api_key = st.session_state.deepseek_api_key

    if "partial_response" not in st.session_state:
        st.session_state.partial_response = ""

    if "editing_conv_id" not in st.session_state:
        st.session_state.editing_conv_id = None

    # Clave para resetear el file_uploader
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

def load_conversation_messages(conversation_id: int) -> List[Dict]:
    """Carga los mensajes de una conversación desde la base de datos"""
    db = st.session_state.db
    messages = db.get_messages(conversation_id)

    formatted_messages = []
    for msg in messages:
        content = msg["content"]

        # Procesar mensajes de usuario que contienen archivos
        if msg["role"] == "user" and "--- Contenido de '" in content:
            prompt, files = extract_files_from_message(content)
            formatted_messages.append({
                "role": msg["role"],
                "content": content,  # Mantener el contenido completo para la API
                "display_content": prompt,  # Contenido para mostrar
                "files": files,  # Archivos separados
                "truncated": msg["truncated"],
                "interrupted_at": msg["interrupted_at"],
                "reformulation_count": msg.get("reformulation_count") or 0
            })
        else:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "truncated": msg["truncated"],
                "interrupted_at": msg["interrupted_at"],
                "reformulation_count": msg.get("reformulation_count") or 0
            })
    return formatted_messages



# ========== GESTIÓN DE CONVERSACIONES ==========

def create_new_conversation():
    """Crea una nueva conversación y la establece como actual"""
    db = st.session_state.db

    title = f"Conversación {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    new_id = db.create_conversation(title)

    st.session_state.current_conversation_id = new_id
    st.session_state.messages = []
    st.session_state.reformulation_count = 0
    st.session_state.last_user_message = ""
    st.session_state.last_assistant_response = ""
    st.session_state.conversation_start_time = datetime.now()
    st.session_state.partial_response = ""

    return new_id

def switch_conversation(conversation_id: int):
    """Cambia a una conversación existente"""
    db = st.session_state.db

    st.session_state.current_conversation_id = conversation_id
    st.session_state.messages = load_conversation_messages(conversation_id)
    st.session_state.reformulation_count = 0
    st.session_state.last_user_message = ""
    st.session_state.last_assistant_response = ""
    st.session_state.conversation_start_time = datetime.now()
    st.session_state.partial_response = ""

def delete_conversation(conversation_id: int):
    """Elimina una conversación"""
    db = st.session_state.db
    db.delete_conversation(conversation_id)

    if conversation_id == st.session_state.current_conversation_id:
        create_new_conversation()

def clear_current_conversation():
    """Limpia la conversación actual"""
    st.session_state.messages = []
    st.session_state.db.delete_messages(st.session_state.current_conversation_id)
    st.session_state.reformulation_count = 0
    st.session_state.last_user_message = ""
    st.session_state.last_assistant_response = ""
    st.session_state.conversation_start_time = datetime.now()
    st.session_state.partial_response = ""
    st.success("🗑️ Conversación limpiada")

# ========== FUNCIONES DE DETECCIÓN DE REFORMULACIÓN ==========

def detect_reformulation(user_message: str) -> bool:
    """Detecta si el mensaje del usuario es una reformulación"""
    reformulation_keywords = [
        "reformula", "reformular", "reformulación", "reformulacion",
        "rephrasing", "rephrase", "reformulate",
        "otra vez", "de nuevo", "again",
        "mejor", "better", "improve",
        "más claro", "clearer", "más simple", "simpler",
        "diferente", "different", "cambia", "change",
        "reescribe", "rewrite", "reescribir",
        "explica mejor", "explain better",
        "hazlo más", "make it more",
        "intenta de nuevo", "try again",
        "no me gusta", "i don't like",
        "no es lo que quería", "not what i wanted",
        "puedes mejorar", "can you improve",
        "más profesional", "more professional",
        "más formal", "more formal",
        "más informal", "more casual",
        "más corto", "shorter",
        "más largo", "longer",
        "más detallado", "more detailed",
        "más conciso", "more concise"
    ]

    message_lower = user_message.lower()
    for keyword in reformulation_keywords:
        if keyword in message_lower:
            return True
    return False

def build_context_with_reformulation_awareness(
    messages: List[Dict],
    is_reformulation: bool,
    reformulation_count: int
) -> List[Dict]:
    """Construye el contexto estándar para la API"""
    context = []

    system_prompt = """Eres un asistente experto y útil.
Si el usuario pide una reformulación, prioriza la nueva versión de la pregunta.
Responde de manera clara, concisa y precisa."""

    if is_reformulation:
        system_prompt += f"""

        ⚠️ El usuario está reformulando su pregunta (intento #{reformulation_count}).
        Mantén la intención original pero mejora la respuesta anterior.
        Aplica los cambios específicos que el usuario solicite.
        """

    context.append({"role": "system", "content": system_prompt})

    for msg in messages:
        context.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    return context

# ========== FUNCIONES DE STREAMING ==========

def stream_deepseek_completion(
    messages: List[Dict],
    api_key: str,
    model: str = "deepseek-chat",
) -> Generator[str, None, None]:
    """Streaming para DeepSeek"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS_DEEPSEEK,  # ✅ Usar constante
        "stream": True
    }

    try:
        with requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, stream=True, timeout=30) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            json_data = json.loads(data)
                            if "choices" in json_data and json_data["choices"]:
                                delta = json_data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
    except requests.exceptions.RequestException as e:
        yield f"⚠️ Error de conexión con DeepSeek: {str(e)}"

def stream_mistral_completion(
    messages: List[Dict],
    api_key: str,
    model: str = "mistral-small-latest",
) -> Generator[str, None, None]:
    """Streaming para Mistral AI"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": MAX_TOKENS_MISTRAL,  # ✅ Usar constante
        "stream": True
    }

    try:
        with requests.post(
            url="https://api.mistral.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=30
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            json_data = json.loads(data)
                            if "choices" in json_data and json_data["choices"]:
                                delta = json_data["choices"][0].get("delta", {})
                                content = delta.get("content")
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue
    except requests.exceptions.RequestException as e:
        yield f"⚠️ Error de conexión con Mistral: {str(e)}"

def stream_gemini_completion(
    messages: List[Dict],
    api_key: str,
    model: str = "gemini-1.5-flash"
) -> Generator[str, None, None]:
    """Streaming nativo para Google AI Studio (Gemini)"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
    headers = {"Content-Type": "application/json"}

    # Gemini requiere un formato especial, aislando el "system" en "system_instruction"
    system_instruction = None
    gemini_contents = []

    for msg in messages:
        if msg["role"] == "system":
            system_instruction = {"parts": [{"text": msg["content"]}]}
        else:
            # Gemini usa "user" y "model"
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

    payload = {"contents": gemini_contents}
    if system_instruction:
        payload["system_instruction"] = system_instruction

    try:
        with requests.post(url, headers=headers, json=payload, stream=True, timeout=30) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8')
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]" or not data.strip():
                            continue
                        try:
                            json_data = json.loads(data)
                            if "candidates" in json_data and json_data["candidates"]:
                                parts = json_data["candidates"][0].get("content", {}).get("parts", [])
                                if parts and "text" in parts[0]:
                                    yield parts[0]["text"]
                        except json.JSONDecodeError:
                            continue
    except requests.exceptions.RequestException as e:
        yield f"⚠️ Error de conexión con Gemini: {str(e)}"
        
# ========== FUNCIONES DE EXPORTACIÓN/IMPORTACIÓN ==========

def export_current_conversation():
    conversation = {
        "id": st.session_state.current_conversation_id,
        "messages": st.session_state.messages,
        "reformulation_count": st.session_state.reformulation_count,
        "tokens_wasted": st.session_state.tokens_wasted,
        "total_reformulations": st.session_state.total_reformulations,
        "exported_at": datetime.now().isoformat()
    }
    json_str = json.dumps(conversation, indent=2, ensure_ascii=False)
    st.download_button(
        label="📥 Descargar JSON",
        data=json_str,
        file_name=f"conversacion_{st.session_state.current_conversation_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )

def export_all_conversations():
    db = st.session_state.db
    conversations = db.get_conversations()
    all_data = []
    for conv in conversations:
        messages = db.get_messages(conv['id'])
        all_data.append({
            "conversation_id": conv['id'],
            "title": conv['title'],
            "created_at": conv['created_at'],
            "updated_at": conv['updated_at'],
            "messages": messages
        })
    json_str = json.dumps(all_data, indent=2, ensure_ascii=False)
    st.download_button(
        label="📥 Descargar todas las conversaciones",
        data=json_str,
        file_name=f"todas_conversaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )

def import_conversations(uploaded_file):
    try:
        data = json.loads(uploaded_file.getvalue().decode("utf-8"))
        if isinstance(data, list):
            for conv_data in data:
                import_single_conversation(conv_data)
        elif isinstance(data, dict):
            import_single_conversation(data)
        st.success(f"✅ Importadas {len(data) if isinstance(data, list) else 1} conversaciones")
    except Exception as e:
        st.error(f"❌ Error al importar: {str(e)}")

def import_single_conversation(conv_data: Dict):
    db = st.session_state.db
    title = conv_data.get("title", f"Importada {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    conv_id = db.create_conversation(title)
    for msg in conv_data.get("messages", []):
        # Asegurar que reformulation_count sea entero
        reformulation_count = msg.get("reformulation_count")
        if reformulation_count is None:
            reformulation_count = 0
        db.save_message(conv_id, {
            "role": msg.get("role", "user"),
            "content": msg.get("content", ""),
            "truncated": bool(msg.get("truncated", False)),
            "interrupted_at": msg.get("interrupted_at"),
            "reformulation_count": int(reformulation_count)
        })

# ========== INTERFAZ Y SIDEBAR ==========

def update_sidebar_metrics():
    pass

def rename_conversation(conversation_id: int, new_title: str):
    st.session_state.db.update_conversation_title(conversation_id, new_title)
    st.success(f"✅ Conversación renombrada a: {new_title}")

def view_conversation_history():
    conversations = st.session_state.db.get_conversations()
    if "editing_conv_id" not in st.session_state:
        st.session_state.editing_conv_id = None

    for conv in conversations:
        with st.expander(f"📄 {conv['title']}"):
            st.write(f"**ID:** {conv['id']}")
            st.write(f"**Creada:** {conv['created_at']}")
            st.write(f"**Última actualización:** {conv['updated_at']}")
            if conv['last_message']:
                st.write(f"**Último mensaje:** {conv['last_message'][:100]}...")

            if st.session_state.editing_conv_id == conv['id']:
                new_title = st.text_input("Nuevo título", value=conv['title'], key=f"title_input_{conv['id']}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾", key=f"save_title_{conv['id']}"):
                        if new_title.strip():
                            rename_conversation(conv['id'], new_title.strip())
                            st.session_state.editing_conv_id = None 
                            st.rerun()
                        else:
                            st.warning("El título no puede estar vacío")
                with col2:
                    if st.button("🗑️", help="Eliminar esta conversación", key=f"cancel_edit_{conv['id']}"):
                        st.session_state.editing_conv_id = None
                        st.rerun()
            else:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"**Title**\n\t{conv['title']}")
                with col2:
                    if st.button("✏️  ", key=f"edit_btn_{conv['id']}"):
                        st.session_state.editing_conv_id = conv['id']
                        st.rerun()

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📂", key=f"load_{conv['id']}"):
                    switch_conversation(conv['id'])
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"delete_{conv['id']}"):
                    delete_conversation(conv['id'])
                    st.rerun()

# ========== CONFIGURACIÓN DE API KEY Y PROVEEDOR ==========

def configure_api_key():
    """Configura el Proveedor y la API key"""

    # Lista de proveedores
    proveedores = ["DeepSeek", "Google AI Studio (Gemini)", "Mistral AI"]

    # Selector de proveedor
    nuevo_proveedor = st.selectbox(
        "Proveedor de IA",
        proveedores,
        index=proveedores.index(st.session_state.api_provider) if st.session_state.api_provider in proveedores else 0
    )

    # Actualizar proveedor si cambia
    if nuevo_proveedor != st.session_state.api_provider:
        st.session_state.api_provider = nuevo_proveedor
        st.rerun()
        
    # Configuración según el proveedor
    if st.session_state.api_provider == "DeepSeek":
        key_input = get_secret("DEEPSEEK_API_KEY")
        st.session_state.deepseek_api_key = key_input
        st.session_state.api_key = key_input

    elif st.session_state.api_provider == "Google AI Studio (Gemini)":
        key_input = get_secret("GEMINI_API_KEY")
        st.session_state.gemini_api_key = key_input
        st.session_state.api_key = key_input

    elif st.session_state.api_provider == "Mistral AI":
        key_input = get_secret("MISTRAL_API_KEY")
        st.session_state.mistral_api_key = key_input
        st.session_state.api_key = key_input

def render_sidebar():
    with st.sidebar:

        start_time = st.session_state.conversation_start_time
        st.caption(f"🕐 Sesión iniciada: {start_time.strftime('%H:%M:%S')}")
        st.caption("💡 Consejo: Usa 'reformula' para mejorar una respuesta")
        st.divider()

        if st.button("➕ Nueva conversación", use_container_width=True):
            create_new_conversation()
            st.rerun()

        with st.expander("📚 Historial"):
            view_conversation_history()

        st.divider()
        with st.expander("📤 Exportar"):
            if st.button("📥 Exportar actual", use_container_width=True):
                export_current_conversation()
            if st.button("📤 Exportar todas", use_container_width=True):
                export_all_conversations()

        with st.expander("📂 Importar"):
            uploaded_file = st.file_uploader(
                "Importar conversaciones",
                type=["json"],
                key="file_uploader"
            )
            if uploaded_file is not None:
                if st.button("📂 Importar", use_container_width=True):
                    import_conversations(uploaded_file)
                    st.rerun()

        with st.expander("📊 Estadísticas"):
            stats = st.session_state.db.get_stats()
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Conversaciones", stats["total_conversations"])
                st.metric("Mensajes", stats["total_messages"])
            with col2:
                st.metric("Truncados", stats["total_truncated"])
                st.metric("Con truncamiento", stats["conversations_with_truncation"])

        st.divider()

        with st.expander("API Key"):
            configure_api_key()

def add_copy_button(text: str, key: str):
    """Botón de copiar seguro que no rompe el frontend de React en Streamlit"""
    import base64
    import streamlit.components.v1 as components

    # 1. Codificamos a base64 asegurando el soporte UTF-8 (acentos, emojis, etc.)
    text_b64 = base64.b64encode(text.encode('utf-8')).decode('utf-8')

    # 2. Creamos un mini-documento HTML aislado. 
    # Al estar aislado, React no lo procesa y no puede fallar.
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: sans-serif;
            display: flex;
            justify-content: flex-end; /* Alinea el botón a la derecha */
            background-color: transparent;
        }}
        .copy-btn {{
            background: transparent;
            border: 1px solid #d3d4d6;
            color: #888;
            cursor: pointer;
            font-size: 13px;
            padding: 4px 10px;
            border-radius: 5px;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
        }}
        /* Efecto hover hecho con CSS puro en vez de JavaScript */
        .copy-btn:hover {{
            border-color: #FF4B4B;
            color: #FF4B4B;
        }}
        .feedback {{
            display: none;
            color: #28a745;
            font-size: 13px;
            margin-left: 8px;
            line-height: 26px;
            font-weight: bold;
        }}
    </style>
    </head>
    <body>
        <button class="copy-btn" id="btn" title="Copiar en formato Markdown">
            📋 Copiar MD
        </button>
        <span class="feedback" id="feedback">✅ ¡Copiado!</span>

        <script>
            document.getElementById('btn').addEventListener('click', function() {{
                
                // Decodificar Base64 de vuelta a texto respetando UTF-8
                const b64 = '{text_b64}';
                const bin = atob(b64);
                const bytes = new Uint8Array(bin.length);
                for(let i = 0; i < bin.length; i++) {{
                    bytes[i] = bin.charCodeAt(i);
                }}
                const decodedText = new TextDecoder('utf-8').decode(bytes);
                
                // Función segura para copiar incluso desde dentro de un Iframe
                const copyToClipboard = async () => {{
                    try {{
                        await navigator.clipboard.writeText(decodedText);
                        return true;
                    }} catch (err) {{
                        // Fallback de emergencia
                        const textarea = document.createElement('textarea');
                        textarea.value = decodedText;
                        textarea.style.position = 'fixed';
                        textarea.style.opacity = '0';
                        document.body.appendChild(textarea);
                        textarea.select();
                        try {{
                            document.execCommand('copy');
                            document.body.removeChild(textarea);
                            return true;
                        }} catch (e) {{
                            document.body.removeChild(textarea);
                            return false;
                        }}
                    }}
                }};

                copyToClipboard().then((success) => {{
                    if (success) {{
                        const f = document.getElementById('feedback');
                        f.style.display = 'inline-block';
                        setTimeout(() => f.style.display = 'none', 2000);
                    }}
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    # 3. Lo inyectamos como un componente nativo de HTML con una altura fija 
    # para que no genere barras de desplazamiento (scroll).
    components.html(html_code, height=35)

# ========== FUNCIÓN PRINCIPAL ==========

def main():
    st.set_page_config(
        page_title="💬 Multi-IA Chat",
        page_icon="💬",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    init_database()
    render_sidebar()

    # Información superior
    st.header(f"", divider="rainbow")

    # Acciones contextuales cerca del input
    with st.container():
        st.caption(f"Conversación #{st.session_state.current_conversation_id} | Mensajes: {len(st.session_state.messages)} | Reformulaciones: {st.session_state.total_reformulations} | Provider: {st.session_state.api_provider}")
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("🗑️ Limpiar"):
                clear_current_conversation()

    # Mostrar mensajes
    for idx, msg in enumerate(st.session_state.messages):  # Añadimos enumerate para el índice
        with st.chat_message(msg["role"]):
            # Verificar si el mensaje tiene archivos adjuntos
            if msg["role"] == "user" and "--- Contenido de '" in msg["content"]:
                # Separar el prompt del contenido de archivos
                parts = msg["content"].split("--- Contenido de '")
                prompt_part = parts[0].strip()
                st.markdown(prompt_part)

                # Mostrar cada archivo en un expander
                for part in parts[1:]:
                    if "' ---" in part:
                        filename = part.split("' ---")[0]
                        content: Any | Literal[''] = part.split("' ---")[1].strip() if "' ---" in part else ""
                        with st.expander(f"📄 {filename}"):
                            st.code(content, language="text")
            else:
                st.markdown(msg["content"])

            # AÑADIR AQUÍ: Botón de copiar SOLO para respuestas del asistente
            if msg["role"] == "assistant":
                # Usar un key determinista basado en current_conversation_id y idx
                msg_key = f"msg_{st.session_state.current_conversation_id}_{idx}"
                add_copy_button(msg["content"], msg_key)

            #
            if msg.get("truncated", False):
                st.caption("⚠️ *Mensaje truncado*")
            # Usamos (msg.get("reformulation_count") or 0) para evitar None
            if (msg.get("reformulation_count") or 0) > 0:
                st.caption(f"🔄 *Reformulado {msg['reformulation_count']} veces*")
                
    # Verificar API key
    if not st.session_state.api_key:
        st.warning(f"⚠️ Configura tu API Key de {st.session_state.api_provider} en el config.toml.")
        return

    # ====== SUBIDA DE ARCHIVOS ======
    # Usamos una key dinámica para resetear el uploader después de enviar
    uploaded_files = st.file_uploader(
        "📎 Adjuntar archivos (opcional)",
        accept_multiple_files=True,
        key=f"file_uploader_{st.session_state.uploader_key}",
        label_visibility="collapsed",
        help="Sube archivos de texto, PDF, DOCX, CSV, JSON, código, etc."
    )

    # Mostrar los archivos seleccionados (si hay)
    if uploaded_files:
        with st.container():
            st.caption(f"📎 Archivos adjuntos: {', '.join([f.name for f in uploaded_files])}")

    # ====== INPUT DEL USUARIO ======
    if prompt := st.chat_input("Escribe tu mensaje..."):
        # --- PROCESAR ARCHIVOS ---
        file_content = ""
        file_metadata = []

        if uploaded_files:
            for file in uploaded_files:
                text = extract_text_from_file(file)
                if text:
                    file_content += f"\n\n--- Contenido de '{file.name}' ---\n{text}\n"
                    file_metadata.append({
                        "name": file.name,
                        "size": file.size,
                        "content_preview": text[:200] + "..." if len(text) > 200 else text
                    })

            # Si no hay prompt, usamos solo el contenido del archivo
            if not prompt:
                final_prompt = f"Contenido de archivos adjuntos:\n{file_content}"
            else:
                final_prompt = f"{prompt}\n\n{file_content}"
        else:
            final_prompt = prompt

        # Guardar el mensaje original para detección de reformulación (sin contenido del archivo)
        original_prompt = prompt

        # Guardar parcial truncado si existía
        if st.session_state.partial_response:
            st.session_state.messages.append({
                "role": "assistant",
                "content": st.session_state.partial_response,
                "truncated": True,
                "interrupted_at": datetime.now().isoformat(),
                "reformulation_count": st.session_state.reformulation_count
            })
            st.session_state.db.save_message(
                st.session_state.current_conversation_id,
                st.session_state.messages[-1]
            )
            st.session_state.tokens_wasted += len(st.session_state.partial_response) // 4
            st.session_state.partial_response = ""

        # Mensaje de usuario (se guarda el contenido completo, incluyendo archivos)
        st.session_state.messages.append({"role": "user", "content": final_prompt})
        st.session_state.last_user_message = original_prompt  # Guardamos el original para referencia
        st.session_state.db.save_message(
            st.session_state.current_conversation_id,
            {"role": "user", "content": final_prompt}
        )

        with st.chat_message("user"):
            # Mostramos el prompt original + indicación de archivos si los hay
            if uploaded_files:
                st.markdown(original_prompt)
                # Mostrar archivos en expanders colapsables
                for file_info in file_metadata:
                    with st.expander(f"📄 {file_info['name']} ({file_info['size']} bytes)"):
                        st.code(file_info['content_preview'], language="text")
            else:
                st.markdown(original_prompt)

        # Generar respuesta
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""
            is_reformulation = detect_reformulation(original_prompt)  # Detectamos sobre el texto original

            if is_reformulation:
                st.session_state.reformulation_count += 1
                st.session_state.total_reformulations += 1
                st.caption(f"🔄 *Reformulación #{st.session_state.reformulation_count}*")

            # Construir contexto con el mensaje completo (incluyendo archivos)
            api_messages = build_context_with_reformulation_awareness(
                st.session_state.messages,
                is_reformulation,
                st.session_state.reformulation_count
            )

            try:
                # SELECCIONAMOS EL GENERADOR SEGÚN EL PROVEEDOR
                if st.session_state.api_provider == "DeepSeek":
                    stream_gen = stream_deepseek_completion(api_messages, st.session_state.api_key)
                elif st.session_state.api_provider == "Mistral AI":
                    stream_gen = stream_mistral_completion(api_messages, st.session_state.api_key)
                else:
                    stream_gen = stream_gemini_completion(api_messages, st.session_state.api_key)

                # Iteramos el generador
                for chunk in stream_gen:
                    if chunk:
                        full_response += chunk
                        st.session_state.partial_response = full_response
                        response_placeholder.markdown(full_response + "▌")

                response_placeholder.markdown(full_response)

                # Omitir el botón de copiar para la nueva respuesta
                #add_copy_button(full_response, f"new_response_{datetime.now().timestamp()}")  # ❌ Eliminado

                # Guardar el mensaje del asistente
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "truncated": False,
                    "reformulation_count": st.session_state.reformulation_count if is_reformulation else 0
                })
                st.session_state.db.save_message(
                    st.session_state.current_conversation_id,
                    st.session_state.messages[-1]
                )

                st.session_state.last_assistant_response = full_response
                st.session_state.partial_response = ""
                st.session_state.reformulation_count = 0

            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"⚠️ Error al generar respuesta: {str(e)}",
                    "truncated": False
                })

        # Incrementar la key del uploader para resetearlo
        st.session_state.uploader_key += 1
        update_sidebar_metrics()
        st.rerun()


# ========== CSS PERSONALIZADO ==========
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { max-width: 300px; }
    [data-testid="stMainMenu"] { display: none; }
    body{ line-height: 1; text-size-adjust: 80%; }
    .st-emotion-cache-liupih {
        width: 100%;
        padding: 2rem 0rem 1rem;
        max-width: initial;
        min-width: auto;
        z-index: 100;
    }
    @media (min-width: calc(736px + 8rem)) {
        .st-emotion-cache-liupih {
            padding-left: 2rem;
            padding-right: 2rem;
        }
    }
    .stAppToolbar, .stAppHeader { background-color: transparent; }

    /* Mejorar la visualización de archivos adjuntos */
    .stMain .stExpander {
        border-left: 3px solid #FF4B4B;
        border-radius: 5px;
    }

    /* Limitar altura de código en expanders */
    .stExpander .stCode {
        max-height: 300px;
        overflow-y: auto;
    }

    /* Mejorar el mensaje del usuario cuando tiene archivos */
    div[data-testid="stChatMessage"]:has(.stExpander) {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

if __name__ == "__main__":
    main()