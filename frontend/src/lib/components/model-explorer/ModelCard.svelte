<script lang="ts">
  import type { ModelRecord } from '../../api/types';
  import { derivePromptPrice, extractContextLength, formatContext, formatPrice } from '../../models/utils';

  export let model: ModelRecord;
  export let onSelect: (model: ModelRecord) => void;
</script>

<article class="model-card">
  <header>
    <h4>{model.name ?? model.id}</h4>
    <p class="model-id">{model.id}</p>
  </header>
  {#if model.description}
    <p class="description">{model.description}</p>
  {/if}
  <dl class="metadata">
    <div>
      <dt>Context length</dt>
      <dd>{formatContext(extractContextLength(model))}</dd>
    </div>
    <div>
      <dt>Prompt pricing (1M tokens)</dt>
      <dd>{formatPrice(derivePromptPrice(model))}</dd>
    </div>
    {#if model.provider?.display_name}
      <div>
        <dt>Provider</dt>
        <dd>{model.provider.display_name}</dd>
      </div>
    {/if}
  </dl>
  <footer>
    <button type="button" class="primary" on:click={() => onSelect(model)}>Use this model</button>
  </footer>
</article>

<style>
  .model-card {
    border: 1px solid #1f2c48;
    border-radius: 1rem;
    padding: 1rem;
    display: grid;
    gap: 0.75rem;
    background: #0c1324;
    height: 100%;
  }

  header {
    display: grid;
    gap: 0.2rem;
  }

  h4 {
    margin: 0;
    font-size: 1.1rem;
  }

  .model-id {
    margin: 0;
    color: #69738d;
    font-size: 0.85rem;
  }

  .description {
    margin: 0;
    color: #9aa2ba;
    font-size: 0.9rem;
  }

  .metadata {
    margin: 0;
    display: grid;
    gap: 0.5rem;
  }

  .metadata div {
    display: flex;
    justify-content: space-between;
    font-size: 0.9rem;
  }

  .metadata dt {
    color: #7d87a2;
  }

  .metadata dd {
    margin: 0;
  }

  .primary {
    border-radius: 999px;
    border: none;
    background: #38bdf8;
    color: #041225;
    padding: 0.5rem 1.2rem;
    font-weight: 600;
    cursor: pointer;
  }
</style>
