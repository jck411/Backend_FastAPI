# How Tool Schemas Are Auto-Generated from Python Functions

## The Complete Flow

### 1. You Write a Python Function

```python
# In src/backend/mcp_servers/calendar_server.py
from mcp.server.fastmcp import FastMCP

DEFAULT_USER_EMAIL = "jck411@gmail.com"
mcp: FastMCP = FastMCP("custom-calendar")

@mcp.tool("calendar_get_events")
async def get_events(
    user_email: str = DEFAULT_USER_EMAIL,  # ← FastMCP reads this default
    calendar_id: Optional[str] = None,     # ← FastMCP sees Optional[str]
    time_min: Optional[str] = None,        # ← FastMCP sees Optional[str]
    time_max: Optional[str] = None,        # ← FastMCP sees Optional[str]
    max_results: int = 25,                 # ← FastMCP sees int with default
    query: Optional[str] = None,           # ← FastMCP sees Optional[str]
    detailed: bool = False,                # ← FastMCP sees bool with default
) -> str:                                  # ← Return type
    """Retrieve calendar events. Omit calendar_id to search all household calendars..."""
    # function body...
```

---

### 2. FastMCP Introspects the Function

When you use `@mcp.tool()`, FastMCP automatically:

1. **Reads the function signature** using Python's `inspect` module
2. **Extracts type hints** (`str`, `Optional[str]`, `int`, `bool`)
3. **Captures default values** (`= DEFAULT_USER_EMAIL`, `= None`, `= 25`, `= False`)
4. **Parses the docstring** for the description
5. **Generates JSON Schema** following OpenAPI/JSON Schema spec

---

### 3. FastMCP Generates the MCP Protocol Schema

```python
# This happens automatically inside FastMCP
{
  "name": "calendar_get_events",
  "description": "Retrieve calendar events. Omit calendar_id...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "user_email": {
        "type": "string",
        "title": "User Email",
        "default": "jck411@gmail.com"  # ← From DEFAULT_USER_EMAIL
      },
      "calendar_id": {
        "anyOf": [{"type": "string"}, {"type": "null"}],  # ← From Optional[str]
        "title": "Calendar Id",
        "default": null  # ← From = None
      },
      "time_min": {
        "anyOf": [{"type": "string"}, {"type": "null"}],  # ← From Optional[str]
        "title": "Time Min",
        "default": null  # ← From = None
      },
      "max_results": {
        "type": "integer",  # ← From int
        "title": "Max Results",
        "default": 25  # ← From = 25
      },
      "detailed": {
        "type": "boolean",  # ← From bool
        "title": "Detailed",
        "default": false  # ← From = False
      }
    }
  }
}
```

---

### 4. Your Backend Transforms It for OpenAI/OpenRouter

```python
# In src/backend/chat/mcp_client.py
def get_openai_tools(self) -> list[dict[str, Any]]:
    """Return tools formatted for OpenAI/OpenRouter."""
    formatted = []
    for tool in self._tools:  # ← Tools from FastMCP
        entry = {
            "type": "function",
            "function": {
                "name": tool.name,           # ← "calendar_get_events"
                "description": tool.description,  # ← From docstring
                "parameters": tool.inputSchema    # ← Schema from FastMCP
            }
        }
        formatted.append(entry)
    return formatted
```

---

### 5. This Goes to OpenRouter API

```python
# In src/backend/streaming.py (simplified)
response = await openrouter_client.chat_completion(
    model="openai/gpt-4o-mini-2024-07-18",
    messages=[
        {"role": "system", "content": "Today is 2025-11-10..."},
        {"role": "user", "content": "whats on my calendar today?"}
    ],
    tools=[
        {
            "type": "function",
            "function": {
                "name": "calendar_get_events",
                "description": "Retrieve calendar events...",
                "parameters": { /* the schema */ }
            }
        },
        # ... all other tools
    ]
)
```

---

### 6. LLM Responds with Tool Call

The LLM analyzes the schema and decides:

```json
{
  "role": "assistant",
  "tool_calls": [
    {
      "id": "call_xyz123",
      "type": "function",
      "function": {
        "name": "calendar_get_events",
        "arguments": "{\"user_email\":\"jck411@gmail.com\",\"time_min\":\"2025-11-10T00:00:00-05:00\",\"time_max\":\"2025-11-10T23:59:59-05:00\"}"
      }
    }
  ]
}
```

---

## The Magic of Type Hints

FastMCP uses Python's type system to auto-generate schemas:

| Python Type | JSON Schema | Notes |
|------------|-------------|-------|
| `str` | `{"type": "string"}` | Required if no default |
| `int` | `{"type": "integer"}` | Required if no default |
| `bool` | `{"type": "boolean"}` | Required if no default |
| `Optional[str]` | `{"anyOf": [{"type": "string"}, {"type": "null"}]}` | Optional |
| `str = "default"` | `{"type": "string", "default": "default"}` | Has default value |
| `int = 25` | `{"type": "integer", "default": 25}` | Has default value |
| `Optional[str] = None` | `{"anyOf": [...], "default": null}` | Optional with explicit null |

---

## Key Takeaways

1. ✅ **You never write JSON schemas manually** - they're generated from your function signature
2. ✅ **Type hints = JSON Schema types** (`str` → `"string"`, `int` → `"integer"`)
3. ✅ **Default values = schema defaults** (`= None` → `"default": null`)
4. ✅ **Docstrings = tool descriptions** (first line or full docstring)
5. ✅ **FastMCP does all the introspection** - you just write normal Python functions

This is why **good type hints** and **meaningful defaults** are so important - they directly influence how the LLM understands and uses your tools!

---

## Verification

You can always verify the generated schema using MCP Inspector:

```bash
npx @modelcontextprotocol/inspector --cli \
  uv run python -m backend.mcp_servers.calendar_server \
  --method tools/list | jq '.tools[] | select(.name == "calendar_get_events")'
```

This shows the **exact** schema that FastMCP generated from your Python function.
