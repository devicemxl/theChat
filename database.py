import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional
import streamlit as st

class ChatDatabase:
    """Gestor de base de datos SQLite para conversaciones"""

    def __init__(self, db_path: str = "chat_history.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Inicializa la base de datos y crea las tablas necesarias"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Tabla de conversaciones
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1
                )
            ''')

            # Tabla de mensajes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    truncated INTEGER DEFAULT 0,
                    interrupted_at TEXT,
                    reformulation_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id)
                )
            ''')

            # Índices para búsqueda rápida
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_conversation 
                ON messages(conversation_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversations_updated 
                ON conversations(updated_at DESC)
            ''')

            conn.commit()

    # ========== CONVERSACIONES ==========

    def create_conversation(self, title: str = "Nueva conversación") -> int:
        """Crea una nueva conversación y retorna su ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversations (title) VALUES (?)",
                (title,)
            )
            conn.commit()
            return cursor.lastrowid

    def get_conversations(self, limit: int = 50) -> List[Dict]:
        """Obtiene las conversaciones más recientes"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.*, 
                       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as msg_count,
                       (SELECT content FROM messages m WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1) as last_message
                FROM conversations c
                WHERE c.is_active = 1
                ORDER BY c.updated_at DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_conversation(self, conversation_id: int) -> Optional[Dict]:
        """Obtiene una conversación específica"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM conversations WHERE id = ? AND is_active = 1",
                (conversation_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_conversation_title(self, conversation_id: int, title: str):
        """Actualiza el título de una conversación"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, conversation_id)
            )
            conn.commit()

    def delete_conversation(self, conversation_id: int):
        """Elimina lógicamente una conversación"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE conversations SET is_active = 0 WHERE id = ?",
                (conversation_id,)
            )
            conn.commit()

    # ========== MENSAJES ==========

    def save_message(self, conversation_id: int, message: Dict):
        """Guarda un mensaje en la conversación"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages 
                (conversation_id, role, content, truncated, interrupted_at, reformulation_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                conversation_id,
                message.get("role", ""),
                message.get("content", ""),
                1 if message.get("truncated", False) else 0,
                message.get("interrupted_at"),
                message.get("reformulation_count")
            ))

            # Actualizar contador y timestamp de la conversación
            cursor.execute('''
                UPDATE conversations 
                SET message_count = message_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (conversation_id,))

            conn.commit()

    def get_messages(self, conversation_id: int) -> List[Dict]:
        """Obtiene todos los mensajes de una conversación"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM messages 
                WHERE conversation_id = ?
                ORDER BY id ASC
            ''', (conversation_id,))

            messages = []
            for row in cursor.fetchall():
                msg = dict(row)
                # Convertir campos a formato compatible
                msg["truncated"] = bool(msg["truncated"])
                messages.append(msg)

            return messages

    def delete_messages(self, conversation_id: int):
        """Elimina todos los mensajes de una conversación"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )
            conn.commit()

    # ========== BÚSQUEDA ==========

    def search_messages(self, query: str, limit: int = 20) -> List[Dict]:
        """Busca mensajes que contengan el texto especificado"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT m.*, c.title as conversation_title
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE m.content LIKE ? AND c.is_active = 1
                ORDER BY m.created_at DESC
                LIMIT ?
            ''', (f"%{query}%", limit))
            return [dict(row) for row in cursor.fetchall()]

    # ========== ESTADÍSTICAS ==========

    def get_stats(self) -> Dict:
        """Obtiene estadísticas generales"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as total FROM conversations WHERE is_active = 1")
            total_conversations = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) as total FROM messages")
            total_messages = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) as total FROM messages WHERE truncated = 1")
            total_truncated = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(DISTINCT conversation_id) as total FROM messages WHERE truncated = 1")
            conversations_with_truncation = cursor.fetchone()["total"]

            return {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "total_truncated": total_truncated,
                "conversations_with_truncation": conversations_with_truncation
            }