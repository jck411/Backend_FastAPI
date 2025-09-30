<script lang="ts">
  import { createEventDispatcher, onMount } from "svelte";

  export let value = "";
  export let originalValue = "";
  export let saving = false;
  export let disabled = false;

  const dispatch = createEventDispatcher<{
    submit: { text: string };
    cancel: void;
  }>();

  let textarea: HTMLTextAreaElement | null = null;

  onMount(() => {
    if (textarea) {
      textarea.focus();
      textarea.setSelectionRange(0, textarea.value.length);
    }
  });

  $: trimmedValue = value.trim();
  $: canSubmit = Boolean(trimmedValue) && !saving && !disabled;
  $: isModified = trimmedValue !== originalValue.trim();

  function handleSubmit(): void {
    if (!canSubmit) {
      return;
    }
    dispatch("submit", { text: trimmedValue });
  }

  function handleCancel(): void {
    if (saving) {
      return;
    }
    dispatch("cancel");
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }
</script>

<form class="message-editor" on:submit|preventDefault={handleSubmit}>
  <div class="editor-shell">
    <div class="editor-header">
      <span>Edit message</span>
      {#if isModified}
        <span class="editor-status">Updated</span>
      {/if}
    </div>
    <textarea
      bind:this={textarea}
      bind:value={value}
      rows="3"
      placeholder="Update your message..."
      on:keydown={handleKeydown}
      disabled={saving || disabled}
    ></textarea>
    <div class="editor-actions">
      <button type="button" class="button secondary" on:click={handleCancel} disabled={saving}>
        Cancel
      </button>
      <button type="submit" class="button primary" disabled={!canSubmit}>
        {#if saving}
          Sending…
        {:else}
          Save &amp; Send
        {/if}
      </button>
    </div>
  </div>
</form>

<style>
  .message-editor {
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    padding: 0 0 1.25rem;
  }
  .editor-shell {
    width: min(800px, 100%);
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 1rem 1.25rem 1.25rem;
    border-radius: 1rem;
    background: rgba(11, 18, 34, 0.9);
    border: 1px solid rgba(57, 82, 124, 0.55);
    box-shadow: 0 12px 28px rgba(4, 8, 20, 0.45);
  }
  .editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #96a0ba;
  }
  .editor-status {
    text-transform: none;
    font-size: 0.75rem;
    color: rgba(177, 189, 220, 0.85);
  }
  textarea {
    width: 100%;
    min-height: 4rem;
    background: rgba(6, 10, 20, 0.68);
    border: 1px solid rgba(57, 82, 124, 0.55);
    border-radius: 0.75rem;
    padding: 0.75rem 1rem;
    resize: vertical;
    color: inherit;
    font: inherit;
    line-height: 1.5;
  }
  textarea:focus {
    outline: none;
    border-color: rgba(138, 162, 210, 0.9);
    box-shadow: 0 0 0 1px rgba(138, 162, 210, 0.55);
  }
  textarea:disabled {
    opacity: 0.75;
    cursor: not-allowed;
  }
  .editor-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.75rem;
  }
  .button {
    padding: 0.5rem 1.1rem;
    border-radius: 999px;
    border: none;
    font-size: 0.85rem;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  }
  .button.primary {
    background: rgba(60, 99, 200, 0.85);
    color: #f8fafc;
  }
  .button.primary:hover,
  .button.primary:focus {
    background: rgba(86, 132, 232, 0.95);
  }
  .button.primary:disabled {
    background: rgba(60, 99, 200, 0.5);
    cursor: not-allowed;
  }
  .button.secondary {
    background: rgba(29, 41, 69, 0.9);
    color: #d1d5e5;
  }
  .button.secondary:hover,
  .button.secondary:focus {
    background: rgba(46, 64, 101, 0.95);
  }
  .button.secondary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
