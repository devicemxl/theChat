import json
import streamlit as st
from datetime import datetime
from typing import Dict

def export_current_conversation():
    """Exporta la conversación actual a un archivo JSON."""
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
        label="📥 Descargar JSON de esta conversación",
        data=json_str,
        file_name=f"conversacion_{st.session_state.current_conversation_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )

def export_all_conversations():
    """Exporta todo el historial de conversaciones de la base de datos a un archivo JSON."""
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
        label="📥 Descargar historial completo",
        data=json_str,
        file_name=f"todas_conversaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )

def import_conversations(uploaded_file):
    """Procesa un archivo JSON subido para importar una o varias conversaciones."""
    try:
        data = json.loads(uploaded_file.getvalue().decode("utf-8"))
        
        if isinstance(data, list):
            for conv_data in data:
                import_single_conversation(conv_data)
        elif isinstance(data, dict):
            import_single_conversation(data)
            
        st.success(f"✅ Importadas {len(data) if isinstance(data, list) else 1} conversaciones exitosamente.")
    except Exception as e:
        st.error(f"❌ Error al importar el archivo: {str(e)}")

def import_single_conversation(conv_data: Dict):
    """Inserta una única conversación y sus mensajes en la base de datos."""
    db = st.session_state.db
    title = conv_data.get("title", f"Importada {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Crear la nueva conversación
    conv_id = db.create_conversation(title)
    
    # Insertar los mensajes uno por uno
    for msg in conv_data.get("messages", []):
        # Asegurar que reformulation_count sea entero (por compatibilidad con exportaciones viejas)
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