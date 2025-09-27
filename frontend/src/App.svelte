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
  let explorerOpen = false;
  let chatContainer: HTMLElement | null = null;

  onMount(loadModels);

  afterUpdate(() => {
    // auto-scroll to newest message
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
  });

  function handleSubmit() {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    sendMessage(trimmed);
    prompt = "";
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleModelChange(e: Event) {
    const sel = e.target as HTMLSelectElement;
    setModel(sel.value);
  }

  function handleExplorerSelect(e: CustomEvent<{ id: string }>) {
    setModel(e.detail.id);
  }

  /* keep the model list logic you already had */
  $: selectableModels = (() => {
    const active = $activeFilters;
    const base = active ? $filteredModels : $modelsStore;
    if (!base?.length) return [];
    const selected = $chatStore.selectedModel;
    if (!selected) return base;
    return base.some((m) => m.id === selected)
      ? base
      : [$modelsStore.find((m) => m.id === selected), ...base].filter(
          (m): m is NonNullable<typeof m> => m !== null && m !== undefined,
        );
  })();
</script>

<main class="chat-app">
  <!-- ░░ Header ░░ -->
  <header class="topbar">
    <div class="topbar-content">
      <h1 class="title">Chat&nbsp;Playground</h1>

      <div class="controls">
        <select
          on:change={handleModelChange}
          bind:value={$chatStore.selectedModel}
          disabled={$modelsLoading}
        >
          {#if $modelsLoading}
            <option>Loading…</option>
          {:else if $modelsError}
            <option disabled>{`Failed to load models — ${$modelsError}`}</option
            >
          {:else if !selectableModels.length}
            <option disabled>No models</option>
          {:else}
            {#each selectableModels as m (m.id)}
              <option value={m.id}>{m.name ?? m.id}</option>
            {/each}
          {/if}
        </select>

        <button class="ghost" on:click={() => (explorerOpen = true)}
          >Explorer</button
        >
        <button
          class="ghost"
          on:click={clearConversation}
          disabled={!$chatStore.messages.length}
        >
          Clear
        </button>
      </div>
    </div>
  </header>

  <!-- ░░ Quick-prompts (only shown before first user turn) ░░ -->
  {#if !$chatStore.messages.length}
    <section class="suggestions">
      <button
        on:click={() => (prompt = "What are the advantages of using Next.js?")}
      >
        Next.js advantages
      </button>
      <button
        on:click={() =>
          (prompt = "Write code to demonstrate Dijkstra's algorithm")}
      >
        Dijkstra code
      </button>
      <button
        on:click={() =>
          (prompt = "Help me write an essay about Silicon Valley")}
      >
        Essay helper
      </button>
      <button on:click={() => (prompt = "What is the weather in Orlando?")}>
        Weather
      </button>
    </section>
  {/if}

  <!-- ░░ Messages ░░ -->
  <section class="conversation" bind:this={chatContainer} aria-live="polite">
    {#each $chatStore.messages as m (m.id)}
      <article class="message {m.role}">
        <div class="bubble">
          {#if m.role !== "user"}
            <span class="sender">{m.role}</span>
          {/if}
          <p>{m.content}</p>
          {#if m.pending}
            <span class="pending">…</span>
          {/if}
        </div>
      </article>
    {/each}
  </section>

  <!-- ░░ Composer ░░ -->
  <form class="composer" on:submit|preventDefault={handleSubmit}>
    <div class="composer-content">
      <div class="input-shell">
        <button
          type="button"
          class="icon-button leading"
          aria-label="New prompt"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M9 2v14M2 9h14"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
          </svg>
        </button>

        <textarea
          rows="1"
          bind:value={prompt}
          on:keydown={handleKeydown}
          placeholder={$chatStore.isStreaming
            ? "Waiting for response…"
            : "Ask me anything…"}
          aria-disabled={$chatStore.isStreaming}
        ></textarea>

        <div class="composer-actions">
          {#if $chatStore.isStreaming}
            <button type="button" class="stop-inline" on:click={cancelStream}>
              <span aria-hidden="true" class="stop-indicator"></span>
              Stop
            </button>
          {/if}
          <button
            type="button"
            class="icon-button"
            aria-label="Toggle microphone"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 18 18"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M9 3a2 2 0 0 1 2 2v4a2 2 0 1 1-4 0V5a2 2 0 0 1 2-2Z"
                stroke="currentColor"
                stroke-width="1.5"
              />
              <path
                d="M5 8.5a4 4 0 0 0 8 0M9 12.5V15"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
          <button type="button" class="icon-button" aria-label="Attach audio">
            <svg
              width="18"
              height="18"
              viewBox="0 0 18 18"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M4 9v-1.5M7 12V6M11 12V6M14 9v-1.5"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </form>

  <ModelExplorer bind:open={explorerOpen} on:select={handleExplorerSelect} />
</main>

<style>
  /* ==== Layout tokens ==== */
  * {
    box-sizing: border-box;
  }
  .chat-app {
    --header-h: 64px;
    --composer-h: 140px;
    display: flex;
    flex-direction: column;
    height: 100vh;
    background: radial-gradient(
      circle at top,
      #162135 0%,
      #05070f 55%,
      #04060d 100%
    );
    color: #f3f5ff;
    overflow: hidden;
    position: relative;
  }

  /* Fade overlays for header and footer areas */
  .chat-app::before,
  .chat-app::after {
    content: "";
    position: fixed;
    left: 0;
    right: 0;
    pointer-events: none;
    z-index: 10;
  }

  /* Top fade overlay */
  .chat-app::before {
    top: 0;
    height: calc(var(--header-h) + 2rem);
    background: linear-gradient(
      to bottom,
      rgba(4, 6, 13, 1) 0%,
      rgba(4, 6, 13, 0.95) 30%,
      rgba(4, 6, 13, 0.8) 50%,
      rgba(4, 6, 13, 0.4) 70%,
      rgba(4, 6, 13, 0.1) 90%,
      transparent 100%
    );
  }

  /* Bottom fade overlay */
  .chat-app::after {
    bottom: 0;
    height: calc(var(--composer-h) + 2rem);
    background: linear-gradient(
      to top,
      rgba(4, 6, 13, 1) 0%,
      rgba(4, 6, 13, 0.95) 30%,
      rgba(4, 6, 13, 0.8) 50%,
      rgba(4, 6, 13, 0.4) 70%,
      rgba(4, 6, 13, 0.1) 90%,
      transparent 100%
    );
  }

  /* ==== Header ==== */
  .topbar {
    height: var(--header-h);
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    position: relative;
    z-index: 20;
  }
  .topbar-content {
    width: min(800px, 100%);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0 2rem;
  }
  .title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }
  .controls {
    display: flex;
    gap: 0.75rem;
    align-items: center;
  }
  /* Match Explorer styles for select */
  .controls select {
    appearance: none;
    padding: 0.45rem 2rem 0.45rem 0.75rem;
    border-radius: 0.5rem;
    background: rgba(9, 14, 26, 0.9);
    color: #f2f4f8;
    border: 1px solid #25314d;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease;
    background-image: url('data:image/svg+xml,%3Csvg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"%3E%3Cpath d="M7 8l3 3 3-3" stroke="%23d4daee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/%3E%3C/svg%3E');
    background-repeat: no-repeat;
    background-position: right 0.65rem center;
    background-size: 1rem;
    min-width: 160px;
  }
  .controls select:hover {
    border-color: #38bdf8;
    background-color: rgba(12, 19, 34, 0.95);
    color: #f8fafc;
  }
  .controls select:focus {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
    border-color: #38bdf8;
    box-shadow: none;
  }
  .controls select:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    background: rgba(9, 14, 26, 0.6);
  }
  .controls select option {
    background: #0a101a;
    color: #f2f4f8;
  }

  /* Match Explorer styles for ghost buttons */
  .controls .ghost {
    background: none;
    border: 1px solid #25314d;
    border-radius: 999px;
    color: #f2f4f8;
    padding: 0.55rem 1.1rem;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      color 0.2s ease,
      background 0.2s ease;
  }
  .controls .ghost:hover:not(:disabled) {
    border-color: #38bdf8;
    color: #38bdf8;
  }
  .controls .ghost:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* ==== Quick prompts ==== */
  .suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    padding: 1.5rem 2rem;
    max-width: min(800px, 100%);
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }
  .suggestions button {
    font-size: 0.85rem;
    padding: 0.625rem 1.25rem;
    border-radius: 999px;
    background: rgba(20, 30, 51, 0.4);
    border: 1px solid rgba(57, 76, 114, 0.6);
    color: inherit;
    cursor: pointer;
  }
  .suggestions button:hover {
    border-color: rgba(140, 180, 255, 0.6);
  }

  /* ==== Messages ==== */
  .conversation {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 2rem 0;
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
    scroll-padding-top: 4rem;
    scroll-padding-bottom: 4rem;
    scrollbar-gutter: stable;
  }
  .conversation > * {
    padding: 0 2rem;
    max-width: min(800px, 100%);
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }
  .message {
    display: flex;
  }
  .message.user {
    justify-content: flex-end;
  }
  .message.assistant {
    justify-content: flex-start;
  }
  .bubble {
    max-width: 75%;
    padding: 1rem 1.5rem;
    border-radius: 0.95rem;
    background: rgba(18, 26, 46, 0.85);
    border: 1px solid rgba(58, 77, 120, 0.38);
    position: relative;
  }
  .message.user .bubble {
    background: rgba(38, 50, 88, 0.78);
  }
  .message.assistant .bubble {
    background: transparent;
    border: none;
    padding: 0.5rem 0;
  }
  .sender {
    display: block;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
    color: #7b87a1;
    text-transform: uppercase;
  }
  .bubble p {
    margin: 0;
    white-space: pre-wrap;
    line-height: 1.55;
  }
  .pending {
    position: absolute;
    bottom: 0.5rem;
    right: 0.85rem;
    font-size: 1.25rem;
    color: #38bdf8;
  }

  /* ==== Composer ==== */
  .composer {
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    padding: 1rem 0 1.5rem;
    background: transparent;
    position: relative;
    z-index: 20;
  }
  .composer-content {
    width: min(800px, 100%);
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    justify-content: flex-end;
    padding: 0 2rem;
  }
  .input-shell {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.875rem 1.25rem;
    border-radius: 999px;
    background: rgba(11, 18, 34, 0.82);
    border: 1px solid rgba(57, 82, 124, 0.55);
    box-shadow: 0 12px 28px rgba(4, 8, 20, 0.45);
  }
  .input-shell textarea {
    flex: 1 1 auto;
    min-height: 2.5rem;
    background: transparent;
    border: none;
    color: inherit;
    padding: 0.25rem 0;
    resize: none;
    font: inherit;
    line-height: 1.55;
  }
  .input-shell textarea:focus {
    outline: none;
  }
  .input-shell textarea::placeholder {
    color: rgba(184, 197, 226, 0.6);
  }
  .composer-actions {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .stop-inline {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0 1.25rem;
    height: 2.5rem;
    border-radius: 999px;
    border: 1px solid rgba(254, 63, 94, 0.55);
    background: linear-gradient(
      135deg,
      rgba(65, 15, 26, 0.9),
      rgba(35, 11, 20, 0.88)
    );
    color: #ffd7dc;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.01em;
    cursor: pointer;
    box-shadow:
      0 0 0 1px rgba(255, 82, 110, 0.25),
      0 6px 18px rgba(255, 71, 102, 0.18);
    transition:
      border-color 0.2s ease,
      filter 0.2s ease;
  }
  .stop-inline:hover {
    border-color: rgba(255, 111, 136, 0.75);
    filter: saturate(1.05);
  }
  .stop-inline:focus-visible {
    outline: 2px solid rgba(255, 142, 165, 0.8);
    outline-offset: 2px;
  }
  .stop-indicator {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: radial-gradient(
      circle at 35% 35%,
      #ffe7ec 0%,
      #ff5f7c 60%,
      #c91b3d 100%
    );
    box-shadow: 0 0 8px rgba(255, 99, 132, 0.65);
    animation: stopPulse 1.4s ease-in-out infinite;
  }
  @keyframes stopPulse {
    0%,
    100% {
      transform: scale(1);
      box-shadow: 0 0 6px rgba(255, 99, 132, 0.45);
    }
    50% {
      transform: scale(1.1);
      box-shadow: 0 0 11px rgba(255, 120, 150, 0.75);
    }
  }
  .icon-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 999px;
    border: 1px solid rgba(68, 92, 138, 0.65);
    background: rgba(18, 26, 46, 0.9);
    color: #d7e0ff;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      color 0.2s ease;
  }
  .icon-button:hover {
    border-color: rgba(132, 176, 255, 0.75);
    color: #ffffff;
  }
  .icon-button svg {
    display: block;
  }
  .icon-button.leading {
    margin-right: 0.5rem;
  }
</style>
