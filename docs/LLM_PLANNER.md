# LLM-Based Context Planning

## Status: ✅ Active (Always On)

The system uses LLM-based tool planning exclusively. There is no keyword-based fallback or configuration option to disable it.

## How It Works

The `LLMContextPlanner` uses the following approach:

1. **LLM makes planning decisions**: Sends the conversation and available tools to an LLM to decide which tools are relevant
2. **Simple fallback for errors**: If the LLM planner fails, provides all available tools with broad search enabled
3. **No keyword matching**: No hardcoded rules or patterns, all intelligence is in the LLM

### Architecture

```
┌─────────────────┐
│  User Request   │
└────────┬────────┘
         │
         v
┌─────────────────────────────┐
│   LLMContextPlanner         │
│  ┌───────────────────────┐  │
│  │ 1. Create minimal     │  │
│  │    fallback plan      │  │
│  └───────────────────────┘  │
│  ┌───────────────────────┐  │
│  │ 2. Call LLM planner   │  │
│  │    with full context  │  │
│  └───────────────────────┘  │
│  ┌───────────────────────┐  │
### Architecture

```
┌─────────────────┐
│  User Request   │
└────────┬────────┘
         │
         v
┌─────────────────────────────┐
│   LLMContextPlanner         │
│  ┌───────────────────────┐  │
│  │ 1. Create minimal     │  │
│  │    fallback plan      │  │
│  └───────────────────────┘  │
│  ┌───────────────────────┐  │
│  │ 2. Call LLM planner   │  │
│  │    with full context  │  │
│  └───────────────────────┘  │
│  ┌───────────────────────┐  │
│  │ 3. Merge LLM response │  │
│  │    with fallback      │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
         │
         v
┌─────────────────┐
│  Tool Context   │
│     Plan        │
└─────────────────┘
```     """Generate a tool context plan using the LLM directly."""
```

### Planning Flow

1. **Prepare minimal fallback**: Creates a simple plan with `broad_search=True` in case the LLM fails
2. **Compact tool digest**: Reduces the capability digest to essential information for the LLM
## Implementation Details

### LLMContextPlanner Class

Located in `src/backend/chat/llm_planner.py`:

```python
class LLMContextPlanner:
    def __init__(self, client: OpenRouterClient):
        self._client = client

    async def plan(
        self,
        request: ChatCompletionRequest,
        conversation: Sequence[dict[str, Any]],
        capability_digest: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> ToolContextPlan:
        """Generate a tool context plan using the LLM directly."""
```

### Planning Flow

1. **Create fallback plan**: Prepares a simple plan with `broad_search=True` in case the LLM call fails
2. **Compact tool digest**: Reduces the capability digest to essential information for the LLM
3. **Call LLM planner**: Makes an async request via `client.request_tool_plan()`
4. **Merge response**: Combines the LLM's plan with the fallback using `merge_model_tool_plan()`
5. **Return plan**: Returns the merged `ToolContextPlan`

### Fallback Behavior

When the LLM planner fails (network error, timeout, API error), the system uses the fallback:

```python
ToolContextPlan(
    stages=[],
    broad_search=True,
    intent="General assistance with all available tools",
)
```

This provides **all available tools** to the model, ensuring the system remains functional.

## Code Simplification

The current implementation is straightforward:

```python
# In ChatOrchestrator
self._llm_planner = LLMContextPlanner(self._client)

# During request processing
plan = await self._llm_planner.plan(
    request,
    conversation,
    capability_digest=capability_digest,
)

# Use the plan to select tools
contexts = plan.contexts_for_attempt(0)
ranked_tool_names = [...]  # Extract from plan.candidate_tools
tools_payload = self._mcp_client.get_openai_tools_by_qualified_names(ranked_tool_names)
```

All planning logic is encapsulated in the `LLMContextPlanner` class.

## Testing

Tests are provided in `tests/test_llm_planner.py`:

```bash
pytest tests/test_llm_planner.py -v
```

Tests cover:
- LLM response handling
- Fallback on errors
- Explicit tool requests
- Tool digest compaction
- Invalid input handling

## Migration Guide

### For Developers

## Benefits

1. **Simpler code**: No keyword mapping logic to maintain
2. **Better adaptability**: LLM understands nuanced queries and context
3. **Easier maintenance**: New tools are automatically considered by the LLM
4. **Improved accuracy**: AI-driven tool selection based on full conversation context
5. **Graceful degradation**: Falls back to providing all tools if planner fails
No changes required! The system automatically uses the best available planning method.

## Future Enhancements

1. **Caching**: Cache LLM planner responses for similar queries
## Future Enhancements

1. **Caching**: Cache LLM planner responses for similar queries to reduce latency
2. **Metrics**: Track planner success rate and tool selection accuracy
3. **Custom prompts**: Allow customization of the LLM planner system prompt
4. **Local LLM**: Support local LLM models for planning (privacy/cost)
5. **Plan persistence**: Store and analyze historical plans for optimization
- `src/backend/chat/llm_planner.py` - LLM planner implementation
- `src/backend/chat/orchestrator.py` - Integration point
- `src/backend/config.py` - Configuration settings
- `tests/test_llm_planner.py` - Test suite
## For Developers

The LLM planner is always active. Key points:

1. **No configuration needed**: System uses LLM planning automatically
2. **Monitor logs**: Check for LLM planner failures (falls back gracefully)
3. **Test tool selection**: Verify tools are being selected appropriately
4. **Customize prompts**: Modify `client.request_tool_plan()` if needed

## For Users

No configuration or action required. The system intelligently selects tools based on your conversation context.
