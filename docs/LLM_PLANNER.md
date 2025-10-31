# LLM-Based Context Planning

## Overview

The LLM-based context planner simplifies the tool selection logic by delegating context planning directly to a Language Model, eliminating the need for complex keyword-based mapping rules.

## Motivation

The previous keyword-based planner (`ToolContextPlanner`) used a hardcoded set of rules to map user queries to tool contexts:

```python
_KEYWORD_RULES = (
    (("schedule", "scheduling", "calendar", ...), [["calendar"]]),
    (("task", "tasks", "todo", ...), [["tasks"]]),
    # ... many more rules
)
```

This approach had several limitations:

1. **Maintenance burden**: Each new tool context required updating keyword rules
2. **Limited flexibility**: Couldn't adapt to nuanced queries or context
3. **Rigid matching**: Simple keyword matching missed complex user intents
4. **Code complexity**: Extensive mapping logic throughout the codebase

## Solution: LLM-First Planning

The new `LLMContextPlanner` simplifies this by:

1. **Direct LLM delegation**: Sending the full conversation and tool digest to an LLM planner endpoint
2. **Minimal fallback**: Only using a simple broad-search fallback when the LLM is unavailable
3. **Eliminating keyword rules**: No hardcoded keyword-to-context mappings needed

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
```

## Configuration

Enable or disable LLM-first planning via environment variable:

```bash
# Enable LLM-first planning (default)
USE_LLM_PLANNER=true

# Disable and use legacy keyword-based planning
USE_LLM_PLANNER=false
```

In code:

```python
from backend.config import Settings

settings = Settings()
if settings.use_llm_planner:
    # Uses LLMContextPlanner
else:
    # Uses ToolContextPlanner
```

## Implementation Details

### LLMContextPlanner Class

The `LLMContextPlanner` class has a simple interface:

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

1. **Prepare minimal fallback**: Creates a simple plan with `broad_search=True` in case the LLM fails
2. **Compact tool digest**: Reduces the capability digest to essential information for the LLM
3. **Call LLM planner**: Makes an async request to the OpenRouter planner endpoint
4. **Merge response**: Combines the LLM's plan with the fallback using `merge_model_tool_plan`
5. **Return plan**: Returns the merged `ToolContextPlan`

### Fallback Behavior

When the LLM planner is unavailable (network error, timeout, etc.), the system falls back to a simple plan:

```python
ToolContextPlan(
    stages=[],
    broad_search=True,
    intent="General assistance with all available tools",
)
```

This ensures the system remains functional even without the LLM planner.

## Code Simplification

### Before (Keyword-Based)

The orchestrator had to:

1. Call keyword-based planner
2. Extract contexts from the plan
3. Build a ranked digest for those contexts
4. Call the LLM planner with the ranked digest
5. Merge results
6. Re-rank tools based on merged plan

```python
# ~70 lines of complex planning logic
plan = self._tool_planner.plan(request, conversation, capability_digest)
contexts = plan.contexts_for_attempt(0)
# ... digest extraction ...
# ... LLM call ...
# ... merging ...
# ... re-ranking ...
```

### After (LLM-First)

With LLM-first planning:

```python
# Simple conditional based on config
if self._settings.use_llm_planner:
    plan = await self._llm_planner.plan(
        request,
        conversation,
        capability_digest=capability_digest,
    )
else:
    # Legacy path still available
    plan = self._tool_planner.plan(...)
```

The planning logic is encapsulated in the `LLMContextPlanner` class, reducing the orchestrator complexity.

## Benefits

1. **Simpler code**: Eliminates complex keyword mapping logic
2. **Better adaptability**: LLM can understand nuanced queries
3. **Easier maintenance**: No need to update keyword rules for new tools
4. **Improved user experience**: More accurate tool selection based on context
5. **Gradual migration**: Can be toggled on/off for testing and rollback

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

1. **Enable LLM planner**: Set `USE_LLM_PLANNER=true` in your `.env` file
2. **Test your workflows**: Ensure tool selection works as expected
3. **Monitor logs**: Check for any LLM planner failures
4. **Fallback available**: If issues arise, set `USE_LLM_PLANNER=false`

### For Users

No changes required! The system automatically uses the best available planning method.

## Future Enhancements

1. **Caching**: Cache LLM planner responses for similar queries
2. **Metrics**: Track LLM vs keyword planner accuracy
3. **Hybrid mode**: Use both planners and combine results
4. **Custom prompts**: Allow customization of the LLM planner prompt
5. **Local LLM**: Support local LLM models for planning

## Related Files

- `src/backend/chat/llm_planner.py` - LLM planner implementation
- `src/backend/chat/orchestrator.py` - Integration point
- `src/backend/config.py` - Configuration settings
- `tests/test_llm_planner.py` - Test suite
- `docs/LLM_PLANNER.md` - This document
