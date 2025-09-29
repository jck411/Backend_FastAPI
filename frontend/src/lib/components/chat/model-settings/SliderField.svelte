<script lang="ts">
  import type { ModelHyperparameters } from '../../../api/types';
  import type { NumberFieldConfig } from './fields';
  import { sliderCurrentValue, sliderFillPercent, sliderStepValue } from './fields';
  import type { ParameterHandlers } from './useModelSettings';
  import { formatParameterNumber } from './valueFormat';

  export let field: NumberFieldConfig;
  export let parameters: ModelHyperparameters | null;
  export let numericValue: number | undefined;
  export let hasCustom = false;
  export let handlers: ParameterHandlers;

  $: sliderValue = sliderCurrentValue(field, parameters);
  $: sliderFill = sliderFillPercent(field, numericValue);
  $: displayValue =
    numericValue !== undefined ? formatParameterNumber(numericValue, field) : 'Provider default';
  $: minValue = field.min ?? sliderValue;
  $: maxValue = field.max ?? sliderValue;
</script>

<div class="setting-range">
  <div class="setting-range-header">
    <span class="range-value" class:default={!hasCustom}>{displayValue}</span>
    <button
      type="button"
      class="range-reset"
      on:click={() => handlers.onRangeReset(field.key)}
      disabled={!hasCustom}
    >
      Use default
    </button>
  </div>
  <input
    class="range-input"
    type="range"
    min={field.min}
    max={field.max}
    step={sliderStepValue(field)}
    value={sliderValue}
    style={`--slider-fill:${sliderFill};`}
    on:input={(event) => handlers.onSliderInput(field.key, event)}
    aria-valuemin={field.min}
    aria-valuemax={field.max}
    aria-valuenow={numericValue ?? undefined}
    aria-valuetext={displayValue}
  />
  <div class="range-extents">
    <span>{formatParameterNumber(minValue, field)}</span>
    <span>{formatParameterNumber(maxValue, field)}</span>
  </div>
</div>
