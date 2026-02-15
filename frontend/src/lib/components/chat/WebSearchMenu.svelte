<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import { webSearchStore } from "../../chat/webSearchStore";

  export let menuClass = "";

  const dispatch = createEventDispatcher<{ disable: void }>();

  function commitEngine(event: Event): void {
    const value = (event.currentTarget as HTMLSelectElement).value;
    webSearchStore.update({
      engine: value === "native" || value === "exa" ? value : null,
    });
  }

  function commitContext(event: Event): void {
    const value = (event.currentTarget as HTMLSelectElement).value;
    webSearchStore.update({
      contextSize:
        value === "low" || value === "medium" || value === "high"
          ? value
          : null,
    });
  }

  function commitMaxResults(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    if (input.value === "") {
      webSearchStore.update({ maxResults: null });
      return;
    }
    let value = Math.trunc(Number(input.value));
    if (!Number.isFinite(value)) return;
    if (value < 1) value = 1;
    if (value > 25) value = 25;
    webSearchStore.update({ maxResults: value });
  }

  function commitPrompt(event: Event): void {
    const value = (event.currentTarget as HTMLTextAreaElement).value;
    webSearchStore.update({ searchPrompt: value });
  }

  function handleDisable(): void {
    webSearchStore.setEnabled(false);
    dispatch("disable");
  }
</script>

<div class={`web-search-menu ${menuClass}`.trim()} role="dialog">
  <div class="web-search-fields">
    <label>
      <span>Engine</span>
      <select
        class="select-control"
        value={$webSearchStore.engine ?? ""}
        on:change={commitEngine}
      >
        <option value="">Auto</option>
        <option value="native">Native</option>
        <option value="exa">Exa</option>
      </select>
    </label>

    <label>
      <span>Context</span>
      <select
        class="select-control"
        value={$webSearchStore.contextSize ?? ""}
        on:change={commitContext}
      >
        <option value="">Default</option>
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
      </select>
    </label>

    <label>
      <span>Max results</span>
      <input
        class="input-control"
        type="number"
        min="1"
        max="25"
        step="1"
        value={$webSearchStore.maxResults ?? ""}
        on:change={commitMaxResults}
        on:blur={commitMaxResults}
        inputmode="numeric"
        pattern="\\d*"
      />
    </label>

    <label class="prompt">
      <span>Search prompt</span>
      <textarea
        class="textarea-control"
        rows="4"
        value={$webSearchStore.searchPrompt ?? ""}
        placeholder="Default: A web search was conducted on &#123;today's_date&#125;. Incorporate the following web search results into your response."
        on:input={commitPrompt}
      ></textarea>
    </label>
  </div>

  <button
    class="btn btn-ghost btn-small web-search-disable"
    type="button"
    on:click={handleDisable}
  >
    Disable Web Search
  </button>
</div>

<style>
  .web-search-menu {
    position: absolute;
    top: calc(100% + 0.35rem);
    left: 0;
    width: min(300px, 80vw);
    background: rgba(8, 14, 24, 0.97);
    border: 1px solid rgba(67, 91, 136, 0.6);
    border-radius: 0.75rem;
    padding: 1rem;
    box-shadow: 0 12px 24px rgba(3, 8, 20, 0.6);
    z-index: 100;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .web-search-fields {
    display: grid;
    gap: 0.65rem;
  }

  .web-search-fields label {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.75rem;
    color: #9fb3d8;
  }

  .web-search-fields label span {
    font-weight: 500;
  }

  .web-search-fields .select-control,
  .web-search-fields .input-control {
    padding: 0.4rem 0.6rem;
    border-radius: 0.4rem;
    background: rgba(9, 14, 26, 0.9);
    border: 1px solid rgba(37, 49, 77, 0.9);
    color: #f3f5ff;
    font: inherit;
    font-size: 0.8rem;
  }

  .web-search-fields .select-control:focus,
  .web-search-fields .input-control:focus,
  .web-search-fields .textarea-control:focus {
    outline: 2px solid #38bdf8;
    outline-offset: 1px;
    border-color: #38bdf8;
  }

  .web-search-fields .textarea-control {
    padding: 0.4rem 0.6rem;
    border-radius: 0.4rem;
    background: rgba(9, 14, 26, 0.9);
    border: 1px solid rgba(37, 49, 77, 0.9);
    color: #f3f5ff;
    font: inherit;
    font-size: 0.8rem;
    resize: vertical;
    min-height: 3rem;
  }

  .web-search-disable {
    margin-top: 0.25rem;
    justify-content: center;
    color: #ef4444;
    border-color: rgba(239, 68, 68, 0.4);
  }

  .web-search-disable:hover {
    color: #f87171;
    border-color: rgba(248, 113, 113, 0.6);
    background: rgba(239, 68, 68, 0.1);
  }

  .mobile-web-search-menu {
    top: calc(100% + 0.5rem);
    left: 0;
    right: auto;
    transform: translateX(-60%);
    z-index: 200;
  }
</style>
