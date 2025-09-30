"""SQLite-backed repository for chat sessions."""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Iterable

import aiosqlite

MessageRecord = dict[str, Any]
AttachmentRecord = dict[str, Any]

_CONTENT_JSON_METADATA_KEY = "__structured_content__"


def _encode_content(value: Any) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if isinstance(value, str):
        return value, False
    serialized = json.dumps(value)
    return serialized, True


def _decode_content(value: str | None, is_structured: bool) -> Any:
    if value is None:
        return None
    if is_structured:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


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
                client_message_id TEXT,
                parent_client_message_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS attachments (
                attachment_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES conversations(session_id) ON DELETE CASCADE,
                storage_path TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                display_url TEXT NOT NULL,
                delivery_url TEXT NOT NULL,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME,
                last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
        await self._ensure_column(
            "messages", "client_message_id", "TEXT"
        )
        await self._ensure_column(
            "messages", "parent_client_message_id", "TEXT"
        )

    async def _ensure_column(self, table: str, column: str, definition: str) -> None:
        """Ensure a column exists on a table, adding it if necessary."""

        assert self._connection is not None
        cursor = await self._connection.execute(f"PRAGMA table_info({table})")
        rows = await cursor.fetchall()
        await cursor.close()
        existing = {row[1] for row in rows}
        if column in existing:
            return
        await self._connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
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
        content: Any,
        *,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        client_message_id: str | None = None,
        parent_client_message_id: str | None = None,
    ) -> int:
        """Persist a single chat message."""

        assert self._connection is not None
        serialized_content, structured = _encode_content(content)

        stored_metadata: dict[str, Any] | None
        if metadata:
            stored_metadata = dict(metadata)
        else:
            stored_metadata = {}
        if structured:
            stored_metadata[_CONTENT_JSON_METADATA_KEY] = True
        metadata_json = json.dumps(stored_metadata) if stored_metadata else None
        cursor = await self._connection.execute(
            """
            INSERT INTO messages(
                session_id,
                role,
                content,
                tool_call_id,
                metadata,
                client_message_id,
                parent_client_message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                serialized_content,
                tool_call_id,
                metadata_json,
                client_message_id,
                parent_client_message_id,
            ),
        )
        await self._connection.commit()
        try:
            inserted_id = cursor.lastrowid
        finally:
            await cursor.close()
        return int(inserted_id)

    async def get_messages(self, session_id: str) -> list[MessageRecord]:
        """Return conversation messages ordered by insertion."""

        assert self._connection is not None
        cursor = await self._connection.execute(
            """
            SELECT
                id,
                role,
                content,
                tool_call_id,
                metadata,
                client_message_id,
                parent_client_message_id
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
            is_structured = False
            if metadata and metadata.pop(_CONTENT_JSON_METADATA_KEY, None):
                is_structured = True
            message: MessageRecord = {
                "role": row["role"],
            }
            message["message_id"] = row["id"]
            content = _decode_content(row["content"], is_structured)
            if content is not None:
                message["content"] = content
            if row["tool_call_id"]:
                message["tool_call_id"] = row["tool_call_id"]
            if metadata:
                message.update(metadata)
            client_message_id = row["client_message_id"]
            if client_message_id:
                message["client_message_id"] = client_message_id
            parent_client_message_id = row["parent_client_message_id"]
            if parent_client_message_id:
                message["parent_client_message_id"] = parent_client_message_id
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

    def _row_to_attachment(self, row: aiosqlite.Row) -> AttachmentRecord:
        record: AttachmentRecord = {
            "attachment_id": row["attachment_id"],
            "session_id": row["session_id"],
            "storage_path": row["storage_path"],
            "mime_type": row["mime_type"],
            "size_bytes": row["size_bytes"],
            "display_url": row["display_url"],
            "delivery_url": row["delivery_url"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "last_used_at": row["last_used_at"],
        }
        metadata = row["metadata"]
        record["metadata"] = json.loads(metadata) if metadata else None
        return record

    async def add_attachment(
        self,
        *,
        attachment_id: str,
        session_id: str,
        storage_path: str,
        mime_type: str,
        size_bytes: int,
        display_url: str,
        delivery_url: str,
        metadata: dict[str, Any] | None = None,
        expires_at: datetime | None = None,
    ) -> AttachmentRecord:
        """Persist an uploaded attachment and return the stored record."""

        assert self._connection is not None
        metadata_json = json.dumps(metadata) if metadata else None
        expires_value = (
            expires_at.isoformat(timespec="seconds") if isinstance(expires_at, datetime) else None
        )
        await self._connection.execute(
            """
            INSERT INTO attachments(
                attachment_id,
                session_id,
                storage_path,
                mime_type,
                size_bytes,
                display_url,
                delivery_url,
                metadata,
                expires_at,
                last_used_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                attachment_id,
                session_id,
                storage_path,
                mime_type,
                size_bytes,
                display_url,
                delivery_url,
                metadata_json,
                expires_value,
            ),
        )
        await self._connection.commit()
        record = await self.get_attachment(attachment_id)
        if record is None:  # pragma: no cover - defensive
            raise RuntimeError("Attachment failed to persist")
        return record

    async def get_attachment(self, attachment_id: str) -> AttachmentRecord | None:
        """Return a single attachment record, if present."""

        assert self._connection is not None
        cursor = await self._connection.execute(
            """
            SELECT
                attachment_id,
                session_id,
                storage_path,
                mime_type,
                size_bytes,
                display_url,
                delivery_url,
                metadata,
                created_at,
                expires_at,
                last_used_at
            FROM attachments
            WHERE attachment_id = ?
            LIMIT 1
            """,
            (attachment_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return self._row_to_attachment(row)

    async def touch_attachment(
        self, attachment_id: str, *, session_id: str | None = None
    ) -> bool:
        """Refresh the last-used timestamp for an attachment."""

        assert self._connection is not None
        if session_id:
            cursor = await self._connection.execute(
                """
                UPDATE attachments
                SET last_used_at = CURRENT_TIMESTAMP
                WHERE attachment_id = ? AND session_id = ?
                """,
                (attachment_id, session_id),
            )
        else:
            cursor = await self._connection.execute(
                """
                UPDATE attachments
                SET last_used_at = CURRENT_TIMESTAMP
                WHERE attachment_id = ?
                """,
                (attachment_id,),
            )
        updated = cursor.rowcount
        await cursor.close()
        await self._connection.commit()
        return bool(updated)

    async def delete_attachment(self, attachment_id: str) -> bool:
        """Remove an attachment record."""

        assert self._connection is not None
        cursor = await self._connection.execute(
            "DELETE FROM attachments WHERE attachment_id = ?",
            (attachment_id,),
        )
        deleted = cursor.rowcount
        await cursor.close()
        await self._connection.commit()
        return bool(deleted)

    async def mark_attachments_used(
        self, session_id: str, attachment_ids: Iterable[str]
    ) -> None:
        """Update usage timestamps for attachments tied to a chat turn."""

        if not attachment_ids:
            return

        assert self._connection is not None
        params = [(attachment_id, session_id) for attachment_id in attachment_ids]
        if params:
            await self._connection.executemany(
                """
                UPDATE attachments
                SET last_used_at = CURRENT_TIMESTAMP
                WHERE attachment_id = ? AND session_id = ?
                """,
                params,
            )
        await self._connection.commit()

    async def delete_message(
        self,
        session_id: str,
        client_message_id: str,
    ) -> int:
        """Delete a message (and related tool outputs) by client-supplied identifier."""

        assert self._connection is not None
        cursor = await self._connection.execute(
            """
            DELETE FROM messages
            WHERE session_id = ?
              AND (
                client_message_id = ?
                OR parent_client_message_id = ?
              )
            """,
            (session_id, client_message_id, client_message_id),
        )
        deleted = cursor.rowcount
        await cursor.close()
        await self._connection.commit()
        return deleted


__all__ = ["ChatRepository"]
