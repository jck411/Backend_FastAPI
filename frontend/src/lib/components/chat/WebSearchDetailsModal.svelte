<script lang="ts">
    import { createEventDispatcher } from "svelte";
    import type { WebSearchDetails } from "../../stores/chatModals/webSearchDetailsModal";
    import ModelSettingsDialog from "./model-settings/ModelSettingsDialog.svelte";

    const dispatch = createEventDispatcher<{ close: void }>();

    export let open = false;
    export let messageId: string | null = null;
    export let details: WebSearchDetails | null = null;

    function handleClose(): void {
        dispatch("close");
    }

    function formatEngine(engine: string | null): string {
        if (!engine) return "Auto";
        if (engine === "native") return "Native (OpenAI/Anthropic)";
        if (engine === "exa") return "Exa";
        return engine;
    }

    function formatContextSize(contextSize: string | null): string {
        if (!contextSize) return "Default";
        return contextSize.charAt(0).toUpperCase() + contextSize.slice(1);
    }
</script>

{#if open}
    <ModelSettingsDialog
        {open}
        labelledBy="web-search-details-modal-title"
        modalClass="web-search-details-modal"
        bodyClass="web-search-details-modal-body"
        closeLabel="Close web search details"
        on:close={handleClose}
    >
        <svelte:fragment slot="heading">
            <h2 id="web-search-details-modal-title">Web Search Details</h2>
            {#if messageId}
                <p class="model-settings-subtitle">Message ID: {messageId}</p>
            {/if}
        </svelte:fragment>

        {#if !details}
            <p class="status modal-empty-state">
                No web search details available.
            </p>
        {:else}
            <div class="details-grid">
                <div class="detail-item">
                    <div class="detail-label">Search Engine</div>
                    <div class="detail-value engine">
                        {formatEngine(details.engine)}
                    </div>
                    <div class="detail-description">
                        {#if !details.engine || details.engine === null}
                            Automatic selection based on model provider
                        {:else if details.engine === "native"}
                            Using provider's built-in web search
                        {:else if details.engine === "exa"}
                            Using Exa's AI-powered search API
                        {/if}
                    </div>
                </div>

                <div class="detail-item">
                    <div class="detail-label">Max Results</div>
                    <div class="detail-value">
                        {details.maxResults ?? 5}
                    </div>
                    <div class="detail-description">
                        Number of search results retrieved
                    </div>
                </div>

                {#if details.contextSize}
                    <div class="detail-item">
                        <div class="detail-label">Context Size</div>
                        <div class="detail-value">
                            {formatContextSize(details.contextSize)}
                        </div>
                        <div class="detail-description">
                            Amount of search context provided to the model
                        </div>
                    </div>
                {/if}

                {#if details.searchPrompt && details.searchPrompt.trim()}
                    <div class="detail-item full-width">
                        <div class="detail-label">Custom Search Prompt</div>
                        <div class="detail-value prompt">
                            {details.searchPrompt}
                        </div>
                        <div class="detail-description">
                            Instructions for how to incorporate search results
                        </div>
                    </div>
                {/if}
            </div>
        {/if}
    </ModelSettingsDialog>
{/if}

<style>
    .details-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 1.25rem;
        padding: 0.5rem 0;
    }

    .detail-item {
        background: rgba(9, 14, 26, 0.6);
        border: 1px solid rgba(67, 91, 136, 0.4);
        border-radius: 0.75rem;
        padding: 1rem 1.25rem;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
    }

    .detail-item.full-width {
        grid-column: 1 / -1;
    }

    .detail-label {
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94addb;
    }

    .detail-value {
        font-size: 1.1rem;
        font-weight: 600;
        color: #f3f5ff;
        line-height: 1.3;
    }

    .detail-value.engine {
        color: #7dd3fc;
    }

    .detail-value.prompt {
        font-size: 0.9rem;
        font-weight: 400;
        line-height: 1.5;
        padding: 0.75rem 0.85rem;
        background: rgba(15, 22, 38, 0.85);
        border-radius: 0.5rem;
        border: 1px solid rgba(67, 91, 136, 0.35);
        font-family: "Fira Code", "SFMono-Regular", Menlo, Monaco, Consolas,
            "Liberation Mono", "Courier New", monospace;
        white-space: pre-wrap;
        word-break: break-word;
    }

    .detail-description {
        font-size: 0.8rem;
        color: rgba(159, 179, 216, 0.75);
        line-height: 1.4;
    }

    @media (max-width: 640px) {
        .details-grid {
            grid-template-columns: 1fr;
        }
    }
</style>
