"""SQLite-backed repository for chat sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

MessageRecord = dict[str, Any]


class ChatRepository:
    """Persist chat sessions, messages, and auxiliary events."""

    def __init__(self, database_path: Path):
        self._path = database_path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Open the SQLite connection and ensure tables exist."""

        if self._connection is not None:
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL;")
        await self._connection.execute("PRAGMA foreign_keys=ON;")
        await self._create_schema()

    async def _create_schema(self) -> None:
        assert self._connection is not None
        await self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                session_id TEXT PRIMARY KEY,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT,
                tool_call_id TEXT,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
                request_id TEXT,
                kind TEXT NOT NULL,
                payload TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def ensure_session(self, session_id: str) -> None:
        """Insert the session if it does not already exist."""

        assert self._connection is not None
        await self._connection.execute(
            "INSERT OR IGNORE INTO conversations(session_id) VALUES (?)",
            (session_id,),
        )
        await self._connection.commit()

    async def session_exists(self, session_id: str) -> bool:
        """Return True if the session is present in the database."""

        assert self._connection is not None
        cursor = await self._connection.execute(
            "SELECT 1 FROM conversations WHERE session_id = ? LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return row is not None

    async def clear_session(self, session_id: str) -> None:
        """Remove all messages and events for the given session."""

        assert self._connection is not None
        await self._connection.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        await self._connection.commit()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str | None,
        *,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Persist a single chat message."""

        assert self._connection is not None
        metadata_json = json.dumps(metadata) if metadata else None
        await self._connection.execute(
            """
            INSERT INTO messages(session_id, role, content, tool_call_id, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, role, content, tool_call_id, metadata_json),
        )
        await self._connection.commit()

    async def get_messages(self, session_id: str) -> list[MessageRecord]:
        """Return conversation messages ordered by insertion."""

        assert self._connection is not None
        cursor = await self._connection.execute(
            """
            SELECT role, content, tool_call_id, metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        messages: list[MessageRecord] = []
        for row in rows:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None
            message: MessageRecord = {
                "role": row["role"],
            }
            if row["content"] is not None:
                message["content"] = row["content"]
            if row["tool_call_id"]:
                message["tool_call_id"] = row["tool_call_id"]
            if metadata:
                message.update(metadata)
            messages.append(message)
        return messages

    async def add_event(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> None:
        """Persist auxiliary metadata for debugging or replay."""

        assert self._connection is not None
        await self._connection.execute(
            """
            INSERT INTO events(session_id, request_id, kind, payload)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, request_id, kind, json.dumps(payload)),
        )
        await self._connection.commit()


__all__ = ["ChatRepository"]
