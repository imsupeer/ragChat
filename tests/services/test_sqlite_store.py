import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from backend.services.sqlite_store import SQLiteStore, SQLITE_BUSY_TIMEOUT_MS


def test_sqlite_store_accepts_plain_filename_database_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    store = SQLiteStore("app.db")
    chat = store.create_chat()

    assert chat["title"] == "New Chat"
    assert (tmp_path / "app.db").exists()


def test_sqlite_store_enforces_message_chat_foreign_key(tmp_path):
    store = SQLiteStore(str(tmp_path / "app.db"))

    with pytest.raises(sqlite3.IntegrityError):
        store.add_message(
            chat_id="missing-chat",
            role="user",
            content="This should not be stored.",
        )


def test_sqlite_store_migrates_debug_json_column(tmp_path):
    db_path = tmp_path / "legacy.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE chats (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE messages (
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
    conn.execute("INSERT INTO chats (id, title) VALUES ('chat-1', 'Legacy Chat')")
    conn.execute(
        """
        INSERT INTO messages (id, chat_id, role, content, sources_json)
        VALUES ('msg-1', 'chat-1', 'user', 'Hello', '[]')
        """
    )
    conn.commit()
    conn.close()

    store = SQLiteStore(str(db_path))
    messages = store.list_messages("chat-1")

    assert len(messages) == 1
    assert messages[0]["content"] == "Hello"
    assert "debug" not in messages[0] or messages[0]["debug"] is None

    with sqlite3.connect(db_path) as migrated:
        columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(messages)").fetchall()
        }
    assert "debug_json" in columns


def test_sqlite_store_saves_and_loads_assistant_debug_metadata(tmp_path):
    store = SQLiteStore(str(tmp_path / "app.db"))
    chat = store.create_chat()
    debug = {
        "trace_id": "trace-123",
        "retrieval": {"latency_ms": 12.0, "retrieved_count": 2, "used_count": 1, "results": []},
        "prompt": {"used_chunk_count": 1, "used_chunk_ids": ["chunk-1"], "used_chunks": []},
    }

    store.add_message(
        chat_id=chat["id"],
        role="assistant",
        content="Answer",
        sources=[{"chunk_id": "chunk-1"}],
        debug=debug,
    )

    messages = store.list_messages(chat["id"])
    assert len(messages) == 1
    assert messages[0]["debug"]["trace_id"] == "trace-123"
    assert messages[0]["debug"]["prompt"]["used_chunk_ids"] == ["chunk-1"]


def test_sqlite_store_ignores_invalid_debug_json(tmp_path):
    db_path = tmp_path / "app.db"
    store = SQLiteStore(str(db_path))
    chat = store.create_chat()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO messages (id, chat_id, role, content, sources_json, debug_json)
            VALUES ('msg-bad', ?, 'assistant', 'Answer', '[]', '{not-json')
            """,
            (chat["id"],),
        )
        conn.commit()

    messages = store.list_messages(chat["id"])
    assert messages[0]["debug"] is None


def test_sqlite_store_applies_busy_timeout_and_wal_pragmas(tmp_path):
    store = SQLiteStore(str(tmp_path / "app.db"))

    with closing(store._connect()) as conn:
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert busy_timeout == SQLITE_BUSY_TIMEOUT_MS
    assert journal_mode.lower() == "wal"


def test_sqlite_store_creates_hot_path_indexes(tmp_path):
    store = SQLiteStore(str(tmp_path / "app.db"))

    with sqlite3.connect(store.db_path) as conn:
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'index' AND name LIKE 'idx_%'
            """
        ).fetchall()

    index_names = {row[0] for row in rows}
    assert "idx_messages_chat_id_created_at" in index_names
    assert "idx_upload_jobs_status_created_at" in index_names
    assert "idx_upload_jobs_document_id" in index_names


def test_sqlite_store_clears_upload_job_document_reference(tmp_path):
    store = SQLiteStore(str(tmp_path / "app.db"))
    job = store.create_upload_job("sample.txt", 10, str(tmp_path / "sample.txt"))
    store.update_upload_job(job["id"], status="completed", document_id="doc-1")

    cleared = store.clear_upload_job_document_reference("doc-1")

    assert cleared == 1
    updated = store.get_upload_job(job["id"])
    assert updated["document_id"] is None


def test_sqlite_store_clears_upload_job_document_reference_for_job(tmp_path):
    store = SQLiteStore(str(tmp_path / "app.db"))
    job = store.create_upload_job("sample.txt", 10, str(tmp_path / "sample.txt"))
    store.update_upload_job(job["id"], status="completed", document_id="doc-1")

    cleared = store.clear_upload_job_document_reference_for_job(
        job["id"],
        expected_document_id="doc-1",
    )

    assert cleared is True
    updated = store.get_upload_job(job["id"])
    assert updated["document_id"] is None

    cleared_again = store.clear_upload_job_document_reference_for_job(
        job["id"],
        expected_document_id="doc-1",
    )
    assert cleared_again is False


def test_sqlite_store_mark_upload_job_failed_safe(tmp_path):
    store = SQLiteStore(str(tmp_path / "app.db"))
    job = store.create_upload_job("sample.txt", 10, str(tmp_path / "sample.txt"))
    message = "Source file is missing. Please re-upload the document."

    applied = store.mark_upload_job_failed_safe(job["id"], error_message=message)

    assert applied is True
    updated = store.get_upload_job(job["id"])
    assert updated["status"] == "failed"
    assert updated["error"] == message

    applied_again = store.mark_upload_job_failed_safe(job["id"], error_message=message)
    assert applied_again is False
