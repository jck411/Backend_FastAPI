<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import type { MessageCitation } from "../../stores/chat";
    import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";

    const dispatch = createEventDispatcher<{ close: void }>();

    export let open = false;
    export let messageId: string | null = null;
    export let citations: MessageCitation[] = [];

    function handleClose(): void {
        dispatch("close");
    }
</script>

{#if open}
    <ModelSettingsDialog
        {open}
        labelledBy="citations-modal-title"
        modalClass="citations-modal"
        bodyClass="citations-modal-body"
        closeLabel="Close web citations"
        on:close={handleClose}
    >
        <svelte:fragment slot="heading">
            <h2 id="citations-modal-title">Web Citations</h2>
            {#if messageId}
                <p class="model-settings-subtitle">Message ID: {messageId}</p>
            {/if}
        </svelte:fragment>

        {#if citations.length === 0}
            <p class="status">No web citations found.</p>
        {:else}
            <ul class="citations-modal-list">
                {#each citations as citation, index}
                    <li class="citations-modal-item">
                        <div class="citations-modal-header">
                            <span class="citations-modal-number"
                                >Citation {index + 1}</span
                            >
                            <a
                                class="citations-modal-link"
                                href={citation.url}
                                target="_blank"
                                rel="noreferrer"
                            >
                                Visit source
                            </a>
                        </div>
                        {#if citation.title}
                            <h3 class="citations-modal-title">
                                {citation.title}
                            </h3>
                        {/if}
                        <div class="citations-modal-url">{citation.url}</div>
                        {#if citation.content}
                            <p class="citations-modal-content">
                                {citation.content}
                            </p>
                        {/if}
                        {#if citation.startIndex !== undefined || citation.endIndex !== undefined}
                            <div class="citations-modal-meta">
                                {#if citation.startIndex !== undefined}
                                    <span>Start: {citation.startIndex}</span>
                                {/if}
                                {#if citation.endIndex !== undefined}
                                    <span>End: {citation.endIndex}</span>
                                {/if}
                            </div>
                        {/if}
                    </li>
                {/each}
            </ul>
        {/if}
    </ModelSettingsDialog>
{/if}

<style>
    .status {
        font-size: 0.9rem;
        color: rgba(199, 210, 254, 0.7);
        text-align: center;
        padding: 2rem 1rem;
    }
    .citations-modal-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
    }
    .citations-modal-item {
        border: 1px solid rgba(67, 91, 136, 0.4);
        border-radius: 0.75rem;
        background: rgba(9, 14, 26, 0.6);
        padding: 1rem 1.25rem;
        display: flex;
        flex-direction: column;
        gap: 0.65rem;
    }
    .citations-modal-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
    }
    .citations-modal-number {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #facc15;
    }
    .citations-modal-link {
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.3rem 0.65rem;
        border-radius: 0.4rem;
        background: rgba(56, 189, 248, 0.12);
        color: #7dd3fc;
        text-decoration: none;
        border: 1px solid rgba(56, 189, 248, 0.25);
        transition:
            background 0.14s ease,
            border-color 0.14s ease,
            color 0.14s ease;
    }
    .citations-modal-link:hover,
    .citations-modal-link:focus-visible {
        background: rgba(56, 189, 248, 0.2);
        border-color: rgba(56, 189, 248, 0.45);
        color: #bae6fd;
        outline: none;
    }
    .citations-modal-title {
        margin: 0;
        font-size: 0.95rem;
        font-weight: 600;
        color: #f3f5ff;
        line-height: 1.4;
    }
    .citations-modal-url {
        font-size: 0.75rem;
        color: #94addb;
        word-break: break-all;
        font-family: "Fira Code", "SFMono-Regular", Menlo, Monaco, Consolas,
            "Liberation Mono", "Courier New", monospace;
    }
    .citations-modal-content {
        margin: 0;
        font-size: 0.85rem;
        line-height: 1.5;
        color: rgba(224, 231, 255, 0.85);
        padding: 0.75rem 0.85rem;
        background: rgba(15, 22, 38, 0.85);
        border-radius: 0.5rem;
        border: 1px solid rgba(67, 91, 136, 0.35);
    }
    .citations-modal-meta {
        display: flex;
        gap: 0.85rem;
        font-size: 0.72rem;
        color: rgba(159, 179, 216, 0.75);
        font-family: "Fira Code", "SFMono-Regular", Menlo, Monaco, Consolas,
            "Liberation Mono", "Courier New", monospace;
    }
</style>
