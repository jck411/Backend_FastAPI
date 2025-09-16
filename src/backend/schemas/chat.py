"""Pydantic models for chat requests and responses."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """Represents a single chat message."""

    role: Literal["system", "user", "assistant", "tool"]
    content: Any
    name: Optional[str] = None
    tool_call_id: Optional[str] = Field(default=None, alias="tool_call_id")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ChatCompletionRequest(BaseModel):
    """Incoming chat completion request payload."""

    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    parallel_tool_calls: Optional[bool] = None
    response_format: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    provider: Optional[Dict[str, Any]] = None
    stream_options: Optional[Dict[str, Any]] = None
    user: Optional[str] = None
    stop: Optional[Union[str, List[str]]] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    def to_openrouter_payload(self, default_model: str) -> Dict[str, Any]:
        """Serialize the request for OpenRouter, enforcing defaults."""

        payload = self.model_dump(by_alias=True, exclude_none=True)
        payload.setdefault("model", default_model)
        payload["stream"] = True
        return payload


__all__ = ["ChatMessage", "ChatCompletionRequest"]
