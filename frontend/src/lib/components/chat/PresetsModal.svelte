<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import type { PresetListItem, PresetModelFilters } from "../../api/types";
    import { chatStore } from "../../stores/chat";
    import { modelSettingsStore } from "../../stores/modelSettings";
    import { presetsStore } from "../../stores/presets";
    import { suggestionsStore } from "../../stores/suggestions";
    import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";

    export let open = false;

    const dispatch = createEventDispatcher<{ close: void }>();

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

    function requestClose(): void {
        dispatch("close");
    }

    function countActiveFilters(
        filters: PresetModelFilters | null | undefined,
    ): number {
        if (!filters) return 0;

        let count = 0;

        // Count each multi-select filter
        if (
            filters.inputModalities &&
            (filters.inputModalities.include?.length ||
                filters.inputModalities.exclude?.length)
        )
            count++;
        if (
            filters.outputModalities &&
            (filters.outputModalities.include?.length ||
                filters.outputModalities.exclude?.length)
        )
            count++;
        if (
            filters.series &&
            (filters.series.include?.length || filters.series.exclude?.length)
        )
            count++;
        if (
            filters.providers &&
            (filters.providers.include?.length ||
                filters.providers.exclude?.length)
        )
            count++;
        if (
            filters.supportedParameters &&
            (filters.supportedParameters.include?.length ||
                filters.supportedParameters.exclude?.length)
        )
            count++;
        if (
            filters.moderation &&
            (filters.moderation.include?.length ||
                filters.moderation.exclude?.length)
        )
            count++;

        // Count range filters
        if (filters.minContext !== null && filters.minContext !== undefined)
            count++;
        if (
            filters.minPromptPrice !== null &&
            filters.minPromptPrice !== undefined
        )
            count++;
        if (
            filters.maxPromptPrice !== null &&
            filters.maxPromptPrice !== undefined
        )
            count++;

        return count;
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
        // Reload suggestions after applying preset
        await suggestionsStore.load();
    }

    async function handleSaveSnapshot(item: PresetListItem): Promise<void> {
        // Ensure backend active model matches current UI selection before snapshotting
        await modelSettingsStore.load($chatStore.selectedModel);
        await presetsStore.saveSnapshot(item.name);
    }

    async function handleDelete(item: PresetListItem): Promise<void> {
        if (item.is_default) {
            // Do not allow deletion of default preset
            return;
        }
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

    async function handleSetDefault(item: PresetListItem): Promise<void> {
        await presetsStore.setDefault(item.name);
    }
</script>

{#if open}
    <ModelSettingsDialog
        {open}
        labelledBy="presets-title"
        modalClass="presets-modal"
        bodyClass="presets-body"
        closeLabel="Close presets"
        on:close={requestClose}
    >
        <svelte:fragment slot="heading">
            <h2 id="presets-title">Presets</h2>
            <p class="model-settings-subtitle">
                Save and manage snapshots of the current configuration.
            </p>
        </svelte:fragment>

        <div class="create-row">
            <input
                type="text"
                placeholder="Preset name"
                bind:value={creatingName}
                aria-label="Preset name"
                bind:this={nameInputEl}
                on:keydown={(e) => (e.key === "Enter" ? handleCreate() : null)}
            />
            <button
                type="button"
                class="primary"
                on:click={handleCreate}
                disabled={!creatingName.trim() || $presetsStore.creating}
                aria-busy={$presetsStore.creating}
            >
                {$presetsStore.creating ? "Creating…" : "Create from current"}
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
                            <div class="name">
                                {item.name}
                                {#if item.is_default}
                                    <span
                                        class="default-badge"
                                        title="Default preset">Default</span
                                    >
                                {/if}
                                {#if item.has_filters}
                                    <span
                                        class="filters-badge"
                                        title="Contains model explorer filters"
                                    >
                                        <svg
                                            width="14"
                                            height="14"
                                            viewBox="0 0 24 24"
                                            fill="none"
                                            stroke="currentColor"
                                            stroke-width="2"
                                            stroke-linecap="round"
                                            stroke-linejoin="round"
                                        >
                                            <polygon
                                                points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"
                                            ></polygon>
                                        </svg>
                                        Filters
                                    </span>
                                {/if}
                            </div>
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
                                disabled={$presetsStore.applying === item.name}
                                aria-busy={$presetsStore.applying === item.name}
                                title="Apply this preset (model, settings, system prompt, MCP servers)"
                            >
                                {$presetsStore.applying === item.name
                                    ? "Applying…"
                                    : "Apply"}
                            </button>
                            <button
                                type="button"
                                class="ghost small"
                                on:click={() => handleSaveSnapshot(item)}
                                disabled={$presetsStore.saving}
                                aria-busy={$presetsStore.saving}
                                title="Overwrite preset with current configuration"
                            >
                                {$presetsStore.saving
                                    ? "Saving…"
                                    : "Save snapshot"}
                            </button>
                            {#if !item.is_default}
                                <button
                                    type="button"
                                    class="ghost small"
                                    on:click={() => handleSetDefault(item)}
                                    disabled={$presetsStore.settingDefault ===
                                        item.name}
                                    aria-busy={$presetsStore.settingDefault ===
                                        item.name}
                                    title="Set as default preset to load on startup"
                                >
                                    {$presetsStore.settingDefault === item.name
                                        ? "Setting…"
                                        : "Set as default"}
                                </button>
                            {/if}
                            <button
                                type="button"
                                class="danger small"
                                on:click={() => handleDelete(item)}
                                disabled={item.is_default ||
                                    $presetsStore.deleting === item.name}
                                aria-busy={$presetsStore.deleting === item.name}
                                title={item.is_default
                                    ? "Cannot delete default preset"
                                    : "Delete preset"}
                            >
                                {confirmingDelete === item.name
                                    ? "Confirm delete"
                                    : $presetsStore.deleting === item.name
                                      ? "Deleting…"
                                      : "Delete"}
                            </button>
                        </div>
                    </li>
                {/each}
            </ul>
        {/if}

        <footer slot="footer" class="model-settings-footer">
            {#if $presetsStore.lastApplied}
                <span class="status"
                    >Applied preset: {$presetsStore.lastApplied}</span
                >
            {:else if $presetsStore.lastResult}
                <span class="status"
                    >Saved: {$presetsStore.lastResult.name}</span
                >
            {:else}
                <span class="status">Create, update, or apply a preset.</span>
            {/if}
        </footer>
    </ModelSettingsDialog>
{/if}

<style>
    :global(.presets-modal) {
        width: min(820px, calc(100% - 2rem));
        max-height: min(80vh, 720px);
    }
    :global(.presets-body) {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
    }
    .create-row {
        display: flex;
        gap: 0.5rem;
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
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .default-badge {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        font-size: 0.75rem;
        font-weight: 500;
        border-radius: 999px;
        background: rgba(34, 197, 94, 0.2);
        color: #86efac;
        border: 1px solid rgba(34, 197, 94, 0.4);
    }
    .filters-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.15rem 0.5rem;
        font-size: 0.75rem;
        font-weight: 500;
        border-radius: 999px;
        background: rgba(59, 130, 246, 0.15);
        color: #93c5fd;
        border: 1px solid rgba(59, 130, 246, 0.3);
    }
    .filters-badge svg {
        width: 12px;
        height: 12px;
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
    .preset-item .actions button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.35rem;
        white-space: nowrap;
        font: inherit;
    }
    .danger.small {
        background: none;
        border: 1px solid rgba(139, 35, 35, 0.6);
        border-radius: 999px;
        padding: 0.35rem 0.7rem;
        color: #fecaca;
        cursor: pointer;
    }
    .danger.small:hover {
        border-color: rgba(200, 55, 55, 0.85);
        color: #ffb4b4;
    }
</style>
