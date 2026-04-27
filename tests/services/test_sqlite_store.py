import sqlite3

import pytest

from backend.services.sqlite_store import SQLiteStore


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
