<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { uploadAttachment } from '../../api/client';
  import type { AttachmentResource } from '../../api/types';
  import { chatStore } from '../../stores/chat';
  import { speechState } from '../../speech/speechController';

  export let prompt = '';
  export let isStreaming = false;

  type AttachmentStatus = 'uploading' | 'ready' | 'error';

  interface AttachmentDraft {
    id: string;
    file: File;
    previewUrl: string;
    status: AttachmentStatus;
    resource?: AttachmentResource;
    error?: string | null;
  }

  const dispatch = createEventDispatcher<{
    submit: { text: string; attachments: AttachmentResource[] };
    cancel: void;
    startDictation: void;
    startConversationMode: void;
  }>();

  const ALLOWED_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif']);
  const MAX_SIZE_BYTES = 10 * 1024 * 1024;
  const MAX_ATTACHMENTS = 4;

  let attachments: AttachmentDraft[] = [];
  let composerError: string | null = null;
  let fileInput: HTMLInputElement | null = null;

  function createLocalId(): string {
    if (globalThis.crypto?.randomUUID) {
      return `attachment_${globalThis.crypto.randomUUID().replace(/-/g, '')}`;
    }
    return `attachment_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  }

  function handleSubmit(): void {
    const trimmed = prompt.trim();
    const hasUploading = attachments.some((item) => item.status === 'uploading');
    if (hasUploading) {
      composerError = 'Please wait for uploads to finish.';
      return;
    }
    const hasErrored = attachments.some((item) => item.status === 'error');
    if (hasErrored) {
      composerError = 'Remove failed uploads before sending.';
      return;
    }
    const readyAttachments = attachments
      .filter((item) => item.status === 'ready' && item.resource)
      .map((item) => item.resource as AttachmentResource);

    if (!trimmed && readyAttachments.length === 0) {
      return;
    }

    dispatch('submit', { text: trimmed, attachments: readyAttachments });
    prompt = '';
    composerError = null;
    resetAttachments();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  function handleCancel(): void {
    dispatch('cancel');
  }

  function handleDictationClick(): void {
    if (isStreaming && $speechState.mode !== 'dictation') {
      return;
    }
    if ($speechState.connecting && !$speechState.recording && $speechState.mode !== 'dictation') {
      return;
    }
    dispatch('startDictation');
  }

  function handleConversationClick(): void {
    const conversationActive = $speechState.conversationActive;
    if (isStreaming && !conversationActive) {
      return;
    }
    if ($speechState.connecting && !$speechState.recording && !conversationActive) {
      return;
    }
    dispatch('startConversationMode');
  }

  $: dictationActive =
    $speechState.mode === 'dictation' && ($speechState.recording || $speechState.connecting);
  $: conversationActive = $speechState.conversationActive;
  $: speechBusy = $speechState.connecting && !$speechState.recording;
  $: speechError = $speechState.error;

  function openFileDialog(): void {
    if (isStreaming) {
      return;
    }
    composerError = null;
    fileInput?.click();
  }

  function handleFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files ? Array.from(input.files) : [];
    input.value = '';
    if (!files.length) {
      return;
    }

    const remainingSlots = MAX_ATTACHMENTS - attachments.length;
    if (remainingSlots <= 0) {
      composerError = `You can attach up to ${MAX_ATTACHMENTS} images.`;
      return;
    }

    const sessionId = chatStore.ensureSessionId();
    const toProcess = files.slice(0, remainingSlots);

    if (files.length > remainingSlots) {
      composerError = `Only ${MAX_ATTACHMENTS} images allowed per message.`;
    }

    for (const file of toProcess) {
      if (!ALLOWED_TYPES.has(file.type)) {
        composerError = 'Unsupported image format.';
        continue;
      }
      if (file.size > MAX_SIZE_BYTES) {
        composerError = 'Images must be 10 MB or less.';
        continue;
      }
      const previewUrl = URL.createObjectURL(file);
      const draft: AttachmentDraft = {
        id: createLocalId(),
        file,
        previewUrl,
        status: 'uploading',
      };
      attachments = [...attachments, draft];
      void uploadDraftAttachment(draft, sessionId);
    }
  }

  async function uploadDraftAttachment(draft: AttachmentDraft, sessionId: string): Promise<void> {
    try {
      const { attachment } = await uploadAttachment(draft.file, sessionId);
      attachments = attachments.map((item) =>
        item.id === draft.id ? { ...item, status: 'ready', resource: attachment } : item,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to upload image.';
      attachments = attachments.map((item) =>
        item.id === draft.id ? { ...item, status: 'error', error: message } : item,
      );
    }
  }

  function removeAttachment(id: string): void {
    attachments = attachments.filter((item) => {
      if (item.id === id && item.previewUrl) {
        URL.revokeObjectURL(item.previewUrl);
      }
      return item.id !== id;
    });
    if (!attachments.length) {
      composerError = null;
    }
  }

  function resetAttachments(): void {
    attachments.forEach((item) => {
      if (item.previewUrl) {
        URL.revokeObjectURL(item.previewUrl);
      }
    });
    attachments = [];
  }

  onDestroy(() => {
    resetAttachments();
  });
</script>

<form class="composer" on:submit|preventDefault={handleSubmit}>
  <div class="composer-content">
    {#if attachments.length}
      <div class="attachment-strip">
        {#each attachments as attachment (attachment.id)}
          <div
            class="attachment-chip"
            class:uploading={attachment.status === 'uploading'}
            class:error={attachment.status === 'error'}
          >
            <img src={attachment.previewUrl} alt="Attachment preview" loading="lazy" />
            {#if attachment.status === 'uploading'}
              <span class="chip-status">Uploading…</span>
            {/if}
            {#if attachment.status === 'error'}
              <span class="chip-status">{attachment.error ?? 'Upload failed.'}</span>
            {/if}
            <button
              type="button"
              class="remove-attachment"
              on:click={() => removeAttachment(attachment.id)}
              aria-label="Remove image"
            >
              ×
            </button>
          </div>
        {/each}
      </div>
    {/if}

    {#if composerError}
      <div class="composer-error" role="alert">{composerError}</div>
    {/if}
    {#if speechError}
      <div class="composer-error voice" role="alert">{speechError}</div>
    {/if}

    <div class="input-shell">
      <button
        type="button"
        class="icon-button leading"
        aria-label="Attach image"
        on:click={openFileDialog}
        disabled={isStreaming || attachments.length >= MAX_ATTACHMENTS}
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

      <input
        bind:this={fileInput}
        class="sr-only"
        type="file"
        accept="image/png,image/jpeg,image/webp,image/gif"
        multiple
        on:change={handleFileChange}
      />

      <textarea
        rows="1"
        bind:value={prompt}
        on:keydown={handleKeydown}
        placeholder={isStreaming ? 'Waiting for response…' : 'Type here…'}
        aria-disabled={isStreaming}
      ></textarea>

      <div class="composer-actions">
        {#if isStreaming}
          <button type="button" class="stop-inline" on:click={handleCancel}>
            <span aria-hidden="true" class="stop-indicator"></span>
            Stop
          </button>
        {/if}
        <button
          type="button"
          class="icon-button"
          aria-label="Start dictation"
          title="Start dictation"
          on:click={handleDictationClick}
          disabled={(isStreaming && !dictationActive) || (speechBusy && !dictationActive)}
          aria-pressed={dictationActive ? 'true' : 'false'}
          data-active={dictationActive ? 'true' : 'false'}
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
        <button
          type="button"
          class="icon-button"
          aria-label="Start conversation mode"
          title="Start conversation mode"
          on:click={handleConversationClick}
          disabled={(isStreaming && !conversationActive) || (speechBusy && !conversationActive)}
          aria-pressed={conversationActive ? 'true' : 'false'}
          data-active={conversationActive ? 'true' : 'false'}
        >
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

<style>
  .composer {
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    padding: 0 0 1rem;
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
  .attachment-strip {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
  }
  .attachment-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem 0.35rem 0.35rem;
    border-radius: 0.85rem;
    background: rgba(23, 32, 52, 0.85);
    border: 1px solid rgba(67, 91, 136, 0.45);
  }
  .attachment-chip.uploading {
    border-color: rgba(129, 140, 248, 0.65);
  }
  .attachment-chip.error {
    border-color: rgba(248, 113, 113, 0.65);
    background: rgba(55, 20, 20, 0.75);
  }
  .attachment-chip img {
    width: 48px;
    height: 48px;
    border-radius: 0.65rem;
    object-fit: cover;
  }
  .chip-status {
    font-size: 0.75rem;
    color: rgba(226, 232, 240, 0.9);
  }
  .attachment-chip.error .chip-status {
    color: #fecaca;
  }
  .remove-attachment {
    appearance: none;
    border: none;
    background: rgba(15, 23, 42, 0.7);
    color: rgba(226, 232, 240, 0.9);
    border-radius: 999px;
    width: 1.5rem;
    height: 1.5rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
  }
  .remove-attachment:hover,
  .remove-attachment:focus-visible {
    background: rgba(79, 70, 229, 0.85);
    color: #fff;
    outline: none;
  }
  .composer-error {
    font-size: 0.8rem;
    color: #fca5a5;
    background: rgba(62, 20, 31, 0.6);
    border: 1px solid rgba(248, 113, 113, 0.4);
    padding: 0.45rem 0.75rem;
    border-radius: 0.65rem;
  }
  .composer-error.voice {
    color: #fbbf24;
    background: rgba(92, 62, 12, 0.6);
    border-color: rgba(251, 191, 36, 0.4);
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
    color: rgba(208, 214, 235, 0.6);
  }
  .icon-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 999px;
    border: none;
    background: rgba(23, 32, 52, 0.85);
    color: inherit;
    cursor: pointer;
    transition: background 0.12s ease;
  }
  .icon-button.leading {
    background: rgba(29, 41, 69, 0.9);
  }
  .icon-button:hover,
  .icon-button:focus {
    background: rgba(46, 64, 101, 0.9);
    outline: none;
  }
  .icon-button[data-active='true'] {
    background: rgba(79, 70, 229, 0.85);
    color: #f8f9ff;
  }
  .icon-button[data-active='true']:hover,
  .icon-button[data-active='true']:focus {
    background: rgba(99, 102, 241, 0.9);
  }
  .icon-button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .composer-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .stop-inline {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    background: none;
    border: 1px solid rgba(236, 72, 153, 0.6);
    color: #f472b6;
    border-radius: 999px;
    padding: 0.3rem 0.75rem;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .stop-inline:hover,
  .stop-inline:focus {
    border-color: rgba(244, 114, 182, 0.9);
    color: #fecdd3;
    outline: none;
  }
  .stop-indicator {
    width: 0.75rem;
    height: 0.75rem;
    border-radius: 0.2rem;
    background: linear-gradient(135deg, #f472b6, #f97316);
  }
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    border: 0;
  }
</style>
