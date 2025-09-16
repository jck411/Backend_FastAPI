"""Chat streaming API routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from ..config import Settings, get_settings
from ..openrouter import OpenRouterClient, OpenRouterError
from ..schemas.chat import ChatCompletionRequest

router = APIRouter(prefix="/api", tags=["chat"])


def get_openrouter_client(
    settings: Settings = Depends(get_settings),
) -> OpenRouterClient:
    return OpenRouterClient(settings)


@router.post("/chat/stream", response_model=None, status_code=200)
async def stream_chat_completions(
    payload: ChatCompletionRequest,
    client: OpenRouterClient = Depends(get_openrouter_client),
) -> EventSourceResponse:
    """Stream chat completions from OpenRouter through Server-Sent Events."""

    async def event_publisher():
        try:
            async for event in client.stream_chat(payload):
                yield event
        except OpenRouterError as exc:
            detail = (
                exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
            )
            error_chunk = {"choices": [{"delta": {"content": f"Error: {detail}"}}]}
            yield {"event": "message", "data": json.dumps(error_chunk)}
            yield {"event": "message", "data": "[DONE]"}
        except Exception as exc:  # pragma: no cover
            error_chunk = {"choices": [{"delta": {"content": f"Error: {str(exc)}"}}]}
            yield {"event": "message", "data": json.dumps(error_chunk)}
            yield {"event": "message", "data": "[DONE]"}

    return EventSourceResponse(event_publisher())


@router.get("/chat/test-stream", response_model=None, status_code=200)
async def test_stream() -> EventSourceResponse:
    """Emit a short fake SSE chat stream for debugging the frontend."""

    async def generator():
        parts = ["Hello ", "from ", "server!"]
        for part in parts:
            chunk = {"choices": [{"delta": {"content": part}}]}
            yield {"event": "message", "data": json.dumps(chunk)}
            await asyncio.sleep(0.2)
        yield {"event": "message", "data": "[DONE]"}

    return EventSourceResponse(generator())


@router.get("/models", status_code=200)
async def list_models(
    client: OpenRouterClient = Depends(get_openrouter_client),
) -> dict[str, Any]:
    """Expose the available OpenRouter models to the frontend."""

    try:
        return await client.list_models()
    except OpenRouterError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


__all__ = ["router"]
