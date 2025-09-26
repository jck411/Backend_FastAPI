<script lang="ts">
  import type { ModelRecord } from "../../api/types";
  import {
    deriveInputTokenPrice,
    deriveOutputTokenPrice,
    extractContextLength,
    extractInputModalities,
    extractOutputModalities,
    formatPrice,
  } from "../../models/utils";

  export let model: ModelRecord;
  export let onSelect: (model: ModelRecord) => void;

  const TOKENS_PER_MILLION = 1_000_000;

  $: modelLabel = model.name ?? model.id;
  $: inputTokenPrice = deriveInputTokenPrice(model);
  $: outputTokenPrice = deriveOutputTokenPrice(model);
  $: contextTokens = extractContextLength(model);
  $: contextDisplay = formatContextMillionsCompact(contextTokens);
  $: inputModalities = extractInputModalities(model).map((value) =>
    value.toLowerCase(),
  );
  $: outputModalities = extractOutputModalities(model).map((value) =>
    value.toLowerCase(),
  );

  function formatModality(value: string): string {
    if (!value) return value;
    return value
      .split(/[\s_/-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  function dedupeAndFormat(values: string[]): string[] {
    const seen = new Set<string>();
    const formatted: string[] = [];
    for (const value of values) {
      const label = formatModality(value.trim());
      if (!label) continue;
      const key = label.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      formatted.push(label);
    }
    return formatted;
  }

  function formatContextMillionsCompact(value: number | null): string {
    if (value === null) return "Unknown";
    const millions = value / TOKENS_PER_MILLION;
    const digits = millions >= 10 ? 0 : 1;
    const display = millions.toFixed(digits).replace(/\.0$/, "");
    return `${display}M tokens`;
  }

  function formatList(values: string[]): string | null {
    if (!values.length) return null;
    return values.join(", ");
  }

  function formatPriceWithUnit(
    value: number | null,
    unit: string,
  ): string | null {
    if (value === null) return null;
    const formatted = formatPrice(value);
    if (formatted === "FREE") {
      return "FREE";
    }
    return `${formatted} ${unit}`;
  }

  $: showInputTokenPrice = inputTokenPrice !== null;
  $: showOutputTokenPrice = outputTokenPrice !== null;
  $: inputLabels = dedupeAndFormat(inputModalities);
  $: outputLabels = dedupeAndFormat(outputModalities);
  $: providerLabel = (() => {
    const provider = model.provider;
    if (provider && typeof provider === "object") {
      if (provider.display_name) {
        return provider.display_name;
      }
      if (provider.slug) {
        return provider.slug;
      }
    }
    const idParts = model.id?.split("/") ?? [];
    if (idParts.length > 1) {
      return idParts[idParts.length - 2];
    }
    return null;
  })();

  type CardEntry = {
    key: string;
    label: string;
    value: string;
  };

  const UNIT_TOKENS = "/ 1M tokens";

  function buildPriceEntry(
    key: string,
    label: string,
    value: number | null,
    unit: string,
  ): CardEntry | null {
    const formatted = formatPriceWithUnit(value, unit);
    if (!formatted) return null;
    return { key, label, value: formatted };
  }

  function buildTextEntry(
    key: string,
    label: string,
    value: string | null,
  ): CardEntry | null {
    if (!value) return null;
    return { key, label, value };
  }

  $: detailEntries = [
    buildTextEntry("context", "Context", contextDisplay),
    buildTextEntry("provider", "Provider", providerLabel),
    buildTextEntry("input-modalities", "Input", formatList(inputLabels)),
    buildTextEntry("output-modalities", "Output", formatList(outputLabels)),
  ].filter((entry): entry is CardEntry => Boolean(entry));

  $: priceEntries = [
    showInputTokenPrice
      ? buildPriceEntry(
          "input-price",
          "Input price",
          inputTokenPrice,
          UNIT_TOKENS,
        )
      : null,
    showOutputTokenPrice
      ? buildPriceEntry(
          "output-price",
          "Output price",
          outputTokenPrice,
          UNIT_TOKENS,
        )
      : null,
  ].filter((entry): entry is CardEntry => Boolean(entry));

  $: cardEntries = [...detailEntries, ...priceEntries];

  function handleClick(): void {
    onSelect(model);
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(model);
    }
  }
</script>

<!-- svelte-ignore a11y-no-noninteractive-element-to-interactive-role -->
<article
  class="model-card"
  role="button"
  tabindex="0"
  aria-label={`Use model ${modelLabel}`}
  on:click={handleClick}
  on:keydown={handleKeydown}
>
  <header>
    <h4>{modelLabel}</h4>
  </header>

  <section class="info-section">
    <dl class="info-grid">
      {#each cardEntries as entry (entry.key)}
        <div class="info-item">
          <dt>{entry.label}</dt>
          <dd>{entry.value}</dd>
        </div>
      {/each}
    </dl>
  </section>
</article>

<style>
  .model-card {
    border: 1px solid #1f2c48;
    border-radius: 0.85rem;
    padding: 0.85rem;
    display: grid;
    gap: 0.75rem;
    background: #0c1324;
    height: 100%;
    cursor: pointer;
    transition:
      border-color 0.15s ease,
      box-shadow 0.15s ease,
      transform 0.15s ease;
  }

  .model-card:hover {
    border-color: rgba(56, 189, 248, 0.6);
    box-shadow: 0 4px 18px rgba(7, 12, 22, 0.45);
    transform: translateY(-1px);
  }

  .model-card:focus-visible {
    outline: 2px solid rgba(56, 189, 248, 0.9);
    outline-offset: 2px;
    border-color: rgba(56, 189, 248, 0.7);
    box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.18);
  }

  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.25rem;
  }

  h4 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .info-section {
    display: grid;
  }

  .info-grid {
    margin: 0;
    display: grid;
    gap: 0.5rem;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  }

  .info-item {
    display: grid;
    gap: 0.2rem;
    padding: 0.45rem 0.6rem;
    border-radius: 0.75rem;
    background: rgba(16, 23, 43, 0.85);
    border: 1px solid rgba(56, 83, 132, 0.35);
  }

  .info-item dt {
    margin: 0;
    font-size: 0.7rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #7d87a2;
  }

  .info-item dd {
    margin: 0;
    font-size: 0.9rem;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    line-height: 1.2;
    color: #e2e8f0;
    word-break: break-word;
  }
</style>
