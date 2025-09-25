<script lang="ts">
  import { afterUpdate, onMount } from 'svelte';
  import { chatStore } from './lib/stores/chat';
  import { modelStore } from './lib/stores/models';
  import ModelExplorer from './lib/components/model-explorer/ModelExplorer.svelte';

  const { sendMessage, cancelStream, clearConversation, setModel } = chatStore;
  const {
    loadModels,
    models: modelsStore,
    loading: modelsLoading,
    error: modelsError,
    filtered: filteredModels,
    activeFilters,
  } = modelStore;

  let prompt = '';
  let chatLog: HTMLElement | null = null;
  let lastMessageCount = 0;
  let explorerOpen = false;

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
    prompt = '';
  }

  function handleModelChange(event: Event) {
    const target = event.target as HTMLSelectElement | null;
    if (!target) return;
    setModel(target.value);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  function openExplorer() {
    explorerOpen = true;
  }

  function handleExplorerSelect(event: CustomEvent<{ id: string }>) {
    const nextModel = event.detail.id;
    if (nextModel) {
      setModel(nextModel);
    }
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

<main>
  <header class="app-header">
    <div>
      <h1>Chat Console</h1>
      <p class="subtitle">Connects to the OpenRouter FastAPI backend.</p>
    </div>
    <button class="clear" type="button" on:click={clearConversation} disabled={$chatStore.messages.length === 0}>
      Clear
    </button>
  </header>

  <section class="toolbar">
    <label>
      <span>Model</span>
      <select on:change={handleModelChange} bind:value={$chatStore.selectedModel} disabled={$modelsLoading}>
        {#if $modelsLoading}
          <option>Loading models…</option>
        {:else if $modelsError}
          <option disabled>{`Failed to load models (${ $modelsError })`}</option>
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
    <button type="button" class="ghost" on:click={openExplorer} disabled={$modelsLoading}>
      Explorer
    </button>
    <div class="status">
      {#if $chatStore.isStreaming}
        <span class="dot" aria-hidden="true"></span>
        <span>Streaming response…</span>
      {:else}
        <span>Idle</span>
      {/if}
    </div>
  </section>

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
      placeholder={$chatStore.isStreaming ? 'Waiting for response…' : 'Ask the assistant anything…'}
      aria-disabled={$chatStore.isStreaming}
    ></textarea>
    <div class="actions">
      {#if $chatStore.isStreaming}
        <button type="button" class="secondary" on:click={cancelStream}>
          Stop
        </button>
      {/if}
      <button type="submit" class="primary" disabled={!prompt.trim() || $chatStore.isStreaming}>
        Send
      </button>
    </div>
  </form>

  {#if $chatStore.error}
    <p class="error" role="alert">{$chatStore.error}</p>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0b101b;
    color: #f2f4f8;
    min-height: 100vh;
  }

  main {
    max-width: 960px;
    margin: 0 auto;
    padding: 2.5rem 1.5rem 3rem;
    display: grid;
    gap: 1.5rem;
  }

  .app-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
  }

  .app-header h1 {
    margin: 0;
    font-size: 1.75rem;
  }

  .subtitle {
    margin: 0.4rem 0 0;
    color: #a4aab8;
    font-size: 0.95rem;
  }

  .clear {
    background: none;
    border: 1px solid #25314b;
    border-radius: 999px;
    color: #f2f4f8;
    padding: 0.5rem 1.25rem;
    cursor: pointer;
  }

  .clear:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem;
    background: #121a2c;
    border: 1px solid #1d2640;
    border-radius: 1rem;
  }

  .toolbar label {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    font-size: 0.95rem;
  }

  .toolbar select {
    min-width: 220px;
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    border: 1px solid #24304c;
    background: #0b101b;
    color: inherit;
  }

  .toolbar .ghost {
    border-radius: 999px;
    border: 1px solid #25314d;
    background: none;
    color: inherit;
    padding: 0.45rem 1.1rem;
    cursor: pointer;
  }

  .status {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
    color: #a4aab8;
  }

  .status .dot {
    width: 0.75rem;
    height: 0.75rem;
    border-radius: 999px;
    background: #38bdf8;
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 0.5;
      transform: scale(0.9);
    }
    50% {
      opacity: 1;
      transform: scale(1);
    }
  }

  .conversation {
    background: #10172b;
    border-radius: 1rem;
    border: 1px solid #1c2745;
    min-height: 380px;
    max-height: 560px;
    overflow-y: auto;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .placeholder {
    margin: auto;
    text-align: center;
    color: #7b8194;
  }

  .message {
    padding: 0.75rem 1rem;
    border-radius: 0.85rem;
    display: grid;
    gap: 0.45rem;
    position: relative;
  }

  .message header {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #7b8194;
  }

  .message.user {
    align-self: flex-end;
    background: #1f2b45;
  }

  .message.assistant {
    align-self: flex-start;
    background: #172034;
  }

  .message p {
    margin: 0;
    white-space: pre-wrap;
    line-height: 1.45;
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
  }

  textarea {
    width: 100%;
    resize: vertical;
    min-height: 120px;
    padding: 0.75rem 1rem;
    border-radius: 1rem;
    border: 1px solid #1d2943;
    background: #0b101b;
    color: inherit;
    line-height: 1.45;
  }

  textarea:focus {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }

  .actions button {
    border-radius: 999px;
    padding: 0.6rem 1.4rem;
    cursor: pointer;
    border: 1px solid transparent;
  }

  .actions button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .primary {
    background: #38bdf8;
    color: #031221;
    font-weight: 600;
  }

  .secondary {
    background: none;
    color: #f2f4f8;
    border-color: #2f3c5f;
  }

  .error {
    margin: 0;
    padding: 0.75rem 1rem;
    border-radius: 0.85rem;
    background: rgba(248, 113, 113, 0.15);
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

  @media (max-width: 640px) {
    .toolbar {
      flex-direction: column;
      align-items: stretch;
    }

    .toolbar select {
      width: 100%;
    }

    .actions {
      justify-content: space-between;
    }
  }
</style>
