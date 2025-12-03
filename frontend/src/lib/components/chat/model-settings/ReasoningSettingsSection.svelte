<script lang="ts">
  import type { ReasoningHandlers, ReasoningState } from './useModelSettings';
  import { numericInputValue } from './valueFormat';

  export let reasoning: ReasoningState;
  export let handlers: ReasoningHandlers;
</script>

<section class="setting reasoning">
  <div class="setting-header">
    <span class="setting-label">Reasoning tokens</span>
    <span class="setting-hint">
      Adjust effort, budget, or output visibility when the provider supports reasoning traces.
    </span>
  </div>
  <div class="reasoning-controls">
    <label class="reasoning-field">
      <span>Enabled behavior</span>
      <select class="select-control" value={reasoning.enabledSelection} on:change={handlers.onEnabledChange}>
        <option value="default">Use provider default</option>
        <option value="on">Force enabled</option>
        <option value="off">Disable reasoning</option>
      </select>
    </label>
    {#if reasoning.effort.showField}
      <label class="reasoning-field" aria-disabled={!reasoning.effort.supported}>
        <span>Effort</span>
        <select
          class="select-control"
          value={reasoning.effort.supported ? reasoning.effort.value ?? '' : ''}
          disabled={!reasoning.effort.supported}
          on:change={handlers.onEffortChange}
        >
          <option value="">Provider default</option>
          {#each reasoning.options as option}
            <option value={option}>{option.charAt(0).toUpperCase() + option.slice(1)}</option>
          {/each}
        </select>
      </label>
    {/if}
    {#if reasoning.maxTokens.showField}
      <label class="reasoning-field" aria-disabled={!reasoning.maxTokens.supported}>
        <span>Max reasoning tokens</span>
        <input
          class="input-control"
          type="number"
          inputmode="numeric"
          min={reasoning.schemas.maxTokens?.min ?? undefined}
          max={reasoning.schemas.maxTokens?.max ?? undefined}
          step={reasoning.schemas.maxTokens?.step ?? 1}
          placeholder="Default"
          disabled={!reasoning.maxTokens.supported}
          value={numericInputValue(reasoning.maxTokens.value)}
          on:change={handlers.onMaxTokensChange}
        />
      </label>
    {/if}
    <label class="reasoning-toggle">
      <input type="checkbox" checked={reasoning.exclude} on:change={handlers.onExcludeChange} />
      <span>Exclude reasoning from responses</span>
    </label>
  </div>
</section>
