<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import FilterSection from "./FilterSection.svelte";

  type ToggleVariant = "default" | "columns" | "compact";

  export let title: string;
  export let options: string[] = [];
  export let selected: string[] = [];
  export let excluded: string[] = [];
  export let emptyMessage = "No options available.";
  export let variant: ToggleVariant = "default";

  const dispatch = createEventDispatcher<{ toggle: string }>();

  type PressedState = "true" | "false" | "mixed";
  type OptionRenderState = {
    value: string;
    state: ReturnType<typeof selectionState>;
    pressed: PressedState;
  };

  let optionStates: OptionRenderState[] = [];

  $: optionStates = options.map((option) => {
    const state = selectionState(option);
    const pressed: PressedState =
      state === "include" ? "true" : state === "exclude" ? "mixed" : "false";
    return { value: option, state, pressed };
  });

  function handleToggle(value: string) {
    dispatch("toggle", value);
  }

  function normalize(value: string): string {
    return value.trim().toLowerCase();
  }

  function matches(list: string[], value: string): boolean {
    if (list.length === 0) {
      return false;
    }
    const token = normalize(value);
    return token ? list.some((entry) => normalize(entry) === token) : false;
  }

  function selectionState(value: string): "include" | "exclude" | "neutral" {
    if (matches(selected, value)) {
      return "include";
    }
    if (matches(excluded, value)) {
      return "exclude";
    }
    return "neutral";
  }
</script>

<FilterSection {title} forceOpen={selected.length + excluded.length > 0}>
  <div class="options" data-variant={variant}>
    {#if options.length === 0}
      <p class="empty">{emptyMessage}</p>
    {:else}
      {#each optionStates as { value, state, pressed } (value)}
        <button
          type="button"
          class="pill"
          class:active={state === "include"}
          class:exclude={state === "exclude"}
          aria-pressed={pressed}
          data-state={state}
          on:click={() => handleToggle(value)}
        >
          <span class="label">{value}</span>
          <span class="indicator" aria-hidden="true"></span>
        </button>
      {/each}
    {/if}
  </div>
</FilterSection>

<style>
  .options {
    display: grid;
    gap: 0.5rem;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    align-items: start;
  }

  .options[data-variant="columns"] {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }

  .options[data-variant="compact"] {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .pill {
    border-radius: 0.5rem;
    border: 1px solid rgba(31, 42, 69, 0.65);
    background: rgba(14, 20, 33, 0.9);
    color: #d4daee;
    padding: 0.45rem 0.75rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    width: 100%;
    cursor: pointer;
    transition:
      border-color 0.2s ease,
      background 0.2s ease,
      color 0.2s ease,
      transform 0.2s ease;
    text-align: left;
  }

  .options[data-variant="compact"] .pill {
    width: auto;
    padding: 0.3rem 0.65rem;
    border-radius: 999px;
    gap: 0.5rem;
  }

  .pill .label {
    flex: 1;
    white-space: normal;
  }

  .indicator {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: #38bdf8;
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  .pill:hover {
    border-color: #38bdf8;
    color: #f2f7ff;
    transform: translateY(-1px);
  }

  .pill:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .pill:focus:not(:focus-visible) {
    outline: none;
  }

  .pill.active {
    background: rgba(35, 60, 104, 0.85);
    border-color: #38bdf8;
    color: #38bdf8;
  }

  .pill.active .indicator {
    opacity: 1;
  }

  .pill.exclude {
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(248, 113, 113, 0.75);
    color: #fca5a5;
  }

  .pill.exclude .indicator {
    opacity: 1;
    background: #f87171;
  }

  .pill.exclude:hover {
    border-color: #f87171;
    color: #fee2e2;
  }

  .options[data-variant="compact"] .indicator {
    display: none;
  }

  .options[data-variant="compact"] .pill.active {
    background: rgba(56, 189, 248, 0.15);
  }

  .options[data-variant="compact"] .pill.exclude {
    background: rgba(248, 113, 113, 0.2);
    border-color: rgba(248, 113, 113, 0.7);
    color: #fecaca;
  }

  .empty {
    margin: 0;
    color: #7f89a3;
    font-size: 0.9rem;
  }

  @media (max-width: 768px) {
    .options {
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }
  }

  @media (max-width: 480px) {
    .options {
      grid-template-columns: 1fr;
    }
  }
</style>
