# AI-Generated Conversation Titles — Implementation Plan

**Created:** February 15, 2026
**Status:** Complete
**Goal:** Replace the current "first 60 chars of first message" auto-title with an LLM-generated summary title using a cheap OpenRouter model.

---

## How It Works Today

- **File:** `src/backend/repository.py` → `_auto_title_if_needed()` (line ~908)
- When `add_message(role="user")` is called, it checks if `conversations.title IS NULL`
- If null, it grabs the first user message content, truncates to 60 chars, and sets it as the title
- There is no distinction between auto-generated titles and user-provided titles in the DB
- The `conversations` table has columns: `session_id`, `created_at`, `timezone`, `title`, `saved`, `updated_at`
- Columns are added via `_ensure_column()` pattern in `_create_schema()` (line ~128)

### Current conversation list flow
- **Backend:** `GET /api/chat/conversations` → `list_saved_conversations()` in `repository.py` (line ~810)
- **Frontend API:** `listConversations()` in `frontend/src/lib/api/client.ts` (line ~653)
- **Frontend display:** `ChatHeader.svelte` renders `.history-item` divs (line ~585) showing `conv.title || conv.preview || "Untitled"`
- **Types:** `ConversationSummary` in `frontend/src/lib/api/types.ts` (line ~490): `{ session_id, title, created_at, updated_at, message_count, preview }`

### When users "exit" a conversation
- **Clear/New Chat:** `App.svelte` `on:clear` handler (line ~401) calls `clearConversation()` from `frontend/src/lib/stores/chat.ts` (line ~420) — resets UI state, no backend call
- **Load old conversation:** `App.svelte` `on:loadConversation` handler (line ~417) calls `loadSession(sessionId)` from `chat.ts` (line ~448)
- Neither currently does anything with the outgoing conversation's title

### Existing infrastructure
- **OpenRouter client:** `src/backend/openrouter.py` — `OpenRouterClient` class with streaming methods, HTTP/2, connection pooling, retry logic. Uses `settings.openrouter_api_key` and `settings.openrouter_base_url` (`https://openrouter.ai/api/v1`)
- **Background tasks:** Project uses `asyncio.create_task()` throughout (see `app.py`, `alarm_scheduler.py`, `mcp_client.py`, etc.) — no FastAPI `BackgroundTasks`
- **Chat router:** `src/backend/routers/chat.py` — has endpoints for save, unsave, update title (`PATCH`), delete, list, get messages
- **Config:** `src/backend/config.py` — `Settings` class with Pydantic, env vars from `.env`

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Model | `google/gemini-2.0-flash-lite-001` | Very cheap, fast, good at short summarization |
| When to generate | On conversation exit (clear or switch) | Avoids wasting API calls on throwaway chats |
| Immediate title | Keep current truncation as placeholder | User always sees something right away |
| Failure handling | Fall back to truncated title, allow manual retry | Resilient; refresh icon lets user retry |
| Token cap | Truncate messages to ~4000 chars | Prevents cost blowout on long conversations |
| Non-streaming call | New `title_service.py` (not extending `OpenRouterClient`) | Keeps streaming client focused; title call is simple |
| Title tracking | New `title_source` DB column (`auto`/`ai`/`user`) | Frontend knows when to show refresh icon |
| Refresh icon | Per-conversation in history dropdown | Show when `title_source !== 'user'` |

---

## Stages

### Stage 1: Backend — DB schema + title service
> **Files to create/edit:** `src/backend/repository.py`, `src/backend/services/title_service.py` (new), `src/backend/config.py`

- [x] **1a.** Add `title_source` column to conversations table
  **File:** `src/backend/repository.py` inside `_create_schema()`
  **What:** Add `await self._ensure_column("conversations", "title_source", "TEXT DEFAULT 'auto'")` after the existing `_ensure_column` calls (around line 130).

- [x] **1b.** Update `_auto_title_if_needed()` to set `title_source = 'auto'`
  **File:** `src/backend/repository.py` → `_auto_title_if_needed()` (~line 953)
  **What:** Change the UPDATE statement from:
  ```sql
  UPDATE conversations SET title = ? WHERE session_id = ? AND title IS NULL
  ```
  to:
  ```sql
  UPDATE conversations SET title = ?, title_source = 'auto' WHERE session_id = ? AND title IS NULL
  ```

- [x] **1c.** Update `update_session_title()` to set `title_source = 'user'`
  **File:** `src/backend/repository.py` → `update_session_title()` (~line 896)
  **What:** Change the UPDATE to also set `title_source = 'user'`.

- [x] **1d.** Update `save_session()` to set `title_source = 'user'` when a title is explicitly provided
  **File:** `src/backend/repository.py` → `save_session()` (~line 862)
  **What:** When `title` param is truthy, also set `title_source = 'user'`.

- [x] **1e.** Update `list_saved_conversations()` to include `title_source` in result
  **File:** `src/backend/repository.py` → `list_saved_conversations()` (~line 810)
  **What:** Add `c.title_source` to the SELECT and include it in the returned dict.

- [x] **1f.** Add a `get_session_messages_for_title()` repo method
  **File:** `src/backend/repository.py`
  **What:** New method that fetches user + assistant messages for a session (skip tool/system roles), returns list of `{"role": str, "content": str}`. Truncate total content to ~4000 chars to cap tokens. Example:
  ```python
  async def get_session_messages_for_title(self, session_id: str) -> list[dict[str, str]]:
      """Fetch user/assistant messages for title generation, capped at ~4000 chars."""
      cursor = await self._connection.execute(
          "SELECT role, content FROM messages WHERE session_id = ? AND role IN ('user', 'assistant') ORDER BY id ASC",
          (session_id,),
      )
      rows = await cursor.fetchall()
      await cursor.close()
      messages = []
      total_chars = 0
      for row in rows:
          content = row["content"] or ""
          # Handle structured content (JSON arrays with text parts)
          try:
              parsed = json.loads(content)
              if isinstance(parsed, list):
                  text_parts = [item.get("text", "") for item in parsed if isinstance(item, dict) and item.get("type") == "text"]
                  content = " ".join(text_parts)
          except (json.JSONDecodeError, TypeError):
              pass
          if total_chars + len(content) > 4000:
              content = content[:4000 - total_chars]
              messages.append({"role": row["role"], "content": content})
              break
          messages.append({"role": row["role"], "content": content})
          total_chars += len(content)
      return messages
  ```

- [x] **1g.** Add `update_session_ai_title()` repo method
  **File:** `src/backend/repository.py`
  **What:** New method to set both title and `title_source = 'ai'`:
  ```python
  async def update_session_ai_title(self, session_id: str, title: str) -> bool:
      cursor = await self._connection.execute(
          "UPDATE conversations SET title = ?, title_source = 'ai', updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
          (title, session_id),
      )
      updated = cursor.rowcount
      await cursor.close()
      await self._connection.commit()
      return bool(updated)
  ```

- [x] **1h.** Add config for title model
  **File:** `src/backend/config.py` → `Settings` class
  **What:** Add field:
  ```python
  title_model: str = "google/gemini-2.0-flash-lite-001"
  ```
  This allows overriding via `TITLE_MODEL` env var.

- [x] **1i.** Create `src/backend/services/title_service.py`
  **What:** New file with a `generate_title()` async function. Uses the existing `OpenRouterClient`'s HTTP client pool pattern OR a standalone `httpx` call. Non-streaming POST to OpenRouter `/chat/completions` with `stream: false`.
  ```python
  """Lightweight LLM title generation for conversations."""
  from __future__ import annotations
  import json, logging
  import httpx
  from ..config import Settings

  logger = logging.getLogger(__name__)

  TITLE_SYSTEM_PROMPT = (
      "Generate a concise title (3-8 words) that summarizes the main topic of this conversation. "
      "Return only the title text. No quotes, no punctuation at the end, no extra commentary."
  )

  async def generate_title(settings: Settings, messages: list[dict[str, str]]) -> str | None:
      """Call OpenRouter with a cheap model to generate a conversation title.
      Returns the title string, or None on failure."""
      if not messages:
          return None
      conversation_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
      payload = {
          "model": settings.title_model,
          "messages": [
              {"role": "system", "content": TITLE_SYSTEM_PROMPT},
              {"role": "user", "content": conversation_text},
          ],
          "max_tokens": 30,
          "temperature": 0.3,
          "stream": False,
      }
      base_url = str(settings.openrouter_base_url).rstrip("/")
      headers = {
          "Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}",
          "Content-Type": "application/json",
      }
      try:
          async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
              resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
              resp.raise_for_status()
              data = resp.json()
              title = data["choices"][0]["message"]["content"].strip()
              # Sanity check: reject empty or absurdly long titles
              if not title or len(title) > 120:
                  return None
              return title
      except Exception:
          logger.exception("Failed to generate AI title")
          return None
  ```

- [x] **1j.** Write tests for title service
  **File:** `tests/test_title_service.py` (new)
  **What:** Mock the `httpx.AsyncClient.post` call, verify:
  - Happy path: returns title string
  - API error: returns None
  - Empty messages: returns None
  - Absurdly long response: returns None

**Checkpoint:** After Stage 1, the backend has the DB column, repo methods, config, and title service ready. No API endpoint yet, no frontend changes. Run existing tests to ensure nothing broke.

---

### Stage 2: Backend — API endpoint
> **Files to edit:** `src/backend/routers/chat.py`

- [x] **2a.** Add `POST /chat/session/{session_id}/generate-title` endpoint
  **File:** `src/backend/routers/chat.py`
  **What:** New endpoint that:
  1. Gets the orchestrator's repository via the existing dependency pattern
  2. Calls `repo.get_session_messages_for_title(session_id)`
  3. Calls `generate_title(settings, messages)`
  4. If title returned, calls `repo.update_session_ai_title(session_id, title)`
  5. Returns `{"session_id": str, "title": str, "title_source": str}` — on success `title_source = "ai"`, on failure returns current title with `title_source` unchanged

  Example:
  ```python
  @router.post("/chat/session/{session_id}/generate-title")
  async def generate_session_title(
      session_id: str,
      orchestrator: ChatOrchestrator = Depends(get_orchestrator),
  ):
      repo = orchestrator.repository
      messages = await repo.get_session_messages_for_title(session_id)
      if not messages:
          raise HTTPException(status_code=404, detail="No messages found")

      from ..services.title_service import generate_title
      title = await generate_title(orchestrator.settings, messages)
      if title:
          await repo.update_session_ai_title(session_id, title)
          return {"session_id": session_id, "title": title, "title_source": "ai"}

      # Fallback: return existing title
      # (fetch current title from DB)
      conv = await repo.get_conversation_metadata(session_id)
      return {
          "session_id": session_id,
          "title": conv.get("title") if conv else None,
          "title_source": conv.get("title_source", "auto") if conv else "auto",
          "generated": False,
      }
  ```

- [x] **2b.** Add `get_conversation_metadata()` repo method if it doesn't exist
  **File:** `src/backend/repository.py`
  **What:** Simple SELECT of session_id, title, title_source, saved, created_at, updated_at for a single conversation. Check if something equivalent already exists first — `get_session_messages` endpoint in the router fetches metadata, so trace what repo method it uses.

- [x] **2c.** Test the endpoint
  **File:** `tests/test_chat_router.py` (extend existing)
  **What:** Add test for the new endpoint with mocked title service.

**Checkpoint:** After Stage 2, you can test the endpoint manually: `curl -X POST https://localhost:8000/api/chat/session/{id}/generate-title` and verify it returns an AI-generated title.

---

### Stage 3: Frontend — API client + types
> **Files to edit:** `frontend/src/lib/api/client.ts`, `frontend/src/lib/api/types.ts`

- [x] **3a.** Add `title_source` to `ConversationSummary` type
  **File:** `frontend/src/lib/api/types.ts` (~line 490)
  **What:** Add `title_source?: 'auto' | 'ai' | 'user';` to the `ConversationSummary` interface.

- [x] **3b.** Add `generateTitle()` API function
  **File:** `frontend/src/lib/api/client.ts`
  **What:** Add after `updateConversationTitle()`:
  ```typescript
  export async function generateConversationTitle(
    sessionId: string,
  ): Promise<{ session_id: string; title: string; title_source: string }> {
    const path = `/api/chat/session/${encodeURIComponent(sessionId)}/generate-title`;
    return requestJson(resolveApiPath(path), { method: 'POST' });
  }
  ```

**Checkpoint:** Frontend can now call the backend. No UI wired up yet.

---

### Stage 4: Frontend — trigger on conversation exit
> **Files to edit:** `frontend/src/App.svelte`

- [x] **4a.** Fire title generation when user clears conversation (New Chat)
  **File:** `frontend/src/App.svelte` → `on:clear` handler (~line 401)
  **What:** Before calling `clearConversation()`, capture the current `sessionId`. After clearing, fire `generateConversationTitle(previousSessionId)` as a fire-and-forget promise. On completion (success or failure), call `loadConversationList()` to refresh the sidebar with the new title.
  ```typescript
  on:clear={() => {
    const previousSessionId = get(chatStore).sessionId;
    presetAttachments = [];
    prompt = "";
    clearConversation();
    if (previousSessionId) {
      generateConversationTitle(previousSessionId)
        .catch(() => {})
        .finally(() => void loadConversationList());
    } else {
      void loadConversationList();
    }
  }}
  ```

- [x] **4b.** Fire title generation when user switches to another conversation
  **File:** `frontend/src/App.svelte` → `on:loadConversation` handler (~line 417)
  **What:** Same pattern — capture outgoing sessionId before loading the new one:
  ```typescript
  on:loadConversation={async (event) => {
    const previousSessionId = get(chatStore).sessionId;
    await loadSession(event.detail.sessionId);
    presetAttachments = [];
    prompt = "";
    if (previousSessionId && previousSessionId !== event.detail.sessionId) {
      generateConversationTitle(previousSessionId)
        .catch(() => {})
        .finally(() => void loadConversationList());
    }
  }}
  ```

- [x] **4c.** Import `generateConversationTitle` and `get` in `App.svelte`
  **What:** Add the import at the top of the script section. `get` from `svelte/store` may already be imported — check first.

**Checkpoint:** After Stage 4, switching conversations or clicking "New Chat" auto-generates AI titles for the outgoing conversation. Test by having a conversation, clicking New Chat, opening History — the old conversation should have a summarized title within ~1-2 seconds.

---

### Stage 5: Frontend — refresh icon in history
> **Files to edit:** `frontend/src/lib/components/chat/ChatHeader.svelte`

- [x] **5a.** Add refresh icon button next to delete button in history items
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` → inside `{#each group.items as conv}` block (~line 585)
  **What:** Add a refresh/regenerate icon button BEFORE the delete button (so layout is: `[title] [msg count] [refresh] [delete]`). Use adequate spacing between refresh and delete to prevent accidental clicks. Only show when `conv.title_source !== 'user'`.
  ```svelte
  {#if conv.title_source !== 'user'}
    <button
      class="history-item-refresh"
      type="button"
      aria-label="Regenerate title"
      on:click={(e) => handleRegenerateTitle(e, conv.session_id)}
    >
      <!-- refresh/sync SVG icon, 14x14 -->
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M1 4v6h6M23 20v-6h-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>
  {/if}
  ```

- [x] **5b.** Add `handleRegenerateTitle()` function
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` (script section)
  **What:** Stop event propagation (prevent loading the conversation), call `generateConversationTitle()`, dispatch an event or callback to refresh the conversation list.
  ```typescript
  async function handleRegenerateTitle(event: MouseEvent, sessionId: string) {
    event.stopPropagation();
    try {
      await generateConversationTitle(sessionId);
      dispatch('refreshConversations');
    } catch (error) {
      console.error('Failed to regenerate title', error);
    }
  }
  ```

- [x] **5c.** Handle `refreshConversations` event in `App.svelte`
  **File:** `frontend/src/App.svelte`
  **What:** Add `on:refreshConversations={() => void loadConversationList()}` to the `<ChatHeader>` component.

- [x] **5d.** Style the refresh button
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` (style section)
  **What:** Match `.history-item-delete` styling but with its own class `.history-item-refresh`. Ensure spacing: `margin-right: 8px` or similar between refresh and delete. Consider a subtle opacity (0.4 → 0.8 on hover) so it doesn't visually compete with the title.

- [x] **5e.** Optional: loading spinner state on refresh icon
  **What:** Track `regeneratingSessionId` in the component. While generating, show a spinning animation on the refresh icon for that conversation. Reset on completion.

**Checkpoint:** After Stage 5, each conversation in the history dropdown shows a refresh icon. Clicking it regenerates the title via the AI model and updates the list.

---

### Stage 6: Testing & polish
> **Files to edit:** various test files, minor tweaks

- [x] **6a.** Run all existing tests to verify no regressions
  ```bash
  cd /home/human/REPOS/Backend_FastAPI && uv run pytest tests/ -x -q
  ```

- [x] **6b.** Test end-to-end manually
  - Start a conversation, send a few messages
  - Click "New Chat" → check history: title should update from truncated text to AI summary
  - Load an old conversation, then switch to another → outgoing title should regenerate
  - Click refresh icon on a conversation → title updates
  - Manually rename a conversation (if UI exists) → refresh icon should not appear

- [x] **6c.** Build frontend and verify
  ```bash
  cd frontend && npm run build && cd ..
  ```

- [x] **6d.** Deploy to server
  ```bash
  git add src/backend/ frontend/ tests/ docs/
  git commit -m "feat: AI-generated conversation titles via OpenRouter"
  git push
  ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
  ```

---

## File Reference

| File | Role | Changes |
|------|------|---------|
| `src/backend/config.py` | Settings | Add `title_model` field |
| `src/backend/repository.py` | DB layer | Add column, update methods, new methods |
| `src/backend/services/title_service.py` | **NEW** | LLM title generation function |
| `src/backend/routers/chat.py` | API | Add generate-title endpoint |
| `frontend/src/lib/api/types.ts` | Types | Add `title_source` to `ConversationSummary` |
| `frontend/src/lib/api/client.ts` | API client | Add `generateConversationTitle()` |
| `frontend/src/App.svelte` | Root component | Trigger on clear/switch, handle refresh event |
| `frontend/src/lib/components/chat/ChatHeader.svelte` | History UI | Add refresh icon, handler, styles |
| `tests/test_title_service.py` | **NEW** | Unit tests for title service |

## Quick Start for a Fresh Session

1. Read this doc first
2. Start with whichever stage is next (first unchecked item)
3. Key files to read for context before each stage:
   - **Stage 1:** `src/backend/repository.py` (schema + existing methods), `src/backend/config.py`
   - **Stage 2:** `src/backend/routers/chat.py` (existing endpoints + dependency injection pattern)
   - **Stage 3:** `frontend/src/lib/api/client.ts`, `frontend/src/lib/api/types.ts`
   - **Stage 4:** `frontend/src/App.svelte` (clear + loadConversation handlers)
   - **Stage 5:** `frontend/src/lib/components/chat/ChatHeader.svelte` (history dropdown section)
   - **Stage 6:** Run tests, build, deploy
