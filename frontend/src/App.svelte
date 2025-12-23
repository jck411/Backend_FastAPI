<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { fetchGenerationDetails } from "./lib/api/client";
  import type {
    AttachmentResource,
    GenerationDetails,
    ModelRecord,
  } from "./lib/api/types";
  import type { GenerationDetailField } from "./lib/chat/constants";
  import { GENERATION_DETAIL_FIELDS } from "./lib/chat/constants";
  import ChatHeader from "./lib/components/chat/ChatHeader.svelte";
  import Composer from "./lib/components/chat/Composer.svelte";
  import GenerationDetailsModal from "./lib/components/chat/GenerationDetailsModal.svelte";
  import MessageEditor from "./lib/components/chat/MessageEditor.svelte";
  import MessageList from "./lib/components/chat/MessageList.svelte";
  import ModelSettingsModal from "./lib/components/chat/ModelSettingsModal.svelte";
  import QuickPrompts from "./lib/components/chat/QuickPrompts.svelte";
  import SystemSettingsModal from "./lib/components/chat/SystemSettingsModal.svelte";

  import KioskSettingsModal from "./lib/components/chat/KioskSettingsModal.svelte";
  import CliSettingsModal from "./lib/components/chat/CliSettingsModal.svelte";
  import McpServersModal from "./lib/components/chat/McpServersModal.svelte";
  import ModelExplorer from "./lib/components/model-explorer/ModelExplorer.svelte";
  import {
    clearPendingSubmit,
    speechState,
    startDictation,
    stopSpeech,
  } from "./lib/speech/speechController";
  import type { ConversationMessage } from "./lib/stores/chat";
  import { chatStore } from "./lib/stores/chat";
  import { modelStore } from "./lib/stores/models";
  import { presetsStore } from "./lib/stores/presets";
  import { suggestionsStore } from "./lib/stores/suggestions";

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

  let prompt = "";
  let presetAttachments: AttachmentResource[] = [];
  let quickPromptsComponent: QuickPrompts;
  let explorerOpen = false;
  let generationModalOpen = false;
  let modelSettingsOpen = false;
  let systemSettingsOpen = false;
  let mcpServersOpen = false;

  let kioskSettingsOpen = false;
  let cliSettingsOpen = false;
  let lastSpeechPromptVersion = 0;
  let generationModalLoading = false;
  let generationModalError: string | null = null;
  let generationModalData: GenerationDetails | null = null;
  let generationModalId: string | null = null;
  let selectableModels: ModelRecord[] = [];
  let activeModel: ModelRecord | null = null;
  const generationDetailFields: GenerationDetailField[] =
    GENERATION_DETAIL_FIELDS;
  let editingMessageId: string | null = null;
  let editingText = "";
  let editingOriginalText = "";
  let editingSaving = false;

  onMount(async () => {
    await loadModels();
    await suggestionsStore.load();
    // Load and apply default preset if one is set
    const defaultPreset = await presetsStore.loadDefault();
    if (defaultPreset) {
      const applied = await presetsStore.apply(defaultPreset.name);
      if (applied?.model) {
        setModel(applied.model);
      }
      // Reload suggestions after applying preset
      await suggestionsStore.load();
    }
    
    // Check for URL params to open modals directly
    const params = new URLSearchParams(window.location.search);
    if (params.get("mcp") === "1") {
      mcpServersOpen = true;
      // Clean up URL
      window.history.replaceState({}, "", window.location.pathname);
    }
  });

  async function handleSuggestionAdd(): Promise<void> {
    if (!quickPromptsComponent) return;
    const newSuggestion = quickPromptsComponent.getNewSuggestion();
    if (newSuggestion) {
      await suggestionsStore.add(newSuggestion.label, newSuggestion.text);
    }
  }

  async function handleSuggestionDelete(
    event: CustomEvent<{ index: number }>,
  ): Promise<void> {
    await suggestionsStore.remove(event.detail.index);
  }

  $: {
    if (typeof document !== "undefined") {
      document.body.classList.toggle(
        "modal-open",
        explorerOpen ||
          generationModalOpen ||
          modelSettingsOpen ||
          systemSettingsOpen ||
          mcpServersOpen ||
          kioskSettingsOpen ||
          cliSettingsOpen,
      );
    }
  }

  onDestroy(() => {
    if (typeof document !== "undefined") {
      document.body.classList.remove("modal-open");
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

  function handleAssistantAttachmentEdit(detail: {
    message: ConversationMessage;
    attachment: AttachmentResource;
  }): void {
    if (!detail?.attachment) {
      return;
    }
    cancelEditing();

    const cloned: AttachmentResource = {
      ...detail.attachment,
      metadata: detail.attachment.metadata
        ? { ...detail.attachment.metadata }
        : null,
    };

    // Allow selecting multiple assistant images for "edit & send" by
    // accumulating preset attachments instead of replacing them.
    const existing = presetAttachments ?? [];
    const alreadyIncluded = existing.some(
      (item) =>
        item.id === cloned.id ||
        item.displayUrl === cloned.displayUrl ||
        item.deliveryUrl === cloned.deliveryUrl,
    );

    const nextAttachments = alreadyIncluded ? existing : [...existing, cloned];
    presetAttachments = nextAttachments;
  }

  function beginEditingMessage(id: string): void {
    const message = $chatStore.messages.find(
      (item) => item.id === id && item.role === "user",
    );
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
    editingText = "";
    editingOriginalText = "";
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
    editPromise
      .catch((error) => {
        console.error("Failed to apply message edit", error);
      })
      .finally(() => {
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
      const message =
        error instanceof Error ? error.message : "Failed to load details.";
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
      prompt = "";
    } catch (error) {
      console.error("Failed to send speech transcription", error);
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

  $: if (editingMessageId) {
    stopSpeech();
  }
</script>

<main class="chat-app">
  <ChatHeader
    {selectableModels}
    selectedModel={$chatStore.selectedModel}
    modelsLoading={$modelsLoading}
    modelsError={$modelsError}
    hasMessages={$chatStore.messages.length > 0}
    on:openExplorer={() => (explorerOpen = true)}
    on:clear={() => {
      presetAttachments = [];
      prompt = "";
      clearConversation();
    }}
    on:modelChange={(event) => handleModelChange(event.detail.id)}
    on:openModelSettings={() => (modelSettingsOpen = true)}
    on:openSystemSettings={() => (systemSettingsOpen = true)}
    on:openMcpServers={() => (mcpServersOpen = true)}
    on:openKioskSettings={() => (kioskSettingsOpen = true)}
    on:openCliSettings={() => (cliSettingsOpen = true)}
  />

  {#if !$chatStore.messages.length}
    <QuickPrompts
      bind:this={quickPromptsComponent}
      suggestions={$suggestionsStore.items}
      deleting={$suggestionsStore.deleting}
      on:add={handleSuggestionAdd}
      on:delete={handleSuggestionDelete}
      on:select={(event) => handlePromptSelect(event.detail.text)}
    />
  {/if}

  <MessageList
    messages={$chatStore.messages}
    on:openGenerationDetails={(event) => openGenerationDetails(event.detail.id)}
    on:deleteMessage={handleDeleteMessage}
    on:retryMessage={(event) => handleRetryMessage(event.detail.id)}
    on:editMessage={(event) => beginEditingMessage(event.detail.id)}
    on:editAssistantAttachment={(event) =>
      handleAssistantAttachmentEdit(event.detail)}
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
      {presetAttachments}
      isStreaming={$chatStore.isStreaming}
      on:submit={(event) => sendMessage(event.detail)}
      on:cancel={cancelStream}
      on:startDictation={handleStartDictation}
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

  <McpServersModal
    open={mcpServersOpen}
    on:close={() => (mcpServersOpen = false)}
  />

  <KioskSettingsModal
    open={kioskSettingsOpen}
    on:close={() => (kioskSettingsOpen = false)}
  />

  <CliSettingsModal
    open={cliSettingsOpen}
    on:close={() => (cliSettingsOpen = false)}
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
    height: 100dvh;
    min-height: 100vh;
    padding-bottom: env(safe-area-inset-bottom, 0);
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
    content: "";
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
  @media (max-width: 1024px) {
    .chat-app {
      --header-h: 58px;
      --composer-h: 130px;
    }
  }
  @media (max-width: 768px) {
    .chat-app {
      --header-h: 56px;
      --composer-h: 170px;
    }
    .chat-app::before {
      height: calc(var(--header-h) + 1.5rem);
    }
    .chat-app::after {
      height: calc(var(--composer-h) + 1.5rem);
    }
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
