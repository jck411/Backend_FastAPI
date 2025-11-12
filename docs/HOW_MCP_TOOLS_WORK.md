# How MCP Tools Work - The Complete Picture

## Yes, It's Really That Simple!

You write a **normal Python function** with a decorator, and FastMCP handles all the magic:

```python
@mcp.tool("calendar_get_events")  # ← This one line makes it an MCP tool!
async def get_events(
    user_email: str = DEFAULT_USER_EMAIL,
    calendar_id: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 25,
    query: Optional[str] = None,
    detailed: bool = False,
) -> str:
    """Retrieve calendar events. Omit calendar_id to search all household calendars..."""

    # Your regular Python code here!
    service = get_calendar_service(user_email)
    events_result = await asyncio.to_thread(
        service.events().list(calendarId=calendar_id, **params).execute
    )

    # Format and return results
    return "Schedule for jck411@gmail.com: 3 calendar events..."
```

---

## What Happens Under the Hood

### 1. **You Add the Decorator**

```python
@mcp.tool("calendar_get_events")  # ← This is the magic line
```

This tells FastMCP: "Make this function available as a tool to LLMs"

### 2. **FastMCP Inspects Your Function**

When your server starts, FastMCP:
- Reads the function signature
- Extracts type hints: `str`, `Optional[str]`, `int`, `bool`
- Captures defaults: `= DEFAULT_USER_EMAIL`, `= None`, `= 25`, `= False`
- Reads the docstring: `"""Retrieve calendar events..."""`

### 3. **FastMCP Generates the JSON Schema**

Automatically creates:
```json
{
  "name": "calendar_get_events",
  "description": "Retrieve calendar events. Omit calendar_id...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "user_email": {"type": "string", "default": "jck411@gmail.com"},
      "calendar_id": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null},
      "time_min": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null},
      "time_max": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null},
      "max_results": {"type": "integer", "default": 25},
      "query": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null},
      "detailed": {"type": "boolean", "default": false}
    }
  }
}
```

### 4. **Your Backend Sends It to the LLM**

```python
# In your chat orchestrator
tools = mcp_client.get_openai_tools()  # ← Gets all tool schemas

# Send to OpenRouter/OpenAI
response = await openrouter.chat_completion(
    model="gpt-4o-mini",
    messages=[...],
    tools=tools  # ← LLM receives all tool schemas
)
```

### 5. **LLM Decides to Call Your Tool**

```json
{
  "role": "assistant",
  "tool_calls": [
    {
      "function": {
        "name": "calendar_get_events",
        "arguments": "{\"user_email\":\"jck411@gmail.com\",\"time_min\":\"2025-11-10T00:00:00-05:00\"}"
      }
    }
  ]
}
```

### 6. **Your Function Gets Called**

```python
# FastMCP automatically:
# 1. Parses the JSON arguments
# 2. Validates types
# 3. Calls your function with the parameters
result = await get_events(
    user_email="jck411@gmail.com",
    time_min="2025-11-10T00:00:00-05:00"
)

# 7. Returns the result back to the LLM
# "Schedule for jck411@gmail.com: 3 calendar events..."
```

---

## The Actual Function (Simplified)

Here's what your real function looks like (simplified):

```python
@mcp.tool("calendar_get_events")
async def get_events(
    user_email: str = DEFAULT_USER_EMAIL,
    calendar_id: Optional[str] = None,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 25,
    query: Optional[str] = None,
    detailed: bool = False,
) -> str:
    """Retrieve calendar events. Omit calendar_id to search all household calendars..."""

    # 1. Get Google Calendar service
    service = get_calendar_service(user_email)

    # 2. Parse time parameters
    time_min_rfc = _parse_time_string(time_min)
    time_max_rfc = _parse_time_string(time_max) if time_max else None

    # 3. Determine which calendars to query
    if calendar_id is None:
        calendars_to_query = ["primary", "family", "work"]  # All calendars
    else:
        calendars_to_query = [calendar_id]  # Specific calendar

    # 4. Query Google Calendar API
    events = []
    for cal_id in calendars_to_query:
        result = await asyncio.to_thread(
            service.events().list(
                calendarId=cal_id,
                timeMin=time_min_rfc,
                timeMax=time_max_rfc,
                maxResults=max_results
            ).execute
        )
        events.extend(result.get("items", []))

    # 5. Format and return results
    return f"Schedule for {user_email}: {len(events)} calendar events..."
```

**That's it!** No manual JSON schema writing, no API boilerplate, just a normal Python function with a decorator.

---

## What You Need to Provide

### Minimal Requirements:

1. **The decorator**: `@mcp.tool("tool_name")`
2. **Type hints**: So FastMCP knows what types to expect
3. **Default values**: For optional parameters
4. **A docstring**: So the LLM understands what the tool does
5. **Implementation**: Your actual business logic

### Example of a Minimal Tool:

```python
@mcp.tool("add_numbers")
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b
```

That's literally all you need! FastMCP generates:
```json
{
  "name": "add_numbers",
  "description": "Add two numbers together.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "a": {"type": "integer"},
      "b": {"type": "integer"}
    },
    "required": ["a", "b"]
  }
}
```

---

## What FastMCP Handles For You

✅ **JSON Schema generation** - From your type hints
✅ **Parameter validation** - Ensures correct types
✅ **Default value handling** - Applies defaults when needed
✅ **MCP protocol** - Handles all the low-level communication
✅ **Error handling** - Wraps exceptions appropriately
✅ **Serialization** - Converts Python objects to JSON
✅ **Documentation** - Uses your docstrings

---

## Common Patterns

### Optional Parameters
```python
@mcp.tool("search")
def search(query: str, max_results: Optional[int] = None) -> str:
    """Search with optional result limit."""
    limit = max_results or 10  # Default to 10 if not provided
    return f"Found {limit} results for '{query}'"
```

### Complex Return Types
```python
@mcp.tool("get_user")
def get_user(user_id: str) -> str:  # ← Always return str for MCP tools
    """Get user information."""
    user = database.get_user(user_id)
    # Format as readable text for the LLM
    return f"User: {user.name}, Email: {user.email}, Role: {user.role}"
```

### Async Operations
```python
@mcp.tool("fetch_data")
async def fetch_data(url: str) -> str:  # ← Use async for I/O
    """Fetch data from a URL."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
```

---

## Key Insights

1. **You write normal Python** - No special MCP classes or inheritance required
2. **Type hints = Schema** - FastMCP converts Python types to JSON Schema automatically
3. **Docstrings = Descriptions** - What you document is what the LLM sees
4. **Defaults matter** - They tell the LLM what's optional and what's recommended
5. **Return strings** - Always return `str` so the LLM can read the result

---

## How to Create a New Tool

1. Open your MCP server file (e.g., `calendar_server.py`)
2. Write a function with type hints
3. Add `@mcp.tool("tool_name")`
4. Write a good docstring
5. Implement your logic
6. Done! The LLM can now use it.

**Example:**
```python
@mcp.tool("get_weather")
async def get_weather(city: str, units: str = "metric") -> str:
    """Get current weather for a city. Units can be 'metric' or 'imperial'."""
    # Call weather API
    data = await weather_api.get_current(city, units)
    # Format for LLM
    return f"Weather in {city}: {data.temp}°, {data.conditions}"
```

That's it! No configuration files, no JSON schemas to write, no API wrappers to build. FastMCP handles everything.
