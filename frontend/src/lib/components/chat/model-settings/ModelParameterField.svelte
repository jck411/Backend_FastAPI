<script lang="ts">
  import type { ModelHyperparameters } from '../../../api/types';
  import SliderField from './SliderField.svelte';
  import type { FieldConfig } from './fields';
  import { parameterNumberValue } from './fields';
  import type { ParameterHandlers } from './useModelSettings';
  import { numericInputValue } from './valueFormat';

  export let field: FieldConfig;
  export let parameters: ModelHyperparameters | null;
  export let handlers: ParameterHandlers;

  const isNumberField = (config: FieldConfig): config is Extract<FieldConfig, { type: 'number' | 'integer' }> =>
    config.type === 'number' || config.type === 'integer';

  let numericValue: number | undefined;
  let hasCustom = false;

  $: if (isNumberField(field)) {
    numericValue = parameterNumberValue(parameters, field.key);
  } else {
    numericValue = undefined;
  }

  $: hasCustom = parameters?.[field.key] != null;
</script>

<label class="setting">
  <div class="setting-header">
    <span class="setting-label">{field.label}</span>
    {#if field.description}
      <span class="setting-hint">{field.description}</span>
    {/if}
  </div>

  {#if isNumberField(field)}
    {#if field.min !== undefined && field.max !== undefined}
      <SliderField
        {field}
        {parameters}
        {numericValue}
        {hasCustom}
        {handlers}
      />
    {:else}
      <input
        class="input-control"
        type="number"
        inputmode={field.type === 'integer' ? 'numeric' : 'decimal'}
        step={field.step ?? (field.type === 'integer' ? 1 : 'any')}
        min={field.min ?? undefined}
        max={field.max ?? undefined}
        value={numericInputValue(parameters?.[field.key])}
        on:change={(event) => handlers.onNumberChange(field.key, event)}
        placeholder="Default"
      />
    {/if}
  {:else if field.type === 'boolean'}
    <div class="setting-boolean">
      <input
        id={`field-${field.key}`}
        type="checkbox"
        checked={parameters?.[field.key] === true}
        on:change={(event) => handlers.onBooleanChange(field.key, event)}
      />
      <span>Enabled</span>
    </div>
  {/if}
</label>
