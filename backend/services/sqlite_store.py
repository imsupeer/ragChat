import json
import os
import sqlite3
import uuid
from contextlib import closing
from typing import Any, Optional


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_db(self) -> None:
        directory = os.path.dirname(self.db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS upload_jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    stored_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    upload_progress INTEGER NOT NULL DEFAULT 0,
                    index_progress INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    document_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.commit()

    def list_chats(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, title, created_at FROM chats ORDER BY created_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def create_chat(self, title: Optional[str] = None) -> dict[str, Any]:
        chat_id = str(uuid.uuid4())
        title = title or "New Chat"

        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO chats (id, title) VALUES (?, ?)",
                (chat_id, title),
            )
            conn.commit()

        return self.get_chat(chat_id)

    def get_chat(self, chat_id: str) -> Optional[dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT id, title, created_at FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_chat_title(self, chat_id: str, title: str) -> Optional[dict[str, Any]]:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE chats SET title = ? WHERE id = ?",
                (title, chat_id),
            )
            conn.commit()

        return self.get_chat(chat_id)

    def delete_chat(self, chat_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            conn.commit()

    def list_messages(self, chat_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, chat_id, role, content, sources_json, created_at
                FROM messages
                WHERE chat_id = ?
                ORDER BY created_at ASC
            """,
                (chat_id,),
            ).fetchall()

            result = []
            for row in rows:
                item = dict(row)
                item["sources"] = (
                    json.loads(item["sources_json"]) if item["sources_json"] else []
                )
                item.pop("sources_json", None)
                result.append(item)

            return result

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        sources: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        message_id = str(uuid.uuid4())
        sources_json = json.dumps(sources or [], ensure_ascii=False)

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO messages (id, chat_id, role, content, sources_json)
                VALUES (?, ?, ?, ?, ?)
            """,
                (message_id, chat_id, role, content, sources_json),
            )
            conn.commit()

        return {
            "id": message_id,
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "sources": sources or [],
        }

    def create_upload_job(
        self,
        filename: str,
        file_size: int,
        stored_path: str,
    ) -> dict[str, Any]:
        job_id = str(uuid.uuid4())

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO upload_jobs (
                    id, filename, file_size, stored_path, status, upload_progress, index_progress
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (job_id, filename, file_size, stored_path, "queued", 100, 0),
            )
            conn.commit()

        return self.get_upload_job(job_id)

    def list_upload_jobs(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, filename, file_size, stored_path, status, upload_progress,
                       index_progress, error, document_id, created_at
                FROM upload_jobs
                ORDER BY created_at DESC
            """
            ).fetchall()
            return [dict(row) for row in rows]

    def get_upload_job(self, job_id: str) -> Optional[dict[str, Any]]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT id, filename, file_size, stored_path, status, upload_progress,
                       index_progress, error, document_id, created_at
                FROM upload_jobs
                WHERE id = ?
            """,
                (job_id,),
            ).fetchone()
            return dict(row) if row else None

    def update_upload_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        upload_progress: Optional[int] = None,
        index_progress: Optional[int] = None,
        error: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> None:
        fields = []
        values = []

        if status is not None:
            fields.append("status = ?")
            values.append(status)

        if upload_progress is not None:
            fields.append("upload_progress = ?")
            values.append(upload_progress)

        if index_progress is not None:
            fields.append("index_progress = ?")
            values.append(index_progress)

        if error is not None:
            fields.append("error = ?")
            values.append(error)

        if document_id is not None:
            fields.append("document_id = ?")
            values.append(document_id)

        if not fields:
            return

        values.append(job_id)

        with closing(self._connect()) as conn:
            conn.execute(
                f"UPDATE upload_jobs SET {', '.join(fields)} WHERE id = ?",
                tuple(values),
            )
            conn.commit()
