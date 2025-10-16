<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher<{ select: { text: string } }>();

  interface Suggestion {
    label: string;
    text: string;
  }

  const defaultPrompts: Suggestion[] = [
    { label: 'Next.js advantages', text: 'What are the advantages of using Next.js?' },
    { label: 'Dijkstra code', text: "Write code to demonstrate Dijkstra's algorithm" },
    { label: 'Essay helper', text: 'Help me write an essay about Silicon Valley' },
    { label: 'Weather', text: 'What is the weather in Orlando?' },
  ];

  export let suggestions: Suggestion[] = defaultPrompts;

  function handleClick(text: string): void {
    dispatch('select', { text });
  }
</script>

<section class="suggestions">
  {#each suggestions as prompt (prompt.text)}
    <button type="button" on:click={() => handleClick(prompt.text)}>{prompt.label}</button>
  {/each}
</section>

<style>
  .suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    padding: 1.5rem 2rem;
    max-width: min(800px, 100%);
    margin: 0 auto;
    width: 100%;
    box-sizing: border-box;
  }
  .suggestions button {
    font-size: 0.85rem;
    padding: 0.625rem 1.25rem;
    border-radius: 999px;
    background: rgba(20, 30, 51, 0.4);
    border: 1px solid rgba(57, 76, 114, 0.6);
    color: inherit;
    cursor: pointer;
  }
  .suggestions button:hover,
  .suggestions button:focus {
    border-color: rgba(140, 180, 255, 0.6);
  }
  @media (max-width: 900px) {
    .suggestions {
      padding: 1.25rem 1.5rem;
      gap: 0.65rem;
    }
  }
  @media (max-width: 600px) {
    .suggestions {
      padding: 1rem 1rem;
      gap: 0.5rem;
    }
    .suggestions button {
      width: 100%;
      text-align: center;
    }
  }
  @media (max-width: 420px) {
    .suggestions {
      padding: 0.85rem 0.75rem;
      gap: 0.45rem;
    }
  }
</style>
