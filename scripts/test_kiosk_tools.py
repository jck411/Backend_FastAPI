import asyncio
import logging
import json
import uuid
from typing import Any
from unittest.mock import MagicMock, AsyncMock

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_kiosk_tools")
print("DEBUG: imports starting")

# Mock OpenRouter Client and Settings
try:
    from backend.services.kiosk_chat_service import KioskChatService
    from backend.chat.mcp_registry import MCPToolAggregator
    from backend.schemas.kiosk_llm_settings import KioskLlmSettings
    from backend.services.kiosk_llm_settings import KioskLlmSettingsService
    print("DEBUG: imports success")
except Exception as e:
    print(f"DEBUG: imports failed: {e}")
    exit(1)

# Start a dummy MCP server (calculator)
# For this test, we might struggle to actually spin up a full MCP server process easily
# without external dependencies or path issues.
# instead, we can mock the mcp_client's behavior to simulate tool execution return.

async def run_test():
    # 1. Mock Settings
    mock_settings_service = MagicMock(spec=KioskLlmSettingsService)
    mock_settings = KioskLlmSettings(
        system_prompt="You are a helpful assistant with tools.",
        model="test-model"
    )
    mock_settings_service.get_settings.return_value = mock_settings

    # 2. Mock OpenRouter Client
    mock_or_client = MagicMock()
    mock_or_client._settings = MagicMock()
    mock_or_client._settings.openrouter_api_key.get_secret_value.return_value = "fake-key"
    mock_or_client._settings.openrouter_base_url = "http://mock-openrouter"

    # 3. Mock MCP Client
    # We want to verified that call_tool is CALLED. We don't need real MCP execution if we trust MCPToolAggregator works.
    # But we want to test the KioskChatService LOOP.

    mock_mcp_client = AsyncMock(spec=MCPToolAggregator)

    # Setup tools
    mock_mcp_client.get_openai_tools.return_value = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Calculate a math expression",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string"}
                    }
                }
            }
        }
    ]

    mock_mcp_client.format_tool_result.return_value = "Result: 42"
    mock_mcp_client.call_tool.return_value = "42"

    # 4. Initialize Service
    # We need to patch get_kiosk_llm_settings_service to return our mock
    import backend.services.kiosk_chat_service as service_module
    service_module.get_kiosk_llm_settings_service = lambda: mock_settings_service

    service = KioskChatService(mock_or_client, mock_mcp_client)

    # 5. Mock HTTPX Stream
    # We need to simulate the OpenRouter stream:
    # 1. Tool Call Chunk
    # 2. Tool Result (Simulated by loop) -> LLM is called again
    # 3. Final Answer Chunk

    # Since we can't easily mock `httpx.AsyncClient` context manager behavior with side effects recursively
    # (because the service creates a NEW client each loop), we have to be clever.
    # We can mock `httpx.AsyncClient` to return a mock client that yields different streams based on call count.

    import httpx

    original_client_cls = httpx.AsyncClient

    call_count = 0

    class MockStream:
        def __init__(self, chunks):
            self.chunks = chunks
            self.status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def aiter_lines(self):
            for chunk in self.chunks:
                yield f"data: {json.dumps(chunk)}"
            yield "data: [DONE]"

    class MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def stream(self, method, url, **kwargs):
            nonlocal call_count
            payload = kwargs.get("json", {})
            msgs = payload.get("messages", [])
            logger.info(f"LLM Call #{call_count+1}. Messages: {len(msgs)}")

            # Check if this is the first call (user input)
            if call_count == 0:
                call_count += 1
                # Return tool call
                return MockStream([
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_123",
                                            "type": "function",
                                            "function": {
                                                "name": "calculate",
                                                "arguments": '{"expression": "40 + 2"}'
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ])
            else:
                # Second call (after tool result)
                # Verify that the last message is a TOOL role
                last_msg = msgs[-1]
                logger.info(f"Last message role: {last_msg.get('role')}")
                if last_msg.get("role") != "tool":
                    logger.error("Expected last message to be tool result!")

                return MockStream([
                     {
                        "choices": [
                            {
                                "delta": {
                                    "content": "The answer is 42."
                                }
                            }
                        ]
                    }
                ])

    # Patch httpx
    httpx.AsyncClient = MockHttpxClient

    # Run user query
    response = await service.generate_response("What is 40 plus 2?")

    print(f"\nFinal Response: {response}")

    # Assertions
    assert "The answer is 42" in response
    assert call_count == 1  # 0-indexed incremented to 1 means it ran once? No, incremented to 2 means ran twice.
    # ACTUALLY call_count started at 0.
    # Call 1: call_count -> 1. Returns tool.
    # Service loops. Executes tool.
    # Call 2: call_count -> 2. Returns answer.
    # Service loops. NO tool. Breaks.
    # So call_count should be 2?

    # Let's check history
    print("\nHistory:")
    for msg in service._histories["default"]:
        print(f"{msg.get('role')}: {msg.get('content') or msg.get('tool_calls')}")

    # Verify tool execution
    mock_mcp_client.call_tool.assert_awaited_with("calculate", {"expression": "40 + 2"})
    with open("verification_result.txt", "w") as f:
        f.write("Verification passed!\n")
        f.write(f"Response: {response}\n")
    print("\n✅ Verification passed!")

if __name__ == "__main__":
    try:
        asyncio.run(run_test())
    except Exception as e:
        with open("verification_result.txt", "w") as f:
            f.write(f"Verification failed: {e}\n")
        raise
