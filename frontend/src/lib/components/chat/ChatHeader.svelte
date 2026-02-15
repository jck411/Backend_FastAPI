<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";
  import type { ConversationSummary } from "../../api/types";
  import { webSearchStore } from "../../chat/webSearchStore";
  import { presetsStore } from "../../stores/presets";

  interface SelectableModel {
    id: string;
    name?: string | null;
  }

  type ModelPickerComponent = typeof import("./ModelPicker.svelte").default;
  type WebSearchMenuComponent = typeof import("./WebSearchMenu.svelte").default;

  const dispatch = createEventDispatcher<{
    openExplorer: void;
    clear: void;
    modelChange: { id: string };
    openModelSettings: void;
    openSystemSettings: void;
    openKioskSettings: void;
    openCliSettings: void;
    openMcpServers: void;
    drawerToggle: { open: boolean };
    toggleSaved: void;
    loadConversation: { sessionId: string };
    deleteConversation: { sessionId: string };
  }>();

  export let selectableModels: SelectableModel[] = [];
  export let selectedModel = "";
  export let modelsLoading = false;
  export let modelsError: string | null = null;
  export let hasMessages = false;
  export let pwaMode = false;
  export let isSaved = false;
  export let conversations: ConversationSummary[] = [];
  let historyOpen = false;
  let historyWrapperEl: HTMLElement | undefined;
  let dropdownStyle = "";
  let ModelPicker: ModelPickerComponent | null = null;
  let WebSearchMenu: WebSearchMenuComponent | null = null;
  let modelPickerLoading = false;
  let webSearchMenuLoading = false;
  export let controlsOpen = false;
  let lastDrawerOpen: boolean | null = null;

  $: {
    if (lastDrawerOpen !== controlsOpen) {
      lastDrawerOpen = controlsOpen;
      dispatch("drawerToggle", { open: controlsOpen });
    }
  }

  function closeDrawer(): void {
    controlsOpen = false;
  }

  async function loadModelPicker(): Promise<void> {
    if (ModelPicker) return;
    modelPickerLoading = true;
    try {
      const module = await import("./ModelPicker.svelte");
      ModelPicker = module.default;
    } catch (error) {
      console.error("Failed to load ModelPicker", error);
    } finally {
      modelPickerLoading = false;
    }
  }

  async function loadWebSearchMenu(): Promise<void> {
    if (WebSearchMenu) return;
    webSearchMenuLoading = true;
    try {
      const module = await import("./WebSearchMenu.svelte");
      WebSearchMenu = module.default;
    } catch (error) {
      console.error("Failed to load WebSearchMenu", error);
    } finally {
      webSearchMenuLoading = false;
    }
  }

  onMount(() => {
    void loadModelPicker();
    void loadWebSearchMenu();
  });

  function handleExplorerClick(): void {
    closeDrawer();
    dispatch("openExplorer");
  }

  function handleClear(): void {
    closeDrawer();
    dispatch("clear");
  }

  function forwardModelChange(event: CustomEvent<{ id: string }>): void {
    dispatch("modelChange", event.detail);
  }

  function forwardOpenModelSettings(): void {
    if (!pwaMode) closeDrawer();
    dispatch("openModelSettings");
  }

  function forwardOpenSystemSettings(): void {
    if (!pwaMode) closeDrawer();
    dispatch("openSystemSettings");
  }

  function forwardOpenKioskSettings(): void {
    if (!pwaMode) closeDrawer();
    dispatch("openKioskSettings");
  }

  function forwardOpenCliSettings(): void {
    if (!pwaMode) closeDrawer();
    dispatch("openCliSettings");
  }

  function forwardOpenMcpServers(): void {
    if (!pwaMode) closeDrawer();
    dispatch("openMcpServers");
  }

  function handleToggleSaved(): void {
    dispatch("toggleSaved");
  }

  function toggleHistory(): void {
    historyOpen = !historyOpen;
    if (historyOpen && historyWrapperEl) {
      const rect = historyWrapperEl.getBoundingClientRect();
      const maxH = 400;
      const gap = 4;
      const dropW = 320;
      const spaceBelow = window.innerHeight - rect.bottom - gap;
      const spaceAbove = rect.top - gap;
      let top: number;
      let mh: number;
      if (spaceBelow >= 200 || spaceBelow >= spaceAbove) {
        top = rect.bottom + gap;
        mh = Math.min(maxH, spaceBelow);
      } else {
        mh = Math.min(maxH, spaceAbove);
        top = rect.top - gap - mh;
      }
      const left = Math.max(
        8,
        Math.min(rect.left, window.innerWidth - dropW - 8),
      );
      dropdownStyle = `position:fixed;top:${top}px;left:${left}px;max-height:${mh}px;width:${Math.min(dropW, window.innerWidth - 16)}px;`;
    }
  }

  function handleLoadConversation(sessionId: string): void {
    historyOpen = false;
    closeDrawer();
    dispatch("loadConversation", { sessionId });
  }

  function handleDeleteConversation(event: Event, sessionId: string): void {
    event.stopPropagation();
    dispatch("deleteConversation", { sessionId });
  }

  interface DateGroup {
    label: string;
    items: ConversationSummary[];
  }

  function groupByDate(items: ConversationSummary[]): DateGroup[] {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today.getTime() - 86400000);
    const weekAgo = new Date(today.getTime() - 7 * 86400000);
    const monthAgo = new Date(today.getTime() - 30 * 86400000);

    const groups: Record<string, ConversationSummary[]> = {};
    const order: string[] = [];

    function addToGroup(label: string, item: ConversationSummary) {
      if (!groups[label]) {
        groups[label] = [];
        order.push(label);
      }
      groups[label].push(item);
    }

    for (const item of items) {
      const dateStr = item.updated_at || item.created_at;
      if (!dateStr) {
        addToGroup("Older", item);
        continue;
      }
      const d = new Date(dateStr);
      if (d >= today) {
        addToGroup("Today", item);
      } else if (d >= yesterday) {
        addToGroup("Yesterday", item);
      } else if (d >= weekAgo) {
        addToGroup("Previous 7 Days", item);
      } else if (d >= monthAgo) {
        addToGroup("Previous 30 Days", item);
      } else {
        const monthLabel = d.toLocaleDateString("en-US", {
          month: "long",
          year: "numeric",
        });
        addToGroup(monthLabel, item);
      }
    }

    return order.map((label) => ({ label, items: groups[label] }));
  }

  $: dateGroups = groupByDate(conversations);

  function handleClickOutside(event: MouseEvent): void {
    if (!historyOpen) return;
    const target = event.target as HTMLElement;
    if (!target.closest(".history-wrapper")) {
      historyOpen = false;
    }
  }
</script>

<svelte:window on:click={handleClickOutside} />

<header
  class="topbar chat-header"
  data-pwa-mode={pwaMode}
  data-drawer-open={controlsOpen}
>
  <!-- Mobile hamburger bar (≤768px) -->
  <div class="mobile-bar">
    <button
      class="hamburger-btn"
      type="button"
      aria-label={controlsOpen ? "Close menu" : "Open menu"}
      aria-expanded={controlsOpen}
      aria-controls="chat-header-controls"
      on:click={() => (controlsOpen = !controlsOpen)}
    >
      {#if controlsOpen}
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M15 19l-7-7 7-7"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      {:else}
        <svg
          width="22"
          height="22"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M4 6h16M4 12h16M4 18h16"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
          />
        </svg>
      {/if}
    </button>
    <span class="mobile-model-name">
      {#if selectedModel}
        {selectableModels.find((m) => m.id === selectedModel)?.name ??
          selectedModel.split("/").pop() ??
          "Chat"}
      {:else}
        Chat
      {/if}
    </span>
    <button
      class="btn btn-ghost btn-small mobile-save"
      class:active={isSaved}
      type="button"
      on:click={handleToggleSaved}
      aria-label={isSaved ? "Conversation saved" : "Save conversation"}
      title={isSaved ? "Conversation saved" : "Save conversation"}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <polyline
          points="17 21 17 13 7 13 7 21"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <polyline
          points="7 3 7 8 15 8"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>
    <button
      class="btn btn-ghost btn-small mobile-clear"
      type="button"
      on:click={handleClear}
      disabled={!hasMessages}
      aria-label="Clear conversation"
    >
      Clear
    </button>
  </div>

  <!-- Desktop topbar content -->
  <div class="topbar-content">
    <div class="controls" id="chat-header-controls">
      {#if $presetsStore.applying}
        <button
          class="preset-badge applying"
          type="button"
          on:click={forwardOpenSystemSettings}
          aria-live="polite"
          title={`Applying ${$presetsStore.applying}… (open system settings to manage presets)`}
        >
          <span class="spinner" aria-hidden="true"></span>
          <span class="label">Preset</span>
          <span class="name" title={$presetsStore.applying}
            >{$presetsStore.applying}</span
          >
        </button>
      {:else if $presetsStore.lastApplied}
        <button
          class="preset-badge"
          type="button"
          on:click={forwardOpenSystemSettings}
          aria-live="polite"
          title={`Active preset: ${$presetsStore.lastApplied} (open system settings to manage)`}
        >
          <span class="dot" aria-hidden="true"></span>
          <span class="label">Preset</span>
          <span class="name" title={$presetsStore.lastApplied}
            >{$presetsStore.lastApplied}</span
          >
        </button>
      {/if}

      <button
        class="btn btn-ghost btn-small explorer"
        type="button"
        on:click={handleExplorerClick}
      >
        Explorer
      </button>

      {#if ModelPicker}
        <svelte:component
          this={ModelPicker}
          {selectableModels}
          {selectedModel}
          {modelsLoading}
          {modelsError}
          on:modelChange={forwardModelChange}
        />
      {:else}
        <div
          class="model-picker-loading"
          data-loading={modelPickerLoading}
          aria-hidden="true"
        >
          <select disabled>
            <option>Loading…</option>
          </select>
        </div>
      {/if}

      {#if WebSearchMenu}
        <svelte:component this={WebSearchMenu} {pwaMode} />
      {:else}
        <div
          class="web-search-loading"
          data-loading={webSearchMenuLoading}
          aria-hidden="true"
        >
          <button
            class="btn btn-ghost btn-small web-search-summary"
            type="button"
            disabled
          >
            <span>Web search</span>
            <span class="status" data-enabled={$webSearchStore.enabled}>
              {$webSearchStore.enabled ? "On" : "Off"}
            </span>
          </button>
        </div>
      {/if}

      <button
        class="btn btn-ghost btn-small"
        type="button"
        on:click={forwardOpenModelSettings}
        aria-label="Model settings"
        title="Model settings"
        disabled={modelsLoading || !selectedModel}
      >
        <span>Model</span>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.89 3.31.876 2.42 2.42a1.724 1.724 0 0 0 1.066 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.572c.89 1.543-.876 3.31-2.42 2.42a1.724 1.724 0 0 0-2.572 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.89-3.31-.876-2.42-2.42a1.724 1.724 0 0 0-1.066-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.572c-.89-1.543.876-3.31 2.42-2.42.965.557 2.185.21 2.573-1.066Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>

      {#if pwaMode}
        <button
          class="btn btn-ghost btn-small pwa-full-row mcp-btn"
          type="button"
          on:click={forwardOpenMcpServers}
          aria-label="MCP servers"
          title="MCP servers"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 195 195"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <path
              d="M25 97.8528L92.8823 29.9706C102.255 20.598 117.451 20.598 126.823 29.9706V29.9706C136.196 39.3431 136.196 54.5391 126.823 63.9117L75.5581 115.177"
              stroke="currentColor"
              stroke-width="12"
              stroke-linecap="round"
            />
            <path
              d="M76.2653 114.47L126.823 63.9117C136.196 54.5391 151.392 54.5391 160.765 63.9117L161.118 64.2652C170.491 73.6378 170.491 88.8338 161.118 98.2063L99.7248 159.6C96.6006 162.724 96.6006 167.789 99.7248 170.913L112.331 183.52"
              stroke="currentColor"
              stroke-width="12"
              stroke-linecap="round"
            />
            <path
              d="M109.853 46.9411L59.6482 97.1457C50.2757 106.518 50.2757 121.714 59.6482 131.087V131.087C69.0208 140.459 84.2168 140.459 93.5894 131.087L143.794 80.8822"
              stroke="currentColor"
              stroke-width="12"
              stroke-linecap="round"
            />
          </svg>
          <span>MCP Servers</span>
        </button>

        <button
          class="btn btn-ghost btn-small pwa-full-row system-settings"
          type="button"
          on:click={forwardOpenSystemSettings}
          aria-label="System settings"
          title="System settings"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <rect
              x="3"
              y="4"
              width="18"
              height="12"
              rx="2"
              stroke="currentColor"
              stroke-width="1.5"
            />
            <path
              d="M8 20h8"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <path
              d="M3 8h18"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
          <span>System Settings</span>
        </button>

        <div class="history-wrapper pwa-full-row">
          <button
            class="btn btn-ghost btn-small pwa-full-row"
            type="button"
            on:click={toggleHistory}
            aria-label="Conversation history"
            title="Conversation history"
            aria-expanded={historyOpen}
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <circle
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <polyline
                points="12 6 12 12 16 14"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span>History</span>
          </button>
          {#if historyOpen}
            <div class="history-dropdown" role="menu">
              {#if conversations.length === 0}
                <div class="history-empty">No saved conversations</div>
              {:else}
                {#each dateGroups as group}
                  <div class="history-group-label">{group.label}</div>
                  {#each group.items as conv}
                    <div
                      class="history-item"
                      role="menuitem"
                      tabindex="0"
                      on:click={() => handleLoadConversation(conv.session_id)}
                      on:keydown={(e) => {
                        if (e.key === "Enter" || e.key === " ")
                          handleLoadConversation(conv.session_id);
                      }}
                    >
                      <span class="history-item-title"
                        >{conv.title || conv.preview || "Untitled"}</span
                      >
                      <span class="history-item-meta"
                        >{conv.message_count} msgs</span
                      >
                      <button
                        class="history-item-delete"
                        type="button"
                        aria-label="Delete conversation"
                        on:click={(e) =>
                          handleDeleteConversation(e, conv.session_id)}
                      >
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                          aria-hidden="true"
                        >
                          <path
                            d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14"
                            stroke="currentColor"
                            stroke-width="1.5"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                          />
                        </svg>
                      </button>
                    </div>
                  {/each}
                {/each}
              {/if}
            </div>
          {/if}
        </div>
      {/if}

      <div class="icon-row">
        {#if !pwaMode}
          <button
            class="btn btn-ghost btn-small settings-icon mcp-btn"
            type="button"
            on:click={forwardOpenMcpServers}
            aria-label="MCP servers"
            title="MCP servers"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 195 195"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M25 97.8528L92.8823 29.9706C102.255 20.598 117.451 20.598 126.823 29.9706V29.9706C136.196 39.3431 136.196 54.5391 126.823 63.9117L75.5581 115.177"
                stroke="currentColor"
                stroke-width="12"
                stroke-linecap="round"
              />
              <path
                d="M76.2653 114.47L126.823 63.9117C136.196 54.5391 151.392 54.5391 160.765 63.9117L161.118 64.2652C170.491 73.6378 170.491 88.8338 161.118 98.2063L99.7248 159.6C96.6006 162.724 96.6006 167.789 99.7248 170.913L112.331 183.52"
                stroke="currentColor"
                stroke-width="12"
                stroke-linecap="round"
              />
              <path
                d="M109.853 46.9411L59.6482 97.1457C50.2757 106.518 50.2757 121.714 59.6482 131.087V131.087C69.0208 140.459 84.2168 140.459 93.5894 131.087L143.794 80.8822"
                stroke="currentColor"
                stroke-width="12"
                stroke-linecap="round"
              />
            </svg>
          </button>

          <button
            class="btn btn-ghost btn-small settings-icon system-settings"
            type="button"
            on:click={forwardOpenSystemSettings}
            aria-label="System settings"
            title="System settings"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <rect
                x="3"
                y="4"
                width="18"
                height="12"
                rx="2"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <path
                d="M8 20h8"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
              <path
                d="M3 8h18"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        {/if}

        {#if !pwaMode}
          <button
            class="btn btn-ghost btn-small settings-icon kiosk-btn"
            type="button"
            on:click={forwardOpenKioskSettings}
            aria-label="Kiosk settings"
            title="Kiosk settings"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <!-- Screen/display -->
              <rect
                x="4"
                y="2"
                width="16"
                height="12"
                rx="1.5"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <!-- Stand -->
              <path
                d="M12 14v4M8 22h8M8 18h8"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>

          <button
            class="btn btn-ghost btn-small settings-icon cli-btn"
            type="button"
            on:click={forwardOpenCliSettings}
            aria-label="CLI settings"
            title="CLI settings"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M4 17l6-6-6-6M12 19h8"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>

          <button
            class="btn btn-ghost btn-small save-toggle"
            class:active={isSaved}
            type="button"
            on:click={handleToggleSaved}
            aria-label={isSaved ? "Conversation saved" : "Save conversation"}
            title={isSaved ? "Conversation saved" : "Save conversation"}
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <path
                d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <polyline
                points="17 21 17 13 7 13 7 21"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <polyline
                points="7 3 7 8 15 8"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>

          <div class="history-wrapper" bind:this={historyWrapperEl}>
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
            {#if historyOpen}
              <div class="history-dropdown" style={dropdownStyle} role="menu">
                {#if conversations.length === 0}
                  <div class="history-empty">No saved conversations</div>
                {:else}
                  {#each dateGroups as group}
                    <div class="history-group-label">{group.label}</div>
                    {#each group.items as conv}
                      <div
                        class="history-item"
                        role="menuitem"
                        tabindex="0"
                        on:click={() => handleLoadConversation(conv.session_id)}
                        on:keydown={(e) => {
                          if (e.key === "Enter" || e.key === " ")
                            handleLoadConversation(conv.session_id);
                        }}
                      >
                        <span class="history-item-title"
                          >{conv.title || conv.preview || "Untitled"}</span
                        >
                        <span class="history-item-meta"
                          >{conv.message_count} msgs</span
                        >
                        <button
                          class="history-item-delete"
                          type="button"
                          aria-label="Delete conversation"
                          on:click={(e) =>
                            handleDeleteConversation(e, conv.session_id)}
                        >
                          <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            xmlns="http://www.w3.org/2000/svg"
                            aria-hidden="true"
                          >
                            <path
                              d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14"
                              stroke="currentColor"
                              stroke-width="1.5"
                              stroke-linecap="round"
                              stroke-linejoin="round"
                            />
                          </svg>
                        </button>
                      </div>
                    {/each}
                  {/each}
                {/if}
              </div>
            {/if}
          </div>

          <button
            class="btn btn-ghost btn-small"
            type="button"
            on:click={handleClear}
            disabled={!hasMessages}
          >
            Clear
          </button>
        {/if}
      </div>
    </div>
  </div>

  <!-- Mobile drawer backdrop -->
  {#if controlsOpen}
    <button
      class="drawer-backdrop"
      type="button"
      aria-label="Close menu"
      tabindex="-1"
      on:click={() => (controlsOpen = false)}
    ></button>
  {/if}
</header>

<style>
  /* ── Base (desktop) ── */
  .topbar {
    height: var(--header-h);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    background: transparent;
    position: relative;
    z-index: 20;
    padding: 2rem 2rem 1rem;
  }
  .topbar-content {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
  }
  .mobile-bar {
    display: none;
  }
  .drawer-backdrop {
    display: none;
  }
  .controls {
    display: flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: nowrap;
  }
  .controls > * {
    flex: 0 0 auto;
  }
  .pwa-full-row {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
  }
  .icon-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  :global(.chat-header .controls .model-picker) {
    display: flex;
  }
  :global(.chat-header .controls .model-picker),
  :global(.chat-header .controls .web-search) {
    width: auto;
  }
  .preset-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    border: 1px solid #25314d;
    background: rgba(12, 19, 34, 0.7);
    color: #c8d6ef;
    font-size: 0.8rem;
    white-space: nowrap;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease,
      box-shadow 0.2s ease;
  }
  .preset-badge:hover,
  .preset-badge:focus-visible {
    border-color: #38bdf8;
    color: #f2f6ff;
    background: rgba(12, 22, 40, 0.85);
    outline: none;
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25);
  }
  .preset-badge .label {
    text-transform: uppercase;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    color: #9fb3d8;
  }
  .preset-badge .name {
    max-width: 14ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #e5edff;
  }
  .preset-badge .dot {
    width: 0.4rem;
    height: 0.4rem;
    border-radius: 999px;
    background: #22c55e;
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.15);
  }
  .preset-badge.applying .spinner {
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 999px;
    border: 2px solid rgba(148, 187, 233, 0.25);
    border-top-color: #38bdf8;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
  :global(.chat-header .controls select) {
    appearance: none;
    padding: 0.45rem 2rem 0.45rem 0.75rem;
    border-radius: 0.5rem;
    background-color: rgba(9, 14, 26, 0.92);
    color: #f3f5ff;
    border: 1px solid rgba(37, 49, 77, 0.9);
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease;
    background-image: url('data:image/svg+xml,%3Csvg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Cpath d="M7 8l3 3 3-3" stroke="%23d4daee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/%3E%3C/svg%3E');
    background-repeat: no-repeat;
    background-position: right 0.65rem center;
    background-size: 0.9rem;
    min-width: 160px;
    font: inherit;
  }
  :global(.chat-header .controls select:hover) {
    border-color: #38bdf8;
    background-color: rgba(12, 19, 34, 0.95);
    color: #f8fafc;
  }
  :global(.chat-header .controls select:focus) {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
    border-color: #38bdf8;
    box-shadow: none;
  }
  :global(.chat-header .controls select:disabled) {
    opacity: 0.6;
    cursor: not-allowed;
    background-color: rgba(9, 14, 26, 0.6);
  }
  :global(.chat-header .controls select option) {
    background: #0a101a;
    color: #f3f5ff;
  }
  :global(.chat-header .controls .btn) {
    white-space: nowrap;
  }
  :global(.chat-header .controls .btn.settings-icon svg) {
    width: 1.05rem;
    height: 1.05rem;
  }
  .model-picker-loading,
  .web-search-loading {
    display: inline-flex;
    align-items: center;
    gap: 0.75rem;
  }
  .web-search-loading .status {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
    border: 1px solid rgba(62, 90, 140, 0.6);
    color: #9fb3d8;
  }

  /* ── Tablet breakpoint ── */
  @media (max-width: 1280px) {
    .topbar {
      height: auto;
      padding: 0.75rem 1.5rem 1rem;
    }
    .topbar-content {
      flex-direction: column;
      align-items: stretch;
      gap: 0.75rem;
      width: 100%;
      max-width: 900px;
      margin: 0 auto;
    }
    .controls {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      align-items: stretch;
      width: 100%;
      max-width: 900px;
      margin: 0 auto;
      gap: 0.75rem;
      justify-items: stretch;
    }
    .controls > * {
      width: 100%;
      min-width: 0;
    }
    :global(.chat-header .controls .btn),
    :global(.chat-header .controls select),
    .preset-badge,
    .model-picker-loading,
    .web-search-loading,
    :global(.chat-header .controls .model-picker),
    :global(.chat-header .controls .web-search) {
      width: 100%;
    }
    :global(.chat-header .controls .btn),
    .preset-badge {
      justify-content: center;
    }
    .icon-row {
      grid-column: 1 / -1;
      justify-content: center;
      flex-wrap: nowrap;
    }
    .icon-row :global(.btn) {
      width: auto;
    }
    :global(.chat-header .controls select) {
      min-width: 0;
      text-align: left;
    }
    :global(.chat-header .controls .explorer) {
      grid-column: 1;
    }
    :global(.chat-header .controls .model-picker),
    .model-picker-loading {
      grid-column: 2;
    }
    .preset-badge {
      grid-column: 1 / -1;
      order: -1;
    }
    .web-search-loading {
      justify-content: center;
    }
  }
  @media (max-width: 1024px) {
    .topbar {
      padding: 0.75rem 1.25rem 1rem;
    }
    .controls {
      gap: 0.65rem;
    }
  }

  /* ── Mobile: hamburger + slide-out drawer ── */
  @media (max-width: 768px) {
    .topbar {
      height: auto;
      padding: 0;
      flex-direction: column;
      align-items: stretch;
    }

    /* Thin always-visible bar */
    .mobile-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.5rem 0.75rem;
      padding-top: max(0.5rem, env(safe-area-inset-top, 0));
      background: rgba(4, 6, 13, 0.97);
      border-bottom: 1px solid rgba(37, 49, 77, 0.5);
      position: relative;
      z-index: 52;
    }
    .hamburger-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      padding: 0;
      border: none;
      border-radius: 0.5rem;
      background: transparent;
      color: #c8d6ef;
      cursor: pointer;
      transition:
        background 0.15s ease,
        color 0.15s ease;
      flex-shrink: 0;
    }
    .hamburger-btn:hover,
    .hamburger-btn:focus-visible {
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      outline: none;
    }
    .mobile-model-name {
      flex: 1;
      text-align: center;
      font-size: 0.8rem;
      color: #9fb3d8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      padding: 0 0.25rem;
    }
    .mobile-clear {
      flex-shrink: 0;
      font-size: 0.78rem;
      padding: 0.3rem 0.7rem;
    }

    /* Desktop topbar-content becomes the drawer */
    .topbar-content {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: min(300px, 80vw);
      background: rgba(6, 10, 20, 0.98);
      border-right: 1px solid rgba(37, 49, 77, 0.6);
      padding: 1rem;
      padding-top: calc(max(0.5rem, env(safe-area-inset-top, 0)) + 3rem);
      overflow-y: auto;
      z-index: 51;
      transform: translateX(-100%);
      transition: transform 0.25s ease;
      flex-direction: column;
      backdrop-filter: blur(16px);
    }
    .topbar[data-drawer-open="true"] .topbar-content {
      transform: translateX(0);
    }

    .controls {
      display: flex;
      flex-direction: column;
      gap: 0.65rem;
      max-width: 100%;
    }
    .controls > * {
      width: 100%;
      min-width: 0;
    }
    :global(.chat-header .controls .btn),
    :global(.chat-header .controls select),
    .preset-badge,
    .model-picker-loading,
    .web-search-loading,
    :global(.chat-header .controls .model-picker),
    :global(.chat-header .controls .web-search) {
      width: 100%;
    }
    :global(.chat-header .controls .btn) {
      justify-content: flex-start;
      padding: 0.6rem 0.75rem;
    }
    :global(.chat-header .controls select) {
      min-width: 0;
      width: 100%;
    }
    .icon-row {
      flex-wrap: wrap;
      gap: 0.5rem;
      justify-content: flex-start;
    }
    .icon-row :global(.btn) {
      width: auto;
    }
    .preset-badge {
      width: 100%;
      justify-content: flex-start;
    }

    /* Backdrop overlay */
    .drawer-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      z-index: 50;
      background: rgba(0, 0, 0, 0.5);
      border: none;
      padding: 0;
      cursor: default;
    }
    .topbar[data-drawer-open="true"] .drawer-backdrop {
      display: block;
    }
  }

  @media (max-width: 480px) {
    .preset-badge .name {
      max-width: 20ch;
    }
  }

  @media (max-width: 768px) and (prefers-reduced-motion: reduce) {
    .topbar-content {
      transition: none;
    }
  }

  /* ── Save toggle ── */
  .save-toggle,
  .mobile-save {
    color: #9fb3d8;
    transition:
      color 0.15s ease,
      border-color 0.15s ease,
      box-shadow 0.15s ease;
  }
  .save-toggle:hover,
  .mobile-save:hover {
    color: #38bdf8;
  }
  .save-toggle.active,
  .mobile-save.active {
    color: #22c55e;
    border-color: #22c55e;
    box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.35);
  }

  /* ── History wrapper + dropdown ── */
  .history-wrapper {
    position: relative;
  }
  .history-dropdown {
    position: absolute;
    top: 100%;
    right: 0;
    min-width: 280px;
    max-width: 360px;
    max-height: 400px;
    overflow-y: auto;
    background: rgba(9, 14, 26, 0.97);
    border: 1px solid rgba(37, 49, 77, 0.9);
    border-radius: 0.5rem;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 100;
    padding: 0.5rem 0;
    margin-top: 0.25rem;
  }
  .history-empty {
    padding: 1rem;
    text-align: center;
    color: #6b7f9e;
    font-size: 0.85rem;
  }
  .history-group-label {
    padding: 0.5rem 0.75rem 0.25rem;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #6b7f9e;
    font-weight: 600;
  }
  .history-item {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.5rem 0.75rem;
    border: none;
    background: transparent;
    color: #c8d6ef;
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
    text-align: left;
    transition: background 0.12s ease;
  }
  .history-item:hover {
    background: rgba(56, 189, 248, 0.08);
  }
  .history-item-title {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .history-item-meta {
    flex-shrink: 0;
    font-size: 0.72rem;
    color: #6b7f9e;
  }
  .history-item-delete {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    padding: 0;
    border: none;
    border-radius: 0.25rem;
    background: transparent;
    color: #6b7f9e;
    cursor: pointer;
    transition:
      color 0.12s ease,
      background 0.12s ease;
  }
  .history-item-delete:hover {
    color: #ef4444;
    background: rgba(239, 68, 68, 0.12);
  }

  /* ── PWA drawer history dropdown: always inline below the button ── */
  .history-wrapper.pwa-full-row {
    position: static;
    display: flex;
    flex-direction: column;
  }
  .history-wrapper.pwa-full-row .history-dropdown {
    position: static;
    min-width: 0;
    max-width: 100%;
    width: 100%;
    max-height: 250px;
    margin-top: 0.25rem;
    box-shadow: none;
    border-left: none;
    border-right: none;
    border-radius: 0;
    background: rgba(6, 10, 20, 0.95);
    right: auto;
    top: auto;
  }
</style>
