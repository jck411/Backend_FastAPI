<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import ModelExplorer from './lib/components/model-explorer/ModelExplorer.svelte';
  import ChatHeader from './lib/components/chat/ChatHeader.svelte';
  import QuickPrompts from './lib/components/chat/QuickPrompts.svelte';
  import MessageList from './lib/components/chat/MessageList.svelte';
  import Composer from './lib/components/chat/Composer.svelte';
  import MessageEditor from './lib/components/chat/MessageEditor.svelte';
  import GenerationDetailsModal from './lib/components/chat/GenerationDetailsModal.svelte';
  import ModelSettingsModal from './lib/components/chat/ModelSettingsModal.svelte';
  import SystemSettingsModal from './lib/components/chat/SystemSettingsModal.svelte';
  import SpeechSettingsModal from './lib/components/chat/SpeechSettingsModal.svelte';
  import {
    speechState,
    startDictation,
    startConversationMode,
    clearPendingSubmit,
    notifyAssistantStreamingStarted,
    notifyAssistantStreamingFinished,
    stopSpeech,
  } from './lib/speech/speechController';
  import { fetchGenerationDetails } from './lib/api/client';
  import { chatStore } from './lib/stores/chat';
  import { modelStore } from './lib/stores/models';
  import { GENERATION_DETAIL_FIELDS } from './lib/chat/constants';
  import type { GenerationDetails, ModelRecord } from './lib/api/types';
  import type { GenerationDetailField } from './lib/chat/constants';

  const {
    sendMessage,
    cancelStream,
    clearConversation,
    deleteMessage,
    retryMessage,
    editMessage: applyMessageEdit,
    clearError,
    setModel,
  } = chatStore;
  const {
    loadModels,
    models: modelsStore,
    loading: modelsLoading,
    error: modelsError,
    selectable,
    activeFor,
  } = modelStore;

  let prompt = '';
  let explorerOpen = false;
  let generationModalOpen = false;
  let modelSettingsOpen = false;
  let systemSettingsOpen = false;
  let speechSettingsOpen = false;
  let lastSpeechPromptVersion = 0;
  let lastStreaming = false;
  let generationModalLoading = false;
  let generationModalError: string | null = null;
  let generationModalData: GenerationDetails | null = null;
  let generationModalId: string | null = null;
  let selectableModels: ModelRecord[] = [];
  let activeModel: ModelRecord | null = null;
  const generationDetailFields: GenerationDetailField[] = GENERATION_DETAIL_FIELDS;
  let editingMessageId: string | null = null;
  let editingText = '';
  let editingOriginalText = '';
  let editingSaving = false;

  onMount(loadModels);

  $: {
    if (typeof document !== 'undefined') {
      document.body.classList.toggle(
        'modal-open',
        explorerOpen ||
          generationModalOpen ||
          modelSettingsOpen ||
          systemSettingsOpen ||
          speechSettingsOpen,
      );
    }
  }

  onDestroy(() => {
    if (typeof document !== 'undefined') {
      document.body.classList.remove('modal-open');
    }
  });

  $: selectableModels = $selectable($chatStore.selectedModel);

  $: activeModel = $activeFor($chatStore.selectedModel);

  function handleModelChange(id: string): void {
    setModel(id);
  }

  function handleStartDictation(): void {
    void startDictation();
  }

  function handleStartConversationMode(): void {
    void startConversationMode();
  }

  function handleExplorerSelect(event: CustomEvent<{ id: string }>): void {
    setModel(event.detail.id);
  }

  function handlePromptSelect(text: string): void {
    prompt = text;
  }

  function handleDeleteMessage(event: CustomEvent<{ id: string }>): void {
    if ($chatStore.isStreaming) {
      return;
    }
    void deleteMessage(event.detail.id);
  }

  function handleRetryMessage(id: string): void {
    void retryMessage(id);
  }

  function beginEditingMessage(id: string): void {
    const message = $chatStore.messages.find((item) => item.id === id && item.role === 'user');
    if (!message) {
      return;
    }
    editingSaving = false;
    editingMessageId = id;
    editingText = message.text;
    editingOriginalText = message.text;
  }

  function resetEditingState(): void {
    editingMessageId = null;
    editingText = '';
    editingOriginalText = '';
  }

  function cancelEditing(): void {
    if (editingSaving) {
      return;
    }
    resetEditingState();
  }

  function handleEditorCancel(): void {
    cancelEditing();
  }

  function handleEditorSubmit(text: string): void {
    if (!editingMessageId) {
      return;
    }
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }
    const targetId = editingMessageId;
    editingSaving = true;
    resetEditingState();
    const editPromise = applyMessageEdit(targetId, trimmed);
    editPromise.catch((error) => {
      console.error('Failed to apply message edit', error);
    }).finally(() => {
      editingSaving = false;
    });
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

  async function handleSpeechAutoSubmit(text: string): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }
    prompt = trimmed;
    try {
      await sendMessage({ text: trimmed, attachments: [] });
      prompt = '';
    } catch (error) {
      console.error('Failed to send speech transcription', error);
    }
  }

  $: if ($speechState.promptVersion !== lastSpeechPromptVersion) {
    lastSpeechPromptVersion = $speechState.promptVersion;
    prompt = $speechState.promptText;
  }

  $: if ($speechState.pendingSubmit && !$chatStore.isStreaming) {
    const submission = clearPendingSubmit();
    if (submission) {
      void handleSpeechAutoSubmit(submission.text);
    }
  }

  $: if ($chatStore.isStreaming !== lastStreaming) {
    if ($chatStore.isStreaming) {
      notifyAssistantStreamingStarted();
    } else {
      void notifyAssistantStreamingFinished();
    }
    lastStreaming = $chatStore.isStreaming;
  }

  $: if (editingMessageId) {
    stopSpeech();
  }
</script>

<main class="chat-app">
  <ChatHeader
    selectableModels={selectableModels}
    selectedModel={$chatStore.selectedModel}
    modelsLoading={$modelsLoading}
    modelsError={$modelsError}
    hasMessages={$chatStore.messages.length > 0}
    on:openExplorer={() => (explorerOpen = true)}
    on:clear={clearConversation}
    on:modelChange={(event) => handleModelChange(event.detail.id)}
    on:openModelSettings={() => (modelSettingsOpen = true)}
    on:openSystemSettings={() => (systemSettingsOpen = true)}
    on:openSpeechSettings={() => (speechSettingsOpen = true)}
  />

  {#if !$chatStore.messages.length}
    <QuickPrompts on:select={(event) => handlePromptSelect(event.detail.text)} />
  {/if}

  <MessageList
    messages={$chatStore.messages}
    on:openGenerationDetails={(event) => openGenerationDetails(event.detail.id)}
    on:deleteMessage={handleDeleteMessage}
    on:retryMessage={(event) => handleRetryMessage(event.detail.id)}
    on:editMessage={(event) => beginEditingMessage(event.detail.id)}
    disableDelete={$chatStore.isStreaming}
  />

  {#if $chatStore.error}
    <div class="chat-error" role="alert">
      <span>{$chatStore.error}</span>
      <button type="button" on:click={clearError}>Dismiss</button>
    </div>
  {/if}

  {#if editingMessageId}
    <MessageEditor
      bind:value={editingText}
      originalValue={editingOriginalText}
      saving={editingSaving}
      disabled={editingSaving}
      on:cancel={handleEditorCancel}
      on:submit={(event) => handleEditorSubmit(event.detail.text)}
    />
  {:else}
    <Composer
      bind:prompt
      isStreaming={$chatStore.isStreaming}
      on:submit={(event) => sendMessage(event.detail)}
      on:cancel={cancelStream}
      on:startDictation={handleStartDictation}
      on:startConversationMode={handleStartConversationMode}
    />
  {/if}

  <GenerationDetailsModal
    open={generationModalOpen}
    generationId={generationModalId}
    loading={generationModalLoading}
    error={generationModalError}
    data={generationModalData}
    fields={generationDetailFields}
    on:close={closeGenerationDetails}
  />

  <ModelSettingsModal
    open={modelSettingsOpen}
    selectedModel={$chatStore.selectedModel}
    model={activeModel}
    on:close={() => (modelSettingsOpen = false)}
  />

  <SystemSettingsModal
    open={systemSettingsOpen}
    on:close={() => (systemSettingsOpen = false)}
  />

  <SpeechSettingsModal open={speechSettingsOpen} on:close={() => (speechSettingsOpen = false)} />

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
  .chat-error {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin: 0 auto 1.25rem;
    padding: 0.9rem 1.25rem;
    width: min(800px, calc(100% - 4rem));
    border-radius: 0.75rem;
    border: 1px solid rgba(248, 113, 113, 0.4);
    background: rgba(69, 20, 20, 0.6);
    color: #fecaca;
    backdrop-filter: blur(4px);
  }
  .chat-error button {
    border: 1px solid rgba(248, 113, 113, 0.6);
    border-radius: 999px;
    background: transparent;
    color: inherit;
    padding: 0.3rem 0.9rem;
    cursor: pointer;
  }
  .chat-error button:hover,
  .chat-error button:focus-visible {
    border-color: #fca5a5;
    color: #fca5a5;
    outline: none;
  }
</style>
