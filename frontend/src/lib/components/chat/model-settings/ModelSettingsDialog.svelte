<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import './model-settings-styles.css';

  export let open = false;
  export let labelledBy: string | null = null;
  export let modalClass = '';
  export let bodyClass = '';
  export let layerClass = '';
  export let closeLabel = 'Close modal';
  export let closeOnBackdrop = true;
  export let focusOnOpen = true;
  export let closeDisabled = false;

  const dispatch = createEventDispatcher<{ close: void }>();

  let dialogEl: HTMLElement | null = null;
  let wasOpen = false;

  $: if (open && !wasOpen) {
    wasOpen = true;
    if (focusOnOpen && dialogEl) {
      dialogEl.focus();
    }
  } else if (!open && wasOpen) {
    wasOpen = false;
  }

  function handleBackdrop(event: MouseEvent): void {
    if (!closeOnBackdrop || closeDisabled) {
      return;
    }
    if (event.target === event.currentTarget) {
      dispatch('close');
    }
  }

  function handleClose(): void {
    if (closeDisabled) {
      return;
    }
    dispatch('close');
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open || closeDisabled) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      dispatch('close');
    }
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class={`model-settings-layer ${layerClass}`.trim()}>
    <button
      type="button"
      class="model-settings-backdrop"
      aria-label={closeLabel}
      on:click={handleBackdrop}
    ></button>
    <div
      class={`model-settings-modal ${modalClass}`.trim()}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy || undefined}
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="model-settings-header">
        <div class="model-settings-heading">
          <slot name="heading" />
        </div>
        <div class="model-settings-actions">
          <slot name="actions" />
          <button
            type="button"
            class="modal-close"
            on:click={handleClose}
            aria-label={closeLabel}
            disabled={closeDisabled}
          >
            Close
          </button>
        </div>
      </header>
      <section class={`model-settings-body ${bodyClass}`.trim()}>
        <slot />
      </section>
      <slot name="footer" />
    </div>
  </div>
{/if}
