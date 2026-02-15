# Conversation History Search — Implementation Plan

**Created:** February 15, 2026
**Status:** Complete
**Goal:** Add a search field to the conversation history dropdown that filters conversations server-side by title and preview text.

---

## How It Works Today

- **History dropdown:** `frontend/src/lib/components/chat/ChatHeader.svelte` — rendered twice (PWA ~line 556, desktop ~line 860). Toggled by `historyOpen` boolean via `toggleHistory()` (~line 133).
- **Conversation list:** `App.svelte` holds `conversations: ConversationSummary[]` (~line 95), loaded by `loadConversationList()` (~line 96) which calls `listConversations()` from the API client.
- **API client:** `frontend/src/lib/api/client.ts` → `listConversations(limit, offset)` (~line 653). Only accepts `limit` and `offset`, no search.
- **Backend endpoint:** `GET /api/chat/conversations` in `src/backend/routers/chat.py` (~line 82). Accepts `limit` and `offset` query params.
- **Repository:** `list_saved_conversations()` in `src/backend/repository.py` (~line 813). SQL query selects from `conversations` table WHERE `saved = 1`, joins preview from first user message, orders by `COALESCE(updated_at, created_at) DESC`.
- **Types:** `ConversationSummary` in `frontend/src/lib/api/types.ts` (~line 490): `{ session_id, title, title_source?, created_at, updated_at, message_count, preview }`.
- **Grouping:** `groupByDate()` in ChatHeader (~line 177) groups conversations by Today / Yesterday / Previous 7 Days / Previous 30 Days / Month+Year / Older.
- **Dropdown positioning (desktop):** Fixed position calculated from `historyWrapperEl.getBoundingClientRect()`, 320px wide, max 400px tall (~line 134–158).
- **PWA dropdown:** Static position, inline below button, max-height 250px.
- **Close behavior:** `handleClickOutside()` on `svelte:window on:click` — checks `target.closest('.history-wrapper')` (~line 213).

### DB schema (conversations table)
| Column | Type |
|--------|------|
| `session_id` | TEXT PRIMARY KEY |
| `title` | TEXT |
| `title_source` | TEXT DEFAULT 'auto' |
| `saved` | INTEGER DEFAULT 0 |
| `created_at` | DATETIME |
| `updated_at` | DATETIME |
| `timezone` | TEXT |

### Existing patterns to follow
- The models endpoint already has a `search` query parameter with substring matching — see `chat.py` ~line 191.
- ChatHeader already imports from `../../api/client` (for `generateConversationTitle`).
- App.svelte passes `conversations` as a prop and refreshes via `loadConversationList()`.

---

## UX Design

**The "History" button morphs into a search input when the dropdown opens.**

- **Closed state:** Normal button — "History" text (desktop) or clock icon + "History" (PWA).
- **Open state:** The button is replaced by a text input with placeholder "Search..." and a small ✕ to close. The input auto-focuses. The dropdown appears below.
- **Typing:** Debounced (300ms). When the user types, a server-side search runs and replaces the dropdown content. When the input is empty, the full default conversation list is shown.
- **Close:** Clicking outside, pressing Escape, or clicking ✕ closes the dropdown AND clears the search state.

### Visual layout (open state)
```
┌──────────────────────┐
│ 🔍 Search...       ✕ │  ← input replaces button
├──────────────────────┤
│ TODAY                 │
│  Conversation title   │
│  Another convo        │
│ YESTERDAY             │
│  Old conversation     │
└──────────────────────┘
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Search location | SQL `LIKE` on `title` + first-user-message preview | Fast, no FTS needed for short text; covers both AI-generated titles and message text |
| Client vs server | Server-side | Scales beyond the loaded 50 conversations; unlimited history |
| Debounce | 300ms | Responsive without hammering the server |
| Empty input | Show default conversation list | Seamless transition between browse and search |
| Button morph | Replace button with input when open | User requested; clean dual-function UX |
| Results grouping | Same `groupByDate()` for both search results and default list | Consistent visual hierarchy |
| No results state | "No matching conversations" message | Distinct from "No saved conversations" |

---

## Stages

### Stage 1: Backend — Add search to repository + endpoint
> **Files to edit:** `src/backend/repository.py`, `src/backend/routers/chat.py`

- [x] **1a.** Add `search` parameter to `list_saved_conversations()`
  **File:** `src/backend/repository.py` → `list_saved_conversations()` (~line 813)
  **What:** Add `search: str | None = None` parameter. When provided, add SQL WHERE clause to filter by title OR preview. Use parameterized `LIKE` with `%search%`:
  ```python
  async def list_saved_conversations(
      self,
      *,
      limit: int = 50,
      offset: int = 0,
      search: str | None = None,
  ) -> list[dict[str, Any]]:
      """Return saved conversations with title, date, and message preview."""

      assert self._connection is not None
      params: list[Any] = []
      where_clauses = ["c.saved = 1"]

      if search:
          where_clauses.append(
              "(c.title LIKE ? OR "
              "(SELECT m.content FROM messages m "
              "WHERE m.session_id = c.session_id AND m.role = 'user' "
              "ORDER BY m.id ASC LIMIT 1) LIKE ?)"
          )
          like_term = f"%{search}%"
          params.extend([like_term, like_term])

      where_sql = " AND ".join(where_clauses)
      params.extend([limit, offset])

      cursor = await self._connection.execute(
          f"""
          SELECT
              c.session_id,
              c.title,
              c.title_source,
              c.created_at,
              c.updated_at,
              (SELECT COUNT(*) FROM messages m WHERE m.session_id = c.session_id) AS message_count,
              (SELECT m.content FROM messages m
               WHERE m.session_id = c.session_id AND m.role = 'user'
               ORDER BY m.id ASC LIMIT 1) AS preview
          FROM conversations c
          WHERE {where_sql}
          ORDER BY COALESCE(c.updated_at, c.created_at) DESC
          LIMIT ? OFFSET ?
          """,
          tuple(params),
      )
      # ... rest of method unchanged
  ```

- [x] **1b.** Add `search` query parameter to the conversations endpoint
  **File:** `src/backend/routers/chat.py` → `list_conversations()` (~line 82)
  **What:** Add `search: str | None = Query(None, min_length=1, max_length=200)` and pass it through:
  ```python
  @router.get("/chat/conversations", status_code=200)
  async def list_conversations(
      request: Request,
      limit: int = Query(50, ge=1, le=200),
      offset: int = Query(0, ge=0),
      search: str | None = Query(None, min_length=1, max_length=200),
  ) -> dict[str, Any]:
      """List saved conversations, optionally filtered by search term."""
      orchestrator: ChatOrchestrator = request.app.state.chat_orchestrator
      conversations = await orchestrator.repository.list_saved_conversations(
          limit=limit, offset=offset, search=search
      )
      return {"conversations": conversations}
  ```

- [x] **1c.** Write backend tests
  **File:** `tests/test_repository.py` (extend)
  **What:** Add test that creates conversations with known titles, then calls `list_saved_conversations(search="keyword")` and verifies only matching conversations are returned. Test both title match and preview (message content) match. Test that empty/no-match returns empty list.

  **File:** `tests/test_chat_router.py` (extend)
  **What:** Add test for `GET /api/chat/conversations?search=foo` verifying the query param is passed through and filtering works.

**Checkpoint:** Run `uv run pytest tests/test_repository.py tests/test_chat_router.py -x -q`. Backend search works. No frontend changes yet.

---

### Stage 2: Frontend — API client + types
> **Files to edit:** `frontend/src/lib/api/client.ts`

- [x] **2a.** Add `search` parameter to `listConversations()`
  **File:** `frontend/src/lib/api/client.ts` → `listConversations()` (~line 653)
  **What:** Add optional `search` parameter. When provided, append `&search=` (URL-encoded) to the query string:
  ```typescript
  export async function listConversations(
    limit = 50,
    offset = 0,
    search?: string,
  ): Promise<ConversationSummary[]> {
    let url = `/api/chat/conversations?limit=${limit}&offset=${offset}`;
    if (search) {
      url += `&search=${encodeURIComponent(search)}`;
    }
    const response = await requestJson<ConversationListResponse>(
      resolveApiPath(url),
    );
    return response.conversations;
  }
  ```

**Checkpoint:** Frontend can pass search queries. No UI yet.

---

### Stage 3: Frontend — ChatHeader search UI
> **Files to edit:** `frontend/src/lib/components/chat/ChatHeader.svelte`, `frontend/src/App.svelte`

This is the main stage. The history button morphs into a search input when the dropdown is open.

- [x] **3a.** Add state variables and imports to ChatHeader
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` (script section, top)
  **What:** Add new state variables:
  ```typescript
  import { listConversations } from "../../api/client";  // add to existing import

  let searchQuery = "";
  let searchResults: ConversationSummary[] | null = null;
  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  let searching = false;
  let searchInputEl: HTMLInputElement | undefined;
  ```

- [x] **3b.** Add `dispatchSearch()` debounce function
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` (script section, after `handleRegenerateTitle`)
  **What:** Debounced search function:
  ```typescript
  function dispatchSearch(): void {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    if (!searchQuery.trim()) {
      searchResults = null;
      searching = false;
      return;
    }
    searching = true;
    searchDebounceTimer = setTimeout(async () => {
      try {
        searchResults = await listConversations(50, 0, searchQuery.trim());
      } catch (error) {
        console.error("Search failed", error);
        searchResults = null;
      } finally {
        searching = false;
      }
    }, 300);
  }
  ```

- [x] **3c.** Update reactive `dateGroups` to use search results
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` (~line after `groupByDate`)
  **What:** Change from:
  ```typescript
  $: dateGroups = groupByDate(conversations);
  ```
  to:
  ```typescript
  $: displayConversations = searchResults ?? conversations;
  $: dateGroups = groupByDate(displayConversations);
  ```

- [x] **3d.** Clear search state on dropdown close
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` → `handleClickOutside()`, `handleLoadConversation()`, and `toggleHistory()`
  **What:** Add a helper function and call it whenever the dropdown closes:
  ```typescript
  function clearSearch(): void {
    searchQuery = "";
    searchResults = null;
    searching = false;
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  }
  ```
  Call `clearSearch()` in:
  - `handleClickOutside()` — when closing the dropdown
  - `handleLoadConversation()` — before `historyOpen = false`
  - `toggleHistory()` — when `historyOpen` becomes false (i.e., when toggling off)

- [x] **3e.** Replace History button with morphing input (desktop)
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` → desktop `.history-wrapper` (~line 860)
  **What:** Replace the current button:
  ```svelte
  <div class="history-wrapper" bind:this={historyWrapperEl}>
    {#if historyOpen}
      <div class="history-search-wrapper">
        <svg class="history-search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/>
          <path d="m21 21-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <input
          class="history-search-input"
          type="text"
          placeholder="Search..."
          bind:value={searchQuery}
          bind:this={searchInputEl}
          on:input={dispatchSearch}
          on:keydown={(e) => { if (e.key === 'Escape') { historyOpen = false; clearSearch(); } }}
        />
        <button
          class="history-search-close"
          type="button"
          aria-label="Close history"
          on:click={() => { historyOpen = false; clearSearch(); }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>
      </div>
    {:else}
      <button
        class="btn btn-ghost btn-small"
        type="button"
        on:click={toggleHistory}
        aria-label="Conversation history"
        title="Conversation history"
        aria-expanded={historyOpen}
      >
        History
      </button>
    {/if}
    {#if historyOpen}
      <div class="history-dropdown" style={dropdownStyle} role="menu">
        <!-- dropdown content (unchanged structure) -->
      </div>
    {/if}
  </div>
  ```

- [x] **3f.** Replace History button with morphing input (PWA)
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` → PWA `.history-wrapper.pwa-full-row` (~line 556)
  **What:** Same pattern as desktop but using the PWA-mode styling (full-width, icon+text button).

- [x] **3g.** Update dropdown "empty" message
  **File:** Both dropdown instances (PWA + desktop)
  **What:** Distinguish between "no saved conversations" and "no search results":
  ```svelte
  {#if displayConversations.length === 0}
    <div class="history-empty">
      {#if searchQuery.trim()}
        {#if searching}
          Searching…
        {:else}
          No matching conversations
        {/if}
      {:else}
        No saved conversations
      {/if}
    </div>
  {:else}
    {#each dateGroups as group}
      ...
    {/each}
  {/if}
  ```

- [x] **3h.** Auto-focus the search input when dropdown opens
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` → `toggleHistory()`
  **What:** After setting `historyOpen = true` and computing `dropdownStyle`, use `tick()` to wait for DOM update, then focus the input:
  ```typescript
  import { tick } from 'svelte';  // add to existing svelte imports

  async function toggleHistory(): Promise<void> {
    historyOpen = !historyOpen;
    if (historyOpen) {
      // ... existing dropdown positioning logic ...
      await tick();
      searchInputEl?.focus();
    } else {
      clearSearch();
    }
  }
  ```

**Checkpoint:** After Stage 3, the history button morphs into a search input. Typing searches conversations server-side with debounce. Closing the dropdown resets everything. Works on both desktop and PWA. Test manually.

---

### Stage 4: Styling
> **Files to edit:** `frontend/src/lib/components/chat/ChatHeader.svelte` (style section)

- [x] **4a.** Style the search wrapper and input
  **File:** `frontend/src/lib/components/chat/ChatHeader.svelte` → `<style>` section
  **What:** Add styles that match the existing dark theme:
  ```css
  /* ── History search ── */
  .history-search-wrapper {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.5rem;
    border-radius: 0.5rem;
    border: 1px solid rgba(37, 49, 77, 0.9);
    background: rgba(9, 14, 26, 0.92);
    transition: border-color 0.2s ease;
  }
  .history-search-wrapper:focus-within {
    border-color: #38bdf8;
  }
  .history-search-icon {
    flex-shrink: 0;
    color: #6b7f9e;
  }
  .history-search-input {
    flex: 1;
    min-width: 0;
    border: none;
    background: transparent;
    color: #f3f5ff;
    font: inherit;
    font-size: 0.85rem;
    outline: none;
    padding: 0.15rem 0;
  }
  .history-search-input::placeholder {
    color: #6b7f9e;
  }
  .history-search-close {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 22px;
    height: 22px;
    padding: 0;
    border: none;
    border-radius: 0.25rem;
    background: transparent;
    color: #6b7f9e;
    cursor: pointer;
    transition: color 0.12s ease, background 0.12s ease;
  }
  .history-search-close:hover {
    color: #c8d6ef;
    background: rgba(56, 189, 248, 0.12);
  }
  ```

- [x] **4b.** PWA-specific search styles
  **What:** The `.history-wrapper.pwa-full-row .history-search-wrapper` should be full-width to match the PWA button layout. Add:
  ```css
  .history-wrapper.pwa-full-row .history-search-wrapper {
    width: 100%;
  }
  ```

- [x] **4c.** Mobile responsive tweaks
  **What:** Inside `@media (max-width: 768px)`, ensure `.history-search-wrapper` is full-width and looks good in the drawer.

**Checkpoint:** Search input looks native to the existing dark theme. Focus state, hover states, placeholder all match the design system.

---

### Stage 5: Testing & polish
> **Files to edit:** Various

- [x] **5a.** Run all existing tests
  ```bash
  cd /home/human/REPOS/Backend_FastAPI && uv run pytest tests/ -x -q
  ```

- [x] **5b.** Test end-to-end manually
  - Open history dropdown → button morphs into search input, auto-focused
  - Type a keyword → results filter after 300ms, grouped by date
  - Clear the input → full list returns
  - Type a non-matching query → "No matching conversations" shown
  - Press Escape → dropdown closes, search resets
  - Click outside → dropdown closes, search resets
  - Click a search result → loads that conversation, dropdown closes
  - Works on mobile/PWA drawer mode
  - Click ✕ button → dropdown closes

- [x] **5c.** Build frontend
  ```bash
  cd frontend && npm run build && cd ..
  ```

- [x] **5d.** Deploy
  ```bash
  git add src/backend/ frontend/ tests/ docs/
  git commit -m "feat: conversation history search"
  git push
  ssh root@192.168.1.111 "cd /opt/backend-fastapi && git pull"
  ```

---

## File Reference

| File | Role | Changes |
|------|------|---------|
| `src/backend/repository.py` | DB layer | Add `search` param to `list_saved_conversations()` |
| `src/backend/routers/chat.py` | API | Add `search` query param to endpoint |
| `frontend/src/lib/api/client.ts` | API client | Add `search` param to `listConversations()` |
| `frontend/src/lib/components/chat/ChatHeader.svelte` | History UI | Morphing button→input, debounced search, styles |
| `frontend/src/App.svelte` | Root component | No changes needed (uses existing `conversations` prop) |
| `frontend/src/lib/api/types.ts` | Types | No changes needed |
| `tests/test_repository.py` | Tests | Add search tests |
| `tests/test_chat_router.py` | Tests | Add search endpoint test |

## Quick Start for a Fresh Session

1. Read this doc first
2. Start with whichever stage has the first unchecked item
3. Key files to read for context before each stage:
   - **Stage 1:** `src/backend/repository.py` (~line 813, `list_saved_conversations`), `src/backend/routers/chat.py` (~line 82, `list_conversations`)
   - **Stage 2:** `frontend/src/lib/api/client.ts` (~line 653, `listConversations`)
   - **Stage 3:** `frontend/src/lib/components/chat/ChatHeader.svelte` (full file — script, markup, styles), `frontend/src/App.svelte` (~line 395–445, ChatHeader usage)
   - **Stage 4:** ChatHeader.svelte `<style>` section (~line 1020 onwards)
   - **Stage 5:** Run tests, build, deploy
