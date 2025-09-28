<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import ModelExplorer from './lib/components/model-explorer/ModelExplorer.svelte';
  import ChatHeader from './lib/components/chat/ChatHeader.svelte';
  import QuickPrompts from './lib/components/chat/QuickPrompts.svelte';
  import MessageList from './lib/components/chat/MessageList.svelte';
  import Composer from './lib/components/chat/Composer.svelte';
  import GenerationDetailsModal from './lib/components/chat/GenerationDetailsModal.svelte';
  import { fetchGenerationDetails } from './lib/api/client';
  import { chatStore } from './lib/stores/chat';
  import { modelStore } from './lib/stores/models';
  import { GENERATION_DETAIL_FIELDS } from './lib/chat/constants';
  import type { GenerationDetails } from './lib/api/types';
  import type { GenerationDetailField } from './lib/chat/constants';

  const { sendMessage, cancelStream, clearConversation, setModel, updateWebSearch } = chatStore;
  const {
    loadModels,
    models: modelsStore,
    loading: modelsLoading,
    error: modelsError,
    filtered: filteredModels,
    activeFilters,
  } = modelStore;

  let prompt = '';
  let explorerOpen = false;
  let generationModalOpen = false;
  let generationModalLoading = false;
  let generationModalError: string | null = null;
  let generationModalData: GenerationDetails | null = null;
  let generationModalId: string | null = null;
  const generationDetailFields: GenerationDetailField[] = GENERATION_DETAIL_FIELDS;

  onMount(loadModels);

  $: {
    if (typeof document !== 'undefined') {
      document.body.classList.toggle('modal-open', explorerOpen || generationModalOpen);
    }
  }

  onDestroy(() => {
    if (typeof document !== 'undefined') {
      document.body.classList.remove('modal-open');
    }
  });

  $: selectableModels = (() => {
    const active = $activeFilters;
    const base = active ? $filteredModels : $modelsStore;
    if (!base?.length) return [];
    const selected = $chatStore.selectedModel;
    if (!selected) return base;
    return base.some((model) => model.id === selected)
      ? base
      : [$modelsStore.find((model) => model.id === selected), ...base].filter(
          (model): model is NonNullable<typeof model> => model !== null && model !== undefined,
        );
  })();

  function handleModelChange(id: string): void {
    setModel(id);
  }

  function handleExplorerSelect(event: CustomEvent<{ id: string }>): void {
    setModel(event.detail.id);
  }

  function handlePromptSelect(text: string): void {
    prompt = text;
  }

  async function openGenerationDetails(generationId: string): Promise<void> {
    if (!generationId) return;
    generationModalOpen = true;
    generationModalLoading = true;
    generationModalError = null;
    generationModalData = null;
    generationModalId = generationId;

    try {
      const response = await fetchGenerationDetails(generationId);
      generationModalData = response?.data ?? null;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load details.';
      generationModalError = message;
    } finally {
      generationModalLoading = false;
    }
  }

  function closeGenerationDetails(): void {
    generationModalOpen = false;
    generationModalId = null;
    generationModalData = null;
    generationModalError = null;
  }
</script>

<main class="chat-app">
  <ChatHeader
    selectableModels={selectableModels}
    selectedModel={$chatStore.selectedModel}
    modelsLoading={$modelsLoading}
    modelsError={$modelsError}
    hasMessages={$chatStore.messages.length > 0}
    webSearch={$chatStore.webSearch}
    on:openExplorer={() => (explorerOpen = true)}
    on:clear={clearConversation}
    on:modelChange={(event) => handleModelChange(event.detail.id)}
    on:webSearchChange={(event) => updateWebSearch(event.detail.settings)}
  />

  {#if !$chatStore.messages.length}
    <QuickPrompts on:select={(event) => handlePromptSelect(event.detail.text)} />
  {/if}

  <MessageList
    messages={$chatStore.messages}
    on:openGenerationDetails={(event) => openGenerationDetails(event.detail.id)}
  />

  <Composer
    bind:prompt
    isStreaming={$chatStore.isStreaming}
    on:submit={(event) => sendMessage(event.detail.text)}
    on:cancel={cancelStream}
  />

  <GenerationDetailsModal
    open={generationModalOpen}
    generationId={generationModalId}
    loading={generationModalLoading}
    error={generationModalError}
    data={generationModalData}
    fields={generationDetailFields}
    on:close={closeGenerationDetails}
  />

  <ModelExplorer bind:open={explorerOpen} on:select={handleExplorerSelect} />
</main>

<style>
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
  .chat-app::before,
  .chat-app::after {
    content: '';
    position: fixed;
    left: 0;
    right: 0;
    pointer-events: none;
    z-index: 10;
  }
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
</style>
