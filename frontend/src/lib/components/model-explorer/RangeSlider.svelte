<script lang="ts">
  import { createEventDispatcher } from "svelte";

  type RangeValue = {
    min: number;
    max: number;
  };

  const dispatch = createEventDispatcher<{
    input: RangeValue;
    change: RangeValue;
  }>();

  export let id: string;
  export let min = 0;
  export let max = 100;
  export let step = 1;
  export let value: RangeValue = { min, max };
  export let disabled = false;
  export let ariaLabelMin = "Minimum value";
  export let ariaLabelMax = "Maximum value";

  const precision = 6;

  function clamp(input: number, lower: number, upper: number): number {
    if (!Number.isFinite(input)) return lower;
    if (input < lower) return lower;
    if (input > upper) return upper;
    return Number(input.toFixed(precision));
  }

  function toPercent(value: number, lower: number, upper: number): number {
    const span = upper - lower;
    if (!Number.isFinite(span) || span <= 0) return 0;
    return ((value - lower) / span) * 100;
  }

  $: lowerBound = Number.isFinite(min) ? min : 0;
  $: upperBound = Number.isFinite(max) ? max : lowerBound;
  $: lower = clamp(value?.min ?? lowerBound, lowerBound, upperBound);
  $: upper = clamp(value?.max ?? upperBound, lowerBound, upperBound);
  $: if (lower > upper) {
    lower = upper;
  }
  $: lowerPercent = toPercent(lower, lowerBound, upperBound);
  $: upperPercent = toPercent(upper, lowerBound, upperBound);

  function emit(nextMin: number, nextMax: number): void {
    const detail = { min: nextMin, max: nextMax } satisfies RangeValue;
    dispatch("input", detail);
    dispatch("change", detail);
  }

  function handleLower(event: Event): void {
    const target = event.target as HTMLInputElement;
    const next = clamp(Number(target.value), lowerBound, upper);
    if (next > upper) {
      emit(upper, upper);
      return;
    }
    emit(next, upper);
  }

  function handleUpper(event: Event): void {
    const target = event.target as HTMLInputElement;
    const next = clamp(Number(target.value), lower, upperBound);
    if (next < lower) {
      emit(lower, lower);
      return;
    }
    emit(lower, next);
  }
</script>

<div class="range-slider" data-disabled={disabled}>
  <div class="track"></div>
  <div
    class="range"
    style={`left: ${lowerPercent}%; right: ${100 - upperPercent}%;`}
    aria-hidden="true"
  ></div>
  <input
    id={id ? `${id}-min` : undefined}
    class="thumb thumb-min"
    type="range"
    min={lowerBound}
    max={upper}
    {step}
    value={lower}
    on:input={handleLower}
    aria-label={ariaLabelMin}
    {disabled}
  />
  <input
    id={id ? `${id}-max` : undefined}
    class="thumb thumb-max"
    type="range"
    min={lower}
    max={upperBound}
    {step}
    value={upper}
    on:input={handleUpper}
    aria-label={ariaLabelMax}
    {disabled}
  />
</div>

<style>
  .range-slider {
    position: relative;
    width: 100%;
    height: 2.25rem;
  }

  .range-slider[data-disabled="true"] {
    opacity: 0.5;
    pointer-events: none;
  }

  .track,
  .range {
    position: absolute;
    inset: 50% 0 auto;
    transform: translateY(-50%);
    height: 0.35rem;
    border-radius: 999px;
  }

  .track {
    background: rgba(56, 83, 132, 0.35);
  }

  .range {
    background: linear-gradient(90deg, #2563eb, #38bdf8);
  }

  input[type="range"] {
    position: absolute;
    inset: 0;
    margin: 0;
    width: 100%;
    height: 100%;
    background: none;
    pointer-events: none;
    appearance: none;
    -webkit-appearance: none;
  }

  input[type="range"]::-webkit-slider-runnable-track {
    height: 0;
  }

  input[type="range"]::-moz-range-track {
    height: 0;
    background: none;
  }

  input[type="range"]::-webkit-slider-thumb {
    pointer-events: auto;
    -webkit-appearance: none;
    height: 1rem;
    width: 1rem;
    border-radius: 50%;
    background: #f8fbff;
    border: 2px solid #2563eb;
    box-shadow: 0 2px 6px rgba(13, 20, 39, 0.45);
    transition:
      transform 0.2s ease,
      border-color 0.2s ease;
  }

  input[type="range"]::-moz-range-thumb {
    pointer-events: auto;
    height: 1rem;
    width: 1rem;
    border-radius: 50%;
    background: #f8fbff;
    border: 2px solid #2563eb;
    box-shadow: 0 2px 6px rgba(13, 20, 39, 0.45);
    transition:
      transform 0.2s ease,
      border-color 0.2s ease;
  }

  input[type="range"]:hover::-webkit-slider-thumb,
  input[type="range"]:focus-visible::-webkit-slider-thumb {
    transform: scale(1.05);
    border-color: #38bdf8;
  }

  input[type="range"]:hover::-moz-range-thumb,
  input[type="range"]:focus-visible::-moz-range-thumb {
    transform: scale(1.05);
    border-color: #38bdf8;
  }

  .thumb-min {
    z-index: 3;
  }

  .thumb-max {
    z-index: 4;
  }
</style>
