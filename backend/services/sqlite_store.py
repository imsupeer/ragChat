import json
import os
import sqlite3
import uuid
import logging
from contextlib import closing
from typing import Any, Optional

logger = logging.getLogger("uvicorn.error")

SQLITE_BUSY_TIMEOUT_MS = 5000


class SQLiteStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._apply_connection_pragmas(conn)
        return conn

    @staticmethod
    def _apply_connection_pragmas(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")

        try:
            journal_mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
            if journal_mode and journal_mode[0].lower() != "wal":
                logger.warning(
                    "SQLite journal_mode is %s instead of wal",
                    journal_mode[0],
                )
        except sqlite3.Error as exc:
            logger.warning("Failed to enable SQLite WAL mode: %s", exc)

        try:
            conn.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error as exc:
            logger.warning("Failed to set SQLite synchronous=NORMAL: %s", exc)

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
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "debug_json" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN debug_json TEXT")
            conn.commit()

        self._ensure_indexes(conn)

    def _ensure_indexes(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id_created_at
            ON messages(chat_id, created_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_upload_jobs_status_created_at
            ON upload_jobs(status, created_at)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_upload_jobs_document_id
            ON upload_jobs(document_id)
            """
        )
        conn.commit()

    @staticmethod
    def _serialize_debug(debug: Optional[dict[str, Any]]) -> Optional[str]:
        if not debug:
            return None

        try:
            return json.dumps(debug, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to serialize debug metadata: %s", exc)
            return None

    @staticmethod
    def _parse_debug(debug_json: Optional[str]) -> Optional[dict[str, Any]]:
        if not debug_json:
            return None

        try:
            parsed = json.loads(debug_json)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse debug metadata: %s", exc)
            return None

        return parsed if isinstance(parsed, dict) else None

    def ping(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("SELECT 1")

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
                SELECT id, chat_id, role, content, sources_json, debug_json, created_at
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
                item["debug"] = self._parse_debug(item.pop("debug_json", None))
                item.pop("sources_json", None)
                result.append(item)

            return result

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        sources: Optional[list[dict[str, Any]]] = None,
        debug: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        message_id = str(uuid.uuid4())
        sources_json = json.dumps(sources or [], ensure_ascii=False)
        debug_json = self._serialize_debug(debug)

        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO messages (id, chat_id, role, content, sources_json, debug_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (message_id, chat_id, role, content, sources_json, debug_json),
            )
            conn.commit()

        message = {
            "id": message_id,
            "chat_id": chat_id,
            "role": role,
            "content": content,
            "sources": sources or [],
        }
        if debug_json is not None:
            message["debug"] = debug
        return message

    def delete_last_assistant_message(self, chat_id: str) -> None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT id FROM messages
                WHERE chat_id = ? AND role = 'assistant'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()

            if row:
                conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
                conn.commit()

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

    def list_pending_upload_jobs(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, filename, file_size, stored_path, status, upload_progress,
                       index_progress, error, document_id, created_at
                FROM upload_jobs
                WHERE status IN ('queued', 'processing')
                ORDER BY created_at ASC
            """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_upload_jobs_with_document_id(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, filename, file_size, stored_path, status, upload_progress,
                       index_progress, error, document_id, created_at
                FROM upload_jobs
                WHERE document_id IS NOT NULL
                ORDER BY created_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def list_recoverable_upload_jobs(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, filename, file_size, stored_path, status, upload_progress,
                       index_progress, error, document_id, created_at
                FROM upload_jobs
                WHERE status IN ('queued', 'processing', 'failed')
                ORDER BY created_at ASC
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

    def clear_upload_job_document_reference_for_job(
        self,
        job_id: str,
        *,
        expected_document_id: str | None = None,
    ) -> bool:
        job = self.get_upload_job(job_id)
        if job is None or job.get("document_id") is None:
            return False
        if expected_document_id is not None and job["document_id"] != expected_document_id:
            return False

        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE upload_jobs
                SET document_id = NULL
                WHERE id = ? AND document_id IS NOT NULL
                """,
                (job_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_upload_job_failed_safe(
        self,
        job_id: str,
        *,
        error_message: str,
    ) -> bool:
        job = self.get_upload_job(job_id)
        if job is None:
            return False
        if job.get("status") == "failed" and (job.get("error") or "") == error_message:
            return False

        self.update_upload_job(
            job_id,
            status="failed",
            error=error_message,
            index_progress=0,
        )
        return True

    def clear_upload_job_document_reference(self, document_id: str) -> int:
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE upload_jobs
                SET document_id = NULL
                WHERE document_id = ?
                """,
                (document_id,),
            )
            conn.commit()
            return cursor.rowcount
