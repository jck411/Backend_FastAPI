<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import type { PresetListItem } from "../../api/types";
    import { chatStore } from "../../stores/chat";
    import { modelSettingsStore } from "../../stores/modelSettings";
    import { presetsStore } from "../../stores/presets";

    export let open = false;

    const dispatch = createEventDispatcher<{ close: void }>();

    let dialogEl: HTMLElement | null = null;
    let creatingName = "";
    let confirmingDelete: string | null = null;
    let nameInputEl: HTMLInputElement | null = null;
    let initialFocusDone = false;

    let loadedOnOpen = false;

    $: if (open && !loadedOnOpen) {
        loadedOnOpen = true;
        presetsStore.load();
    }
    $: if (!open && loadedOnOpen) {
        loadedOnOpen = false;
    }

    $: if (open && !initialFocusDone) {
        initialFocusDone = true;
        setTimeout(() => {
            nameInputEl?.focus();
        }, 0);
    }
    $: if (!open && initialFocusDone) {
        initialFocusDone = false;
    }

    function handleBackdrop(event: MouseEvent): void {
        if (event.target === event.currentTarget) {
            dispatch("close");
        }
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (!open) return;
        if (event.key === "Escape") {
            event.preventDefault();
            dispatch("close");
        }
    }

    async function handleCreate(): Promise<void> {
        const name = creatingName.trim();
        if (!name) return;
        // Ensure backend active model matches current UI selection before snapshotting
        await modelSettingsStore.load($chatStore.selectedModel);
        const result = await presetsStore.create(name);
        if (result) {
            creatingName = "";
        }
    }

    async function handleApply(item: PresetListItem): Promise<void> {
        const result = await presetsStore.apply(item.name);
        if (result?.model) {
            // Keep chat model synchronized with applied preset
            chatStore.setModel(result.model);
        }
    }

    async function handleSaveSnapshot(item: PresetListItem): Promise<void> {
        // Ensure backend active model matches current UI selection before snapshotting
        await modelSettingsStore.load($chatStore.selectedModel);
        await presetsStore.saveSnapshot(item.name);
    }

    async function handleDelete(item: PresetListItem): Promise<void> {
        if (confirmingDelete === item.name) {
            const ok = await presetsStore.remove(item.name);
            confirmingDelete = null;
            return;
        }
        confirmingDelete = item.name;
        // Reset the confirmation after a short delay to avoid sticky state
        setTimeout(() => {
            if (confirmingDelete === item.name) {
                confirmingDelete = null;
            }
        }, 3000);
    }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
    <div class="presets-layer">
        <button
            type="button"
            class="presets-backdrop"
            aria-label="Close presets"
            on:click={handleBackdrop}
        ></button>

        <div
            class="presets-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="presets-title"
            tabindex="-1"
            bind:this={dialogEl}
        >
            <header class="presets-header">
                <div class="presets-heading">
                    <h2 id="presets-title">Presets</h2>
                    <p class="presets-subtitle">
                        Save and manage snapshots of the current configuration.
                    </p>
                </div>
                <div class="presets-actions">
                    <button
                        type="button"
                        class="modal-close"
                        on:click={() => dispatch("close")}
                        aria-label="Close"
                    >
                        Close
                    </button>
                </div>
            </header>

            <section class="presets-body">
                <!-- Create new preset -->
                <div class="create-row">
                    <input
                        type="text"
                        placeholder="Preset name"
                        bind:value={creatingName}
                        aria-label="Preset name"
                        bind:this={nameInputEl}
                        on:keydown={(e) =>
                            e.key === "Enter" ? handleCreate() : null}
                    />
                    <button
                        type="button"
                        class="primary"
                        on:click={handleCreate}
                        disabled={!creatingName.trim() ||
                            $presetsStore.creating}
                        aria-busy={$presetsStore.creating}
                    >
                        {$presetsStore.creating
                            ? "Creating…"
                            : "Create from current"}
                    </button>
                </div>

                {#if $presetsStore.error}
                    <p class="status error">{$presetsStore.error}</p>
                {/if}

                {#if $presetsStore.loading}
                    <p class="status">Loading presets…</p>
                {:else if !$presetsStore.items.length}
                    <p class="status">No presets saved yet.</p>
                {:else}
                    <ul class="preset-list" aria-live="polite">
                        {#each $presetsStore.items as item (item.name)}
                            <li class="preset-item">
                                <div class="meta">
                                    <div class="name">{item.name}</div>
                                    <div class="details">
                                        <span class="model">{item.model}</span>
                                        <span class="timestamps">
                                            <span title="Created at"
                                                >{new Date(
                                                    item.created_at,
                                                ).toLocaleString()}</span
                                            >
                                            <span aria-hidden="true">·</span>
                                            <span title="Updated at"
                                                >{new Date(
                                                    item.updated_at,
                                                ).toLocaleString()}</span
                                            >
                                        </span>
                                    </div>
                                </div>
                                <div class="actions">
                                    <button
                                        type="button"
                                        class="ghost small"
                                        on:click={() => handleApply(item)}
                                        disabled={$presetsStore.applying ===
                                            item.name}
                                        aria-busy={$presetsStore.applying ===
                                            item.name}
                                        title="Apply this preset (model, settings, system prompt, MCP servers)"
                                    >
                                        {$presetsStore.applying === item.name
                                            ? "Applying…"
                                            : "Apply"}
                                    </button>
                                    <button
                                        type="button"
                                        class="ghost small"
                                        on:click={() =>
                                            handleSaveSnapshot(item)}
                                        disabled={$presetsStore.saving}
                                        aria-busy={$presetsStore.saving}
                                        title="Overwrite preset with current configuration"
                                    >
                                        {$presetsStore.saving
                                            ? "Saving…"
                                            : "Save snapshot"}
                                    </button>
                                    <button
                                        type="button"
                                        class="danger small"
                                        on:click={() => handleDelete(item)}
                                        disabled={$presetsStore.deleting ===
                                            item.name}
                                        aria-busy={$presetsStore.deleting ===
                                            item.name}
                                        title="Delete preset"
                                    >
                                        {confirmingDelete === item.name
                                            ? "Confirm delete"
                                            : $presetsStore.deleting ===
                                                item.name
                                              ? "Deleting…"
                                              : "Delete"}
                                    </button>
                                </div>
                            </li>
                        {/each}
                    </ul>
                {/if}
            </section>

            <footer class="presets-footer">
                {#if $presetsStore.lastApplied}
                    <span class="status"
                        >Applied preset: {$presetsStore.lastApplied}</span
                    >
                {:else if $presetsStore.lastResult}
                    <span class="status"
                        >Saved: {$presetsStore.lastResult.name}</span
                    >
                {:else}
                    <span class="status"
                        >Create, update, or apply a preset.</span
                    >
                {/if}
            </footer>
        </div>
    </div>
{/if}

<style>
    .presets-layer {
        position: fixed;
        inset: 0;
        z-index: 40;
    }
    .presets-backdrop {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        background: rgba(2, 6, 12, 0.6);
        border: none;
    }
    .presets-modal {
        position: absolute;
        inset: 6% 0 auto 0;
        margin: 0 auto;
        width: min(820px, calc(100% - 2rem));
        border-radius: 0.75rem;
        border: 1px solid rgba(37, 49, 77, 0.9);
        background: rgba(9, 14, 26, 0.95);
        color: #e8ecf8;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
        display: flex;
        flex-direction: column;
        outline: none;
    }
    .presets-header,
    .presets-footer {
        padding: 0.9rem 1.25rem;
        border-bottom: 1px solid rgba(37, 49, 77, 0.6);
    }
    .presets-footer {
        border-top: 1px solid rgba(37, 49, 77, 0.6);
        border-bottom: none;
    }
    .presets-heading h2 {
        margin: 0 0 0.25rem;
        font-size: 1.1rem;
    }
    .presets-subtitle {
        margin: 0;
        color: #9fb3d8;
        font-size: 0.9rem;
    }
    .presets-actions {
        margin-left: auto;
        display: flex;
        gap: 0.5rem;
    }
    .modal-close {
        background: none;
        border: 1px solid #25314d;
        border-radius: 999px;
        color: #f2f4f8;
        padding: 0.4rem 0.9rem;
        cursor: pointer;
    }
    .modal-close:hover {
        border-color: #38bdf8;
        color: #38bdf8;
    }
    .presets-body {
        padding: 1rem 1.25rem;
    }
    .create-row {
        display: flex;
        gap: 0.5rem;
        margin-bottom: 1rem;
    }
    .create-row input[type="text"] {
        flex: 1;
        min-width: 200px;
        padding: 0.55rem 0.75rem;
        border-radius: 0.5rem;
        border: 1px solid #25314d;
        background: rgba(9, 14, 26, 0.9);
        color: #f2f4f8;
        font: inherit;
    }
    .create-row .primary {
        border: 1px solid #2c6f8c;
        background: rgba(3, 76, 112, 0.4);
        color: #c7e9ff;
        border-radius: 999px;
        padding: 0.55rem 0.9rem;
        cursor: pointer;
    }
    .create-row .primary[disabled] {
        opacity: 0.6;
        cursor: not-allowed;
    }
    .preset-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 0.5rem;
    }
    .preset-item {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        border: 1px solid rgba(37, 49, 77, 0.6);
        border-radius: 0.65rem;
        padding: 0.6rem 0.75rem;
        background: rgba(12, 19, 34, 0.6);
    }
    .preset-item .meta {
        flex: 1;
        min-width: 0;
    }
    .preset-item .name {
        font-weight: 600;
    }
    .preset-item .details {
        display: flex;
        gap: 0.5rem;
        color: #9fb3d8;
        font-size: 0.85rem;
        flex-wrap: wrap;
    }
    .preset-item .details .model {
        color: #c7d7f4;
    }
    .preset-item .actions {
        display: inline-flex;
        gap: 0.4rem;
    }
    .ghost.small,
    .danger.small {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.35rem;
        background: none;
        border: 1px solid #25314d;
        border-radius: 999px;
        color: #f2f4f8;
        padding: 0.35rem 0.7rem;
        white-space: nowrap;
        cursor: pointer;
        font: inherit;
    }
    .ghost.small:hover {
        border-color: #38bdf8;
        color: #38bdf8;
    }
    .danger.small {
        border-color: rgba(139, 35, 35, 0.6);
        color: #fecaca;
    }
    .danger.small:hover {
        border-color: rgba(200, 55, 55, 0.85);
        color: #ffb4b4;
    }
    .status {
        font-size: 0.85rem;
        color: #9fb3d8;
    }
    .status.error {
        color: #fca5a5;
    }
</style>
