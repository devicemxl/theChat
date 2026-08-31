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
        self._migrate()

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

    # ========== MIGRACIONES ==========

    def _migrate(self):
        """Ejecuta las migraciones idempotentes en orden.

        Cada método de migración es independiente y hace su propio commit.
        Si una falla, las anteriores ya están aplicadas (no se revierte todo).
        """
        self._migrate_projects_table()
        self._migrate_conversations_project_column()
        self._migrate_rag_columns()
        self._migrate_pending_reindex_index()
        self._migrate_messages_parent_message_id()
        self._migrate_conversations_fork_columns()   # ← NUEVO

    def _migrate_projects_table(self):
        """Crea la tabla `projects` si no existe."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    name          TEXT NOT NULL UNIQUE,
                    description   TEXT,
                    system_prompt TEXT,
                    icon          TEXT DEFAULT '📁',
                    color         TEXT DEFAULT '#808080',
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def _migrate_conversations_project_column(self):
        """Añade `project_id` a conversations y su índice."""
        with sqlite3.connect(self.db_path) as conn:
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(conversations)")
            }
            if 'project_id' not in existing_cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN project_id INTEGER"
                )
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversations_project
                ON conversations(project_id)
            ''')
            conn.commit()

    def _migrate_rag_columns(self):
        """Añade columnas reservadas para el pipeline RAG."""
        with sqlite3.connect(self.db_path) as conn:
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(conversations)")
            }
            if 'indexed_at' not in existing_cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN indexed_at TIMESTAMP"
                )
            if 'pending_reindex' not in existing_cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN pending_reindex INTEGER DEFAULT 0"
                )
            conn.commit()

    def _migrate_pending_reindex_index(self):
        """Índice parcial para el futuro worker de reindexado."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversations_pending_reindex
                ON conversations(pending_reindex)
                WHERE pending_reindex = 1
            ''')
            conn.commit()
            
    def _migrate_messages_parent_message_id(self):
        """Añade `parent_message_id` a messages para cadenas de fork (Fase 1)."""
        with sqlite3.connect(self.db_path) as conn:
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(messages)")
            }
            if 'parent_message_id' not in existing_cols:
                conn.execute(
                    "ALTER TABLE messages ADD COLUMN parent_message_id INTEGER"
                )
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_messages_parent
                ON messages(parent_message_id)
            ''')
            conn.commit()

    def _migrate_conversations_fork_columns(self):
        """Añade `forked_from_conversation_id` y `fork_at_message_id` a conversations (Fase 1)."""
        with sqlite3.connect(self.db_path) as conn:
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(conversations)")
            }
            if 'forked_from_conversation_id' not in existing_cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN forked_from_conversation_id INTEGER"
                )
            if 'fork_at_message_id' not in existing_cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN fork_at_message_id INTEGER"
                )
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_conversations_forked_from
                ON conversations(forked_from_conversation_id)
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

    def delete_empty_conversations(self, exclude_ids: Optional[List[int]] = None) -> List[int]:
        """Elimina físicamente todas las conversaciones activas sin mensajes.

        Sigue el patrón SELECT → filtrar → iterar DELETE:
          1. Selecciona los IDs de conversaciones activas con 0 mensajes.
          2. Filtra los que estén en `exclude_ids` (la conversación actual, la que
             se está cargando, etc.) para no borrar por debajo del propio usuario.
          3. Itera y elimina uno a uno.

        A diferencia de `delete_conversation` (que hace soft-delete: is_active=0),
        aquí se hace HARD delete: no hay contenido que preservar en una conversación
        vacía, así que se elimina la fila para no acumular basura en la tabla.

        Args:
            exclude_ids: IDs que no deben borrarse aunque estén vacíos.

        Returns:
            Lista de IDs efectivamente eliminados (útil para logging/debug).
        """
        exclude = set(exclude_ids or [])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 1. SELECT: conversaciones activas sin ningún mensaje asociado.
            cursor.execute('''
                SELECT c.id
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.is_active = 1
                GROUP BY c.id
                HAVING COUNT(m.id) = 0
            ''')
            empty_ids = [row[0] for row in cursor.fetchall()]

            # 2. Filtrar los que el caller quiere proteger.
            to_delete = [cid for cid in empty_ids if cid not in exclude]

            # 3. Iterar y eliminar. Parametrizado — nunca interpolar el id en el SQL.
            for cid in to_delete:
                cursor.execute("DELETE FROM conversations WHERE id = ?", (cid,))

            conn.commit()
            return to_delete

    # ========== PROYECTOS ==========

    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        icon: str = '📁',
        color: str = '#808080'
    ) -> int:
        """Crea un proyecto y retorna su ID.

        Levanta sqlite3.IntegrityError si el nombre ya existe (UNIQUE).
        Levanta ValueError si el nombre está vacío.
        """
        if not name or not name.strip():
            raise ValueError("El nombre del proyecto no puede estar vacío")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO projects (name, description, system_prompt, icon, color)
                   VALUES (?, ?, ?, ?, ?)''',
                (name.strip(), description, system_prompt, icon, color)
            )
            conn.commit()
            return cursor.lastrowid

    def get_projects(self) -> List[Dict]:
        """Devuelve todos los proyectos con conteo de conversaciones asociadas.

        Ordenados alfabéticamente (case-insensitive).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*,
                       (SELECT COUNT(*) FROM conversations c 
                        WHERE c.project_id = p.id AND c.is_active = 1) as conversation_count
                FROM projects p
                ORDER BY p.name COLLATE NOCASE ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_project(self, project_id: int) -> Optional[Dict]:
        """Retorna un proyecto por ID, o None si no existe."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_project(self, project_id: int, **fields):
        """Actualiza campos del proyecto (sólo whitelist).

        Ejemplo: db.update_project(3, name='Nuevo', color='#ff0000')

        Campos permitidos: name, description, system_prompt, icon, color.
        Los desconocidos se ignoran silenciosamente.
        """
        allowed = {'name', 'description', 'system_prompt', 'icon', 'color'}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return

        if 'name' in updates and (not updates['name'] or not updates['name'].strip()):
            raise ValueError("El nombre del proyecto no puede estar vacío")
        if 'name' in updates:
            updates['name'] = updates['name'].strip()

        set_clause = ', '.join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [project_id]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE projects SET {set_clause} WHERE id = ?",
                values
            )
            conn.commit()

    def delete_project(self, project_id: int) -> int:
        """HARD delete del proyecto. Los chats asociados quedan sin proyecto (NULL).

        TODO(backup-zip): antes de borrar, exportar el proyecto y sus chats a
        un archivo .zip para poder recuperarlo. Formato pendiente de definir.

        Retorna el número de conversaciones que quedaron desasignadas.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 1. Contar y desasignar chats — jamás cascade delete de chats.
            cursor.execute(
                "SELECT COUNT(*) FROM conversations WHERE project_id = ?",
                (project_id,)
            )
            orphaned = cursor.fetchone()[0]

            cursor.execute(
                "UPDATE conversations SET project_id = NULL WHERE project_id = ?",
                (project_id,)
            )

            # 2. Borrar la fila del proyecto.
            cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))

            conn.commit()
            return orphaned

    def assign_conversation_to_project(
        self,
        conversation_id: int,
        project_id: Optional[int]
    ):
        """Asigna una conversación a un proyecto.

        project_id=None desasigna (queda en 'Sin proyecto').
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE conversations SET project_id = ? WHERE id = ?",
                (project_id, conversation_id)
            )
            conn.commit()

    def get_conversation_project(self, conversation_id: int) -> Optional[Dict]:
        """Retorna el proyecto asociado a la conversación, o None si no tiene.

        Un JOIN limpio en lugar de dos queries desde el caller.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.*
                FROM projects p
                INNER JOIN conversations c ON c.project_id = p.id
                WHERE c.id = ?
            ''', (conversation_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_conversations_grouped(self) -> List[Dict]:
        """Devuelve las conversaciones agrupadas por proyecto, listas para renderizar.

        Estructura:
            [
                {'project': {id, name, icon, color, ...}, 'conversations': [...]},
                ...
                {'project': None, 'conversations': [...]}  # 'Sin proyecto', al final
            ]

        Los proyectos van ordenados alfabéticamente; 'Sin proyecto' siempre al final.
        Dentro de cada grupo, las conversaciones van por updated_at DESC.
        """
        projects = self.get_projects()
        all_convs = self.get_conversations()

        # Indexar conversaciones por project_id
        by_project: Dict[Optional[int], List[Dict]] = {}
        for conv in all_convs:
            pid = conv.get('project_id')  # None si no asignada
            by_project.setdefault(pid, []).append(conv)

        result = []
        for project in projects:
            result.append({
                'project': project,
                'conversations': by_project.get(project['id'], [])
            })

        # Grupo 'Sin proyecto' — siempre al final, incluso si está vacío
        # (útil para mostrar la cabecera y que se vea "hay una sección aquí").
        result.append({
            'project': None,
            'conversations': by_project.get(None, [])
        })

        return result

    # ========== MENSAJES ==========

    def save_message(self, conversation_id: int, message: Dict) -> int:
        """Guarda un mensaje en la conversación. Retorna el id insertado."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages 
                (conversation_id, role, content, truncated, interrupted_at, reformulation_count, parent_message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                conversation_id,
                message.get("role", ""),
                message.get("content", ""),
                1 if message.get("truncated", False) else 0,
                message.get("interrupted_at"),
                message.get("reformulation_count"),
                message.get("parent_message_id")
            ))
            new_id = cursor.lastrowid          # ← capturar antes del UPDATE

            cursor.execute('''
                UPDATE conversations 
                SET message_count = message_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (conversation_id,))

            conn.commit()
            return new_id                       # ← devolver

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

    def get_messages_for_context(self, conversation_id: int) -> List[Dict]:
        """Devuelve los mensajes completos para una conversación, incluyendo
        la cadena de la madre si es una rama.

        - Si la conversación no es hija: solo sus mensajes.
        - Si es hija: mensajes de la madre hasta `fork_at_message_id` (inclusive)
        seguidos de los mensajes propios.
        """
        conv = self.get_conversation(conversation_id)
        if not conv:
            return []

        # Si no es rama, comportamiento idéntico a get_messages
        if not conv.get("forked_from_conversation_id") or not conv.get("fork_at_message_id"):
            return self.get_messages(conversation_id)

        mother_id = conv["forked_from_conversation_id"]
        fork_point = conv["fork_at_message_id"]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Mensajes de la madre hasta el punto de fork
            cursor.execute('''
                SELECT * FROM messages
                WHERE conversation_id = ? AND id <= ?
                ORDER BY id ASC
            ''', (mother_id, fork_point))
            mother_messages = [dict(row) for row in cursor.fetchall()]

            # Mensajes propios de la hija
            cursor.execute('''
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY id ASC
            ''', (conversation_id,))
            own_messages = [dict(row) for row in cursor.fetchall()]

        # Convertir truncated a bool (igual que get_messages)
        for msg in mother_messages + own_messages:
            msg["truncated"] = bool(msg["truncated"])
        return mother_messages + own_messages

    def create_fork(self, conversation_id: int, fork_at_message_id: int) -> int:
        """Crea una conversación hija que hereda contexto de la madre hasta el punto de fork.

        La hija se crea sin mensajes propios; hereda el proyecto y el título de la madre.
        Retorna el id de la nueva conversación.
        """
        conv = self.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"Conversación {conversation_id} no existe")

        new_id = self.create_conversation(conv["title"])

        if conv.get("project_id"):
            self.assign_conversation_to_project(new_id, conv["project_id"])

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE conversations SET forked_from_conversation_id = ?, fork_at_message_id = ? WHERE id = ?",
                (conversation_id, fork_at_message_id, new_id),
            )
            conn.commit()
        return new_id


    def delete_last_turn(self, conversation_id: int) -> bool:
        """Elimina el último turno (pregunta + respuesta) de una conversación.

        Solo aplica si los dos últimos mensajes son un par (user, assistant).
        Retorna True si se eliminó, False si no aplica.
        """
        with sqlite3.connect(self.db_path) as conn:
            # Obtener los dos últimos mensajes de la conversación
            rows = conn.execute(
                "SELECT id, role FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT 2",
                (conversation_id,),
            ).fetchall()

            if len(rows) < 2:
                return False

            # rows[0] es el más reciente
            if rows[0][1] != "assistant" or rows[1][1] != "user":
                return False

            ids_to_delete = [rows[0][0], rows[1][0]]

            cursor = conn.execute(
                "DELETE FROM messages WHERE id IN (?, ?)",
                ids_to_delete,
            )
            deleted = cursor.rowcount

            conn.execute(
                "UPDATE conversations SET message_count = MAX(0, message_count - ?) WHERE id = ?",
                (deleted, conversation_id),
            )
            conn.commit()

            return deleted == 2
        
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