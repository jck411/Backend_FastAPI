<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let prompt = '';
  export let isStreaming = false;

  const dispatch = createEventDispatcher<{
    submit: { text: string };
    cancel: void;
  }>();

  function handleSubmit(): void {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    dispatch('submit', { text: trimmed });
    prompt = '';
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
</script>

<form class="composer" on:submit|preventDefault={handleSubmit}>
  <div class="composer-content">
    <div class="input-shell">
      <button type="button" class="icon-button leading" aria-label="New prompt">
        <svg
          width="18"
          height="18"
          viewBox="0 0 18 18"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path d="M9 2v14M2 9h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
        </svg>
      </button>

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
        <button type="button" class="icon-button" aria-label="Toggle microphone">
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

<style>
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
  }
  .icon-button.leading {
    background: rgba(29, 41, 69, 0.9);
  }
  .icon-button:hover,
  .icon-button:focus {
    background: rgba(46, 64, 101, 0.9);
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
  }
  .stop-indicator {
    width: 0.75rem;
    height: 0.75rem;
    border-radius: 2px;
    background: currentColor;
  }
</style>
