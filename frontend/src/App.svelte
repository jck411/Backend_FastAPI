<script lang="ts">
  import { afterUpdate, onMount } from "svelte";
  import ModelExplorer from "./lib/components/model-explorer/ModelExplorer.svelte";
  import { chatStore } from "./lib/stores/chat";
  import { modelStore } from "./lib/stores/models";

  const { sendMessage, cancelStream, clearConversation, setModel } = chatStore;
  const {
    loadModels,
    models: modelsStore,
    loading: modelsLoading,
    error: modelsError,
    filtered: filteredModels,
    activeFilters,
  } = modelStore;

  let prompt = "";
  let chatLog: HTMLElement | null = null;
  let lastMessageCount = 0;
  let explorerOpen = false;
  let sidebarCollapsed = false;

  onMount(() => {
    loadModels();
  });

  afterUpdate(() => {
    const messageCount = $chatStore.messages.length;
    if (messageCount !== lastMessageCount) {
      lastMessageCount = messageCount;
      if (chatLog) {
        chatLog.scrollTop = chatLog.scrollHeight;
      }
    }
  });

  function handleSubmit() {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    sendMessage(trimmed);
    prompt = "";
  }

  function handleModelChange(event: Event) {
    const target = event.target as HTMLSelectElement | null;
    if (!target) return;
    setModel(target.value);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  function openExplorer() {
    explorerOpen = true;
  }

  function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
  }

  function handleExplorerSelect(event: CustomEvent<{ id: string }>) {
    const nextModel = event.detail.id;
    if (nextModel) {
      setModel(nextModel);
    }
  }

  function formatToolCallList(
    toolCalls: Array<Record<string, unknown>> | null | undefined,
  ): string | null {
    if (!toolCalls || toolCalls.length === 0) {
      return null;
    }
    const labels = toolCalls
      .map((call) => {
        if (!call || typeof call !== "object") {
          return null;
        }
        const entry = call as Record<string, unknown>;
        const fn = entry.function as Record<string, unknown> | undefined;
        const functionName =
          (fn && typeof fn.name === "string" && fn.name) ||
          (typeof entry.name === "string" && entry.name) ||
          (typeof entry.id === "string" && entry.id) ||
          null;
        return functionName;
      })
      .filter((value): value is string => Boolean(value));
    return labels.length ? labels.join(", ") : null;
  }

  $: selectableModels = (() => {
    const active = $activeFilters;
    const base = active ? $filteredModels : $modelsStore;
    if (!base || base.length === 0) {
      if (!active) {
        return [];
      }
    }

    const selectedId = $chatStore.selectedModel;
    if (!selectedId) {
      return base;
    }
    const exists = base.some((model) => model.id === selectedId);
    if (exists) {
      return base;
    }
    const fallback = $modelsStore.find((model) => model.id === selectedId);
    if (!fallback) {
      return base;
    }
    return [fallback, ...base.filter((model) => model.id !== selectedId)];
  })();
</script>

<ModelExplorer bind:open={explorerOpen} on:select={handleExplorerSelect} />

<main class="app-shell" class:sidebar-collapsed={sidebarCollapsed}>
  <header class="hero">
    <div class="hero-actions">
      <label class="model-select">
        <span class="visually-hidden">Active model</span>
        <select
          on:change={handleModelChange}
          bind:value={$chatStore.selectedModel}
          disabled={$modelsLoading}
        >
          {#if $modelsLoading}
            <option>Loading models…</option>
          {:else if $modelsError}
            <option disabled>{`Failed to load models (${$modelsError})`}</option
            >
          {:else if selectableModels.length === 0}
            <option disabled>
              {#if $activeFilters}
                No models match current filters
              {:else}
                No models available
              {/if}
            </option>
          {:else}
            {#each selectableModels as model (model.id)}
              <option value={model.id}>
                {model.name ?? model.id}
              </option>
            {/each}
          {/if}
        </select>
      </label>
      <button
        type="button"
        class="ghost"
        on:click={openExplorer}
        disabled={$modelsLoading}
      >
        Explorer
      </button>
      <button
        class="clear"
        type="button"
        on:click={clearConversation}
        disabled={$chatStore.messages.length === 0}
      >
        Clear Chat
      </button>
      <button
        type="button"
        class="ghost subtle toggle-sidebar"
        on:click={toggleSidebar}
        aria-controls="threads-sidebar"
        aria-expanded={!sidebarCollapsed}
      >
        {sidebarCollapsed ? "Show Sidebar" : "Hide Sidebar"}
      </button>
    </div>
  </header>

  <div class="layout-grid">
    <aside
      id="threads-sidebar"
      class="sidebar"
      aria-label="Threads history sidebar"
      aria-hidden={sidebarCollapsed}
    >
      <span class="visually-hidden">Threads history sidebar placeholder.</span>
      <div class="sidebar-surface" aria-hidden="true"></div>
    </aside>

    <section class="chat-surface" aria-label="Active chat">
      <header class="chat-header">
        {#if $chatStore.isStreaming}
          <span class="status-pill live">Live · Streaming</span>
        {/if}
      </header>

      <section class="conversation" bind:this={chatLog} aria-live="polite">
        {#if $chatStore.messages.length === 0}
          <p class="placeholder">Send a message to start the conversation.</p>
        {:else}
          {#each $chatStore.messages as message (message.id)}
            <article class={`message ${message.role}`}>
              <header>{message.role}</header>
              <p>{message.content}</p>
              {#if message.pending}
                <span class="pending">…</span>
              {/if}
              {#if message.details}
                {#if message.details.model || message.details.finishReason || message.details.generationId || message.details.toolName || message.details.toolStatus || (message.details.toolCalls && message.details.toolCalls.length)}
                  <dl class="meta">
                    {#if message.details.model}
                      <div>
                        <dt>Model</dt>
                        <dd>{message.details.model}</dd>
                      </div>
                    {/if}
                    {#if message.details.finishReason}
                      <div>
                        <dt>Finish</dt>
                        <dd>{message.details.finishReason}</dd>
                      </div>
                    {/if}
                    {#if message.details.generationId}
                      <div>
                        <dt>Generation</dt>
                        <dd>{message.details.generationId}</dd>
                      </div>
                    {/if}
                    {#if message.details.toolCalls && message.details.toolCalls.length}
                      {#if formatToolCallList(message.details.toolCalls)}
                        <div>
                          <dt>Tool Calls</dt>
                          <dd>
                            {formatToolCallList(message.details.toolCalls)}
                          </dd>
                        </div>
                      {/if}
                    {/if}
                    {#if message.details.toolName}
                      <div>
                        <dt>Tool</dt>
                        <dd>{message.details.toolName}</dd>
                      </div>
                    {/if}
                    {#if message.details.toolStatus}
                      <div>
                        <dt>Status</dt>
                        <dd>{message.details.toolStatus}</dd>
                      </div>
                    {/if}
                  </dl>
                {/if}
                {#if message.details.reasoning && message.details.reasoning.length}
                  <div class="reasoning">
                    <span class="reasoning-label">Reasoning</span>
                    <ul>
                      {#each message.details.reasoning as segment, index (index)}
                        <li>
                          {#if segment.type}
                            <span class="reasoning-type">{segment.type}</span>
                          {/if}
                          <span>{segment.text}</span>
                        </li>
                      {/each}
                    </ul>
                  </div>
                {/if}
              {/if}
            </article>
          {/each}
        {/if}
      </section>

      <form class="composer" on:submit|preventDefault={handleSubmit}>
        <label class="visually-hidden" for="chat-input">Message</label>
        <textarea
          id="chat-input"
          rows="4"
          bind:value={prompt}
          on:keydown={handleKeydown}
          placeholder={$chatStore.isStreaming
            ? "Waiting for response…"
            : "Ask the assistant anything…"}
          aria-disabled={$chatStore.isStreaming}
          aria-describedby="composer-hint"
        ></textarea>
        <div class="actions">
          {#if $chatStore.isStreaming}
            <button type="button" class="secondary" on:click={cancelStream}>
              Stop
            </button>
          {/if}
          <button
            type="submit"
            class="primary"
            disabled={!prompt.trim() || $chatStore.isStreaming}
          >
            Send
          </button>
        </div>
        <p id="composer-hint" class="composer-hint">
          Press Shift + Enter for a new line.
        </p>
      </form>

      {#if $chatStore.error}
        <p class="error" role="alert">{$chatStore.error}</p>
      {/if}
    </section>
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    font-family:
      "Inter",
      system-ui,
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      sans-serif;
    background: radial-gradient(
      circle at top,
      #162135 0%,
      #05070f 55%,
      #04060d 100%
    );
    color: #f3f5ff;
    min-height: 100vh;
  }

  .app-shell {
    max-width: 1240px;
    margin: 0 auto;
    padding: 2.25rem 2rem 3rem;
    display: grid;
    gap: 1.85rem;
  }

  .hero {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .hero-actions {
    display: inline-flex;
    gap: 0.75rem;
    align-items: center;
    flex-wrap: wrap;
  }

  .model-select {
    display: inline-flex;
    align-items: center;
  }

  .model-select select {
    appearance: none;
    min-width: 220px;
    padding: 0.6rem 0.9rem;
    border-radius: 0.9rem;
    border: 1px solid rgba(58, 85, 126, 0.8);
    background: rgba(4, 8, 18, 0.85);
    color: inherit;
    font-size: 0.95rem;
  }

  .model-select select:focus {
    outline: 2px solid rgba(56, 189, 248, 0.65);
    outline-offset: 2px;
  }

  .clear,
  .ghost,
  .primary,
  .secondary {
    border-radius: 999px;
    border: 1px solid transparent;
    cursor: pointer;
    font-weight: 600;
    transition:
      transform 0.15s ease,
      border-color 0.2s ease,
      background 0.2s ease;
  }

  .ghost {
    border-color: rgba(57, 76, 114, 0.6);
    background: rgba(20, 30, 51, 0.4);
    color: #e0e6ff;
    padding: 0.55rem 1.3rem;
  }

  .ghost:hover:not(:disabled) {
    border-color: rgba(140, 180, 255, 0.6);
    transform: translateY(-1px);
  }

  .ghost:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .ghost.subtle {
    padding: 0.4rem 0.95rem;
    font-size: 0.85rem;
    backdrop-filter: blur(4px);
  }

  .toggle-sidebar {
    min-width: 0;
    white-space: nowrap;
  }

  .clear {
    border-color: rgba(62, 80, 122, 0.55);
    background: rgba(18, 24, 42, 0.6);
    color: #f3f5ff;
    padding: 0.55rem 1.45rem;
  }

  .clear:hover:not(:disabled) {
    border-color: rgba(90, 122, 186, 0.8);
    transform: translateY(-1px);
  }

  .clear:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .layout-grid {
    display: grid;
    grid-template-columns: minmax(240px, 280px) minmax(0, 1fr);
    gap: 1.75rem;
    align-items: start;
  }

  .sidebar {
    position: relative;
    border-radius: 1.1rem;
    border: 1px dashed rgba(89, 123, 175, 0.35);
    background: rgba(14, 21, 36, 0.55);
    min-height: 420px;
    transition:
      opacity 0.2s ease,
      transform 0.2s ease;
    display: flex;
  }

  .sidebar-surface {
    flex: 1;
    border-radius: inherit;
  }

  .app-shell.sidebar-collapsed .layout-grid {
    grid-template-columns: 0 minmax(0, 1fr);
    gap: 0;
  }

  .app-shell.sidebar-collapsed .sidebar {
    opacity: 0;
    pointer-events: none;
    transform: translateX(-12px);
  }

  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    border-radius: 999px;
    padding: 0.28rem 0.85rem;
    font-size: 0.78rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    background: rgba(99, 112, 149, 0.25);
    color: #bfc8e6;
  }

  .status-pill::before {
    content: "";
    width: 0.48rem;
    height: 0.48rem;
    border-radius: 999px;
    background: #7b87a1;
    opacity: 0.8;
  }

  .status-pill.live {
    background: rgba(56, 189, 248, 0.16);
    color: #8ec3ff;
  }

  .status-pill.live::before {
    background: #38bdf8;
    animation: pulse 1.4s ease-in-out infinite;
    opacity: 1;
  }

  .chat-surface {
    display: grid;
    gap: 1.1rem;
  }

  .chat-header {
    min-height: 1.5rem;
    display: flex;
    justify-content: flex-end;
  }

  .conversation {
    background: rgba(11, 17, 35, 0.95);
    border-radius: 1.2rem;
    border: 1px solid rgba(42, 59, 99, 0.8);
    min-height: 380px;
    max-height: 560px;
    overflow-y: auto;
    padding: 1.35rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .placeholder {
    margin: auto;
    text-align: center;
    color: #8491b3;
    max-width: 70%;
    line-height: 1.6;
  }

  .message {
    padding: 0.85rem 1.15rem;
    border-radius: 0.95rem;
    display: grid;
    gap: 0.5rem;
    position: relative;
    background: rgba(18, 26, 46, 0.85);
    border: 1px solid rgba(58, 77, 120, 0.38);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
  }

  .message header {
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #7b87a1;
  }

  .message.user {
    align-self: flex-end;
    background: rgba(38, 50, 88, 0.78);
  }

  .message.assistant {
    align-self: flex-start;
  }

  .message.tool {
    align-self: stretch;
  }

  .message p {
    margin: 0;
    white-space: pre-wrap;
    line-height: 1.55;
    color: #e3e9ff;
  }

  .message .meta {
    display: grid;
    gap: 0.35rem;
    margin: 0;
    font-size: 0.82rem;
    color: #9aa6c8;
  }

  .message .meta div {
    display: grid;
    grid-template-columns: minmax(0, max-content) 1fr;
    gap: 0.5rem;
  }

  .message .meta dt {
    margin: 0;
    color: #aab5d3;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
  }

  .message .meta dd {
    margin: 0;
    color: #dce4ff;
  }

  .message .reasoning {
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    padding-top: 0.55rem;
  }

  .message .reasoning-label {
    display: block;
    font-size: 0.78rem;
    font-weight: 600;
    color: #96a2c4;
    margin-bottom: 0.35rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .message .reasoning ul {
    margin: 0;
    padding-left: 1rem;
    display: grid;
    gap: 0.35rem;
    font-size: 0.92rem;
    color: #e6ebff;
  }

  .message .reasoning li {
    list-style: disc;
  }

  .message .reasoning-type {
    font-weight: 600;
    margin-right: 0.4rem;
    color: #8ec3ff;
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
  }

  .pending {
    font-size: 1.25rem;
    color: #38bdf8;
    position: absolute;
    top: 0.6rem;
    right: 0.8rem;
  }

  .composer {
    display: grid;
    gap: 0.75rem;
    background: rgba(13, 18, 34, 0.92);
    border: 1px solid rgba(47, 66, 108, 0.6);
    border-radius: 1.15rem;
    padding: 1.1rem 1.2rem 1.25rem;
  }

  textarea {
    width: 100%;
    resize: vertical;
    min-height: 120px;
    padding: 0.85rem 1.1rem;
    border-radius: 0.95rem;
    border: 1px solid rgba(57, 82, 124, 0.75);
    background: rgba(5, 10, 21, 0.9);
    color: inherit;
    line-height: 1.55;
  }

  textarea:focus {
    outline: 2px solid rgba(56, 189, 248, 0.6);
    outline-offset: 2px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }

  .actions button {
    padding: 0.65rem 1.45rem;
    border: 1px solid transparent;
  }

  .actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .primary {
    background: linear-gradient(135deg, #38bdf8 0%, #60a5fa 100%);
    color: #021226;
  }

  .primary:hover:not(:disabled) {
    transform: translateY(-1px);
  }

  .secondary {
    background: rgba(17, 25, 46, 0.3);
    color: #f3f5ff;
    border-color: rgba(60, 82, 128, 0.7);
  }

  .secondary:hover:not(:disabled) {
    border-color: rgba(111, 155, 222, 0.75);
    transform: translateY(-1px);
  }

  .composer-hint {
    margin: 0;
    font-size: 0.85rem;
    color: #7e8db0;
  }

  .error {
    margin: 0;
    padding: 0.85rem 1.1rem;
    border-radius: 0.95rem;
    background: rgba(248, 113, 113, 0.16);
    border: 1px solid rgba(248, 113, 113, 0.35);
    color: #fecaca;
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 0.65;
      transform: scale(0.9);
    }

    50% {
      opacity: 1;
      transform: scale(1);
    }
  }

  @media (max-width: 1100px) {
    .layout-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  @media (max-width: 880px) {
    .hero {
      align-items: flex-start;
      justify-content: flex-start;
    }
  }

  @media (max-width: 640px) {
    .app-shell {
      padding: 2.25rem 1.35rem 3rem;
      gap: 1.6rem;
    }

    .conversation {
      min-height: 320px;
      max-height: none;
    }

    .actions {
      justify-content: space-between;
    }
  }
</style>
