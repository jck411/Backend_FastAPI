from __future__ import annotations

import pytest

from src.backend.repository import ChatRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def repository(tmp_path):
    repo = ChatRepository(tmp_path / "chat.db")
    await repo.initialize()
    await repo.ensure_session("session-1")
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.anyio
async def test_structured_content_roundtrip(repository):
    payload = [{"type": "text", "text": "hello"}]
    metadata = {"foo": "bar"}

    await repository.add_message(
        "session-1",
        role="user",
        content=payload,
        metadata=dict(metadata),
    )

    messages = await repository.get_messages("session-1")

    assert len(messages) == 1
    message = messages[0]

    assert message["content"] == payload
    assert message["foo"] == "bar"
    assert metadata == {"foo": "bar"}


@pytest.mark.anyio
async def test_string_content_preserved(repository):
    await repository.add_message(
        "session-1",
        role="assistant",
        content="plain text",
    )

    messages = await repository.get_messages("session-1")

    assert messages[0]["content"] == "plain text"
