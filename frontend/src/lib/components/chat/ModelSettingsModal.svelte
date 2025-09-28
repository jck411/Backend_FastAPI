<script lang="ts">
  import { afterUpdate, createEventDispatcher } from 'svelte';
  import type {
    ModelRecord,
    ModelHyperparameters,
    ReasoningConfig,
    ReasoningEffort,
  } from '../../api/types';
  import { extractSupportedParameters } from '../../models/utils';
  import { modelSettingsStore } from '../../stores/modelSettings';

  interface NumberFieldConfig {
    key: keyof ModelHyperparameters;
    label: string;
    description?: string;
    type: 'number' | 'integer';
    min?: number;
    max?: number;
    step?: number;
  }

  interface BooleanFieldConfig {
    key: keyof ModelHyperparameters;
    label: string;
    description?: string;
    type: 'boolean';
  }

  type FieldConfig = NumberFieldConfig | BooleanFieldConfig;

  type FieldFallback =
    | {
        type: 'number' | 'integer';
        min?: number;
        max?: number;
        step?: number;
      }
    | {
        type: 'boolean';
      };

  interface ParameterDefinition {
    key: keyof ModelHyperparameters;
    aliases: string[];
    label: string;
    description?: string;
    fallback: FieldFallback;
  }

  interface ParameterSchema {
    type?: string;
    min?: number;
    max?: number;
    step?: number;
  }

  export let open = false;
  export let selectedModel = '';
  export let model: ModelRecord | null = null;

  const dispatch = createEventDispatcher<{ close: void }>();

  let dialogEl: HTMLElement | null = null;
  let lastLoadedModel: string | null = null;

  const PARAMETER_DEFINITIONS: ParameterDefinition[] = [
    {
      key: 'temperature',
      aliases: ['temperature'],
      label: 'Temperature',
      description: 'Higher values increase randomness.',
      fallback: { type: 'number', min: 0, max: 2, step: 0.1 },
    },
    {
      key: 'top_p',
      aliases: ['top_p'],
      label: 'Top P',
      description: 'Limits sampling to a cumulative probability mass.',
      fallback: { type: 'number', min: 0, max: 1, step: 0.01 },
    },
    {
      key: 'top_k',
      aliases: ['top_k'],
      label: 'Top K',
      description: 'Restrict sampling to the top K tokens.',
      fallback: { type: 'integer', min: 1, max: 400, step: 1 },
    },
    {
      key: 'min_p',
      aliases: ['min_p'],
      label: 'Min P',
      description: 'Nucleus sampling floor; smaller values widen sampling.',
      fallback: { type: 'number', min: 0, max: 1, step: 0.01 },
    },
    {
      key: 'top_a',
      aliases: ['top_a'],
      label: 'Top A',
      description: 'Alternative nucleus control for certain models.',
      fallback: { type: 'number', min: 0, max: 1, step: 0.01 },
    },
    {
      key: 'max_tokens',
      aliases: ['max_tokens', 'max_output_tokens'],
      label: 'Max completion tokens',
      description: 'Upper bound on tokens generated in the response.',
      fallback: { type: 'integer', min: 1, max: 32768, step: 1 },
    },
    {
      key: 'frequency_penalty',
      aliases: ['frequency_penalty'],
      label: 'Frequency penalty',
      description: 'Penalize frequent tokens; useful to reduce repetition.',
      fallback: { type: 'number', min: -2, max: 2, step: 0.05 },
    },
    {
      key: 'presence_penalty',
      aliases: ['presence_penalty'],
      label: 'Presence penalty',
      description: 'Encourage introducing new topics by penalizing seen tokens.',
      fallback: { type: 'number', min: -2, max: 2, step: 0.05 },
    },
    {
      key: 'repetition_penalty',
      aliases: ['repetition_penalty'],
      label: 'Repetition penalty',
      description: 'Higher values push the model away from repeating itself.',
      fallback: { type: 'number', min: 0, max: 2, step: 0.05 },
    },
    {
      key: 'top_logprobs',
      aliases: ['top_logprobs'],
      label: 'Top logprobs',
      description: 'Return log probabilities for the top N tokens per step.',
      fallback: { type: 'integer', min: 0, max: 20, step: 1 },
    },
    {
      key: 'seed',
      aliases: ['seed'],
      label: 'Seed',
      description: 'Deterministic seed (when supported).',
      fallback: { type: 'integer', min: 0, step: 1 },
    },
    {
      key: 'parallel_tool_calls',
      aliases: ['parallel_tool_calls'],
      label: 'Parallel tool calls',
      description: 'Allow the model to invoke multiple tools simultaneously.',
      fallback: { type: 'boolean' },
    },
    {
      key: 'structured_outputs',
      aliases: ['structured_outputs', 'json_schema', 'response_format'],
      label: 'Structured outputs',
      description: 'Favor structured responses when supported by the provider.',
      fallback: { type: 'boolean' },
    },
    {
      key: 'safe_prompt',
      aliases: ['safe_prompt'],
      label: 'Safe prompt',
      description: 'Ask the provider to apply additional safety prompting.',
      fallback: { type: 'boolean' },
    },
    {
      key: 'raw_mode',
      aliases: ['raw_mode'],
      label: 'Raw mode',
      description: 'Bypass guardrails when the provider allows it.',
      fallback: { type: 'boolean' },
    },
  ];

  const normalizeToken = (value: unknown): string | null => {
    if (typeof value !== 'string') return null;
    const token = value.trim().toLowerCase();
    if (!token) return null;
    return token.replace(/[^a-z0-9_\-]/g, '_');
  };

  const REASONING_TOKENS = [
    'reasoning',
    'reasoning_effort',
    'reasoning_max_tokens',
    'reasoning_exclude',
    'reasoning_enabled',
    'include_reasoning',
  ];

  const REASONING_SCHEMA_KEYS = {
    effort: ['reasoning.effort', 'reasoning_effort'],
    maxTokens: ['reasoning.max_tokens', 'reasoning_max_tokens', 'thinking_budget'],
    exclude: ['reasoning.exclude', 'reasoning_exclude', 'include_reasoning'],
    enabled: ['reasoning.enabled', 'reasoning_enabled'],
  } as const;

  function coerceNumber(value: unknown): number | undefined {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    if (typeof value === 'string' && value.trim()) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
    return undefined;
  }

  function extractSchemas(modelRecord: ModelRecord | null): Record<string, ParameterSchema> {
    const result: Record<string, ParameterSchema> = {};
    if (!modelRecord || !modelRecord.capabilities) {
      return result;
    }
    const capabilities = modelRecord.capabilities as Record<string, unknown>;
    const rawParameters = capabilities.parameters;
    if (!rawParameters || typeof rawParameters !== 'object') {
      return result;
    }

    function assignSchema(rawKey: string, schemaValue: unknown): void {
      const normalizedKey = normalizeToken(rawKey);
      if (!normalizedKey) return;
      if (!schemaValue || typeof schemaValue !== 'object') {
        return;
      }
      const record = schemaValue as Record<string, unknown>;
      const schema: ParameterSchema = {};
      const rawType = record.type ?? record.datatype ?? record.kind;
      if (typeof rawType === 'string') {
        schema.type = rawType.toLowerCase();
      }
      const min = record.min ?? record.minimum ?? record.lower_bound ?? record.minimum_value;
      const max = record.max ?? record.maximum ?? record.upper_bound ?? record.maximum_value;
      const step = record.step ?? record.increment ?? record.resolution;
      const minNumber = coerceNumber(min);
      const maxNumber = coerceNumber(max);
      const stepNumber = coerceNumber(step);
      if (minNumber !== undefined) schema.min = minNumber;
      if (maxNumber !== undefined) schema.max = maxNumber;
      if (stepNumber !== undefined) schema.step = stepNumber;
      result[normalizedKey] = schema;

      const properties = record.properties;
      if (properties && typeof properties === 'object') {
        for (const [propertyKey, propertySchema] of Object.entries(properties as Record<string, unknown>)) {
          assignSchema(`${rawKey}.${propertyKey}`, propertySchema);
        }
      }
    }

    for (const [key, value] of Object.entries(rawParameters as Record<string, unknown>)) {
      assignSchema(key, value);
    }

    return result;
  }

  function supportedTokens(modelRecord: ModelRecord | null): Set<string> {
    const tokens = new Set<string>();
    if (!modelRecord) {
      return tokens;
    }
    const normalized = (modelRecord as Record<string, unknown>).supported_parameters_normalized;
    if (Array.isArray(normalized)) {
      for (const entry of normalized) {
        const token = normalizeToken(entry);
        if (token) tokens.add(token);
      }
    }
    const raw = (modelRecord as Record<string, unknown>).supported_parameters;
    if (Array.isArray(raw)) {
      for (const entry of raw) {
        const token = normalizeToken(entry);
        if (token) tokens.add(token);
      }
    }
    if (tokens.size === 0) {
      for (const entry of extractSupportedParameters(modelRecord)) {
        const token = normalizeToken(entry);
        if (token) tokens.add(token);
      }
    }
    return tokens;
  }

  function applySchema(definition: ParameterDefinition, schema: ParameterSchema | undefined): FieldConfig {
    const fallback = definition.fallback;

    if (fallback.type === 'boolean') {
      return {
        key: definition.key,
        label: definition.label,
        description: definition.description,
        type: 'boolean',
      };
    }

    const field: NumberFieldConfig = {
      key: definition.key,
      label: definition.label,
      description: definition.description,
      type: fallback.type,
      min: fallback.min,
      max: fallback.max,
      step: fallback.step,
    };

    if (!schema) {
      if (field.type === 'integer' && (!field.step || field.step <= 0)) {
        field.step = 1;
      }
      return field;
    }

    const schemaType = schema.type?.toLowerCase();
    if (schemaType === 'boolean') {
      return {
        key: definition.key,
        label: definition.label,
        description: definition.description,
        type: 'boolean',
      };
    }

    if (schemaType === 'integer' || schemaType === 'int') {
      field.type = 'integer';
    } else if (schemaType === 'number' || schemaType === 'float' || schemaType === 'double') {
      field.type = 'number';
    }

    if (schema.min !== undefined) field.min = schema.min;
    if (schema.max !== undefined) field.max = schema.max;
    if (schema.step !== undefined) field.step = schema.step;

    if (field.type === 'integer' && (!field.step || field.step <= 0)) {
      field.step = 1;
    }

    return field;
  }

  function buildFields(
    modelRecord: ModelRecord | null,
    parameters: ModelHyperparameters | null,
  ): FieldConfig[] {
    const available = supportedTokens(modelRecord);
    const activeKeys = new Set(
      parameters ? (Object.keys(parameters) as Array<keyof ModelHyperparameters>) : [],
    );
    const schemas = extractSchemas(modelRecord);
    const fields: FieldConfig[] = [];
    const seen = new Set<keyof ModelHyperparameters>();

    for (const definition of PARAMETER_DEFINITIONS) {
      const matches = definition.aliases.some((alias) => available.has(alias));
      if (!matches && !activeKeys.has(definition.key)) {
        continue;
      }
      if (seen.has(definition.key)) {
        continue;
      }
      const schema = definition.aliases
        .map((alias) => schemas[alias])
        .find((entry) => entry !== undefined);
      const field = applySchema(definition, schema);
      if ('min' in field && 'max' in field && field.min !== undefined && field.max !== undefined) {
        if (field.min >= field.max) {
          field.min = undefined;
          field.max = undefined;
        }
      }
      fields.push(field);
      seen.add(definition.key);
    }

    return fields;
  }

  $: settingsState = $modelSettingsStore;
  $: parameters = settingsState.data?.parameters ?? null;
  $: fields = buildFields(model, parameters);
  $: hasCustomParameters = Boolean(parameters && Object.keys(parameters).length > 0);
  $: capabilitySchemas = extractSchemas(model);
  $: availableTokens = supportedTokens(model);

  function lookupSchema(keys: readonly string[]): ParameterSchema | undefined {
    for (const key of keys) {
      const normalized = normalizeToken(key);
      if (!normalized) continue;
      const schema = capabilitySchemas[normalized];
      if (schema) return schema;
    }
    return undefined;
  }

  $: reasoningSchemas = {
    effort: lookupSchema(REASONING_SCHEMA_KEYS.effort),
    maxTokens: lookupSchema(REASONING_SCHEMA_KEYS.maxTokens),
    exclude: lookupSchema(REASONING_SCHEMA_KEYS.exclude),
    enabled: lookupSchema(REASONING_SCHEMA_KEYS.enabled),
  };

  $: reasoningSupported = (() => {
    if (parameters?.reasoning && Object.keys(parameters.reasoning).length > 0) {
      return true;
    }
    for (const alias of REASONING_TOKENS) {
      if (availableTokens.has(alias)) {
        return true;
      }
    }
    for (const schema of Object.values(reasoningSchemas)) {
      if (schema) {
        return true;
      }
    }
    return false;
  })();

  $: reasoningConfig = (parameters?.reasoning as ReasoningConfig | null) ?? null;
  $: reasoningEffortValue = (reasoningConfig?.effort as ReasoningEffort | null) ?? null;
  $: reasoningMaxTokens = reasoningConfig?.max_tokens ?? null;
  $: reasoningExclude = reasoningConfig?.exclude === true;
  $: reasoningEnabledSelection = (() => {
    if (!reasoningConfig) return 'default';
    if (reasoningConfig.enabled === true) return 'on';
    if (reasoningConfig.enabled === false) return 'off';
    return 'default';
  })();

  $: reasoningEffortOptions = ['low', 'medium', 'high'] as ReasoningEffort[];
  $: reasoningEffortHint = Boolean(reasoningSchemas.effort || availableTokens.has('reasoning_effort'));
  $: reasoningMaxTokensHint = Boolean(reasoningSchemas.maxTokens || availableTokens.has('reasoning_max_tokens'));
  $: reasoningEffortSupported = reasoningSupported && (reasoningEffortHint || !reasoningMaxTokensHint);
  $: reasoningMaxTokensSupported = reasoningSupported && (reasoningMaxTokensHint || !reasoningEffortHint);

  function updateReasoning(mutator: (draft: ReasoningConfig) => void): void {
    const current = (reasoningConfig ? { ...reasoningConfig } : {}) as ReasoningConfig;
    mutator(current);
    for (const key of Object.keys(current) as Array<keyof ReasoningConfig>) {
      const value = current[key];
      const remove =
        value === undefined ||
        value === null ||
        (typeof value === 'string' && value.trim() === '');
      if (remove) {
        delete current[key];
      }
    }
    if (Object.keys(current).length === 0) {
      modelSettingsStore.updateParameter('reasoning', null);
    } else {
      modelSettingsStore.updateParameter('reasoning', current);
    }
  }

  $: if (open && selectedModel) {
    if (settingsState.data && settingsState.data.model !== selectedModel) {
      modelSettingsStore.setModel(selectedModel);
    }
    if (lastLoadedModel !== selectedModel) {
      lastLoadedModel = selectedModel;
      modelSettingsStore.clearErrors();
      void modelSettingsStore.load(selectedModel);
    }
  }

  afterUpdate(() => {
    if (open && dialogEl) {
      dialogEl.focus();
    }
  });

  function closeModal(): void {
    void modelSettingsStore.flushSave().finally(() => dispatch('close'));
  }

  function handleBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) {
      closeModal();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeModal();
    }
  }

  function numericInputValue(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) ? String(value) : '';
  }

  function handleNumberChange(
    key: keyof ModelHyperparameters,
    event: Event,
  ): void {
    const target = event.currentTarget as HTMLInputElement | null;
    if (!target) return;
    const raw = target.value.trim();
    if (!raw) {
      modelSettingsStore.updateParameter(key, null);
      return;
    }
    const numeric = Number(raw);
    if (!Number.isFinite(numeric)) {
      modelSettingsStore.updateParameter(key, null);
      return;
    }
    modelSettingsStore.updateParameter(key, numeric);
  }

  function handleBooleanChange(
    key: keyof ModelHyperparameters,
    event: Event,
  ): void {
    const target = event.currentTarget as HTMLInputElement | null;
    if (!target) return;
    modelSettingsStore.updateParameter(key, target.checked);
  }

  function handleReasoningEffortChange(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement | null;
    if (!target) return;
    const value = target.value;
    updateReasoning((draft) => {
      if (!value) {
        delete draft.effort;
      } else {
        draft.effort = value as ReasoningEffort;
      }
    });
  }

  function handleReasoningMaxTokensChange(event: Event): void {
    const target = event.currentTarget as HTMLInputElement | null;
    if (!target) return;
    const raw = target.value.trim();
    if (!raw) {
      updateReasoning((draft) => {
        delete draft.max_tokens;
      });
      return;
    }
    const numeric = Number(raw);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      updateReasoning((draft) => {
        delete draft.max_tokens;
      });
      return;
    }
    updateReasoning((draft) => {
      draft.max_tokens = numeric;
    });
  }

  function handleReasoningExcludeChange(event: Event): void {
    const target = event.currentTarget as HTMLInputElement | null;
    if (!target) return;
    const checked = target.checked;
    updateReasoning((draft) => {
      if (checked) {
        draft.exclude = true;
      } else {
        delete draft.exclude;
      }
    });
  }

  function handleReasoningEnabledChange(event: Event): void {
    const target = event.currentTarget as HTMLSelectElement | null;
    if (!target) return;
    const value = target.value;
    updateReasoning((draft) => {
      if (value === 'on') {
        draft.enabled = true;
      } else if (value === 'off') {
        draft.enabled = false;
      } else {
        delete draft.enabled;
      }
    });
  }
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class="model-settings-layer">
    <button
      type="button"
      class="model-settings-backdrop"
      aria-label="Close model settings"
      on:click={handleBackdrop}
    ></button>
    <div
      class="model-settings-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="model-settings-title"
      tabindex="-1"
      bind:this={dialogEl}
    >
      <header class="model-settings-header">
        <div class="model-settings-heading">
          <h2 id="model-settings-title">Model settings</h2>
          <p class="model-settings-subtitle">
            {#if model?.name}
              {model.name}
            {:else if model?.id}
              {model.id}
            {:else}
              {selectedModel}
            {/if}
          </p>
        </div>
        <div class="model-settings-actions">
          <button
            type="button"
            class="ghost small"
            on:click={() => modelSettingsStore.resetToDefaults()}
            disabled={!hasCustomParameters || settingsState.saving}
          >
            Reset to defaults
          </button>
          <button type="button" class="modal-close" on:click={closeModal} aria-label="Close">
            Close
          </button>
        </div>
      </header>
      <section class="model-settings-body">
        {#if settingsState.loading}
          <p class="status">Loading settings…</p>
        {:else if settingsState.error}
          <p class="status error">{settingsState.error}</p>
        {:else}
          {#if !reasoningSupported && !fields.length}
            <p class="status">This model does not expose configurable parameters.</p>
          {:else}
            <div class="settings-stack" aria-live="polite">
              {#if reasoningSupported}
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
                      <select value={reasoningEnabledSelection} on:change={handleReasoningEnabledChange}>
                        <option value="default">Use provider default</option>
                        <option value="on">Force enabled</option>
                        <option value="off">Disable reasoning</option>
                      </select>
                    </label>
                    <label class="reasoning-field" aria-disabled={!reasoningEffortSupported}>
                      <span>Effort</span>
                      <select
                        value={reasoningEffortSupported ? reasoningEffortValue ?? '' : ''}
                        disabled={!reasoningEffortSupported}
                        on:change={handleReasoningEffortChange}
                      >
                        <option value="">Provider default</option>
                        {#each reasoningEffortOptions as option}
                          <option value={option}>
                            {option.charAt(0).toUpperCase() + option.slice(1)}
                          </option>
                        {/each}
                      </select>
                    </label>
                    <label class="reasoning-field" aria-disabled={!reasoningMaxTokensSupported}>
                      <span>Max reasoning tokens</span>
                      <input
                        type="number"
                        inputmode="numeric"
                        min={reasoningSchemas.maxTokens?.min ?? undefined}
                        max={reasoningSchemas.maxTokens?.max ?? undefined}
                        step={reasoningSchemas.maxTokens?.step ?? 1}
                        placeholder="Default"
                        disabled={!reasoningMaxTokensSupported}
                        value={numericInputValue(reasoningMaxTokens)}
                        on:change={handleReasoningMaxTokensChange}
                      />
                    </label>
                    <label class="reasoning-toggle">
                      <input
                        type="checkbox"
                        checked={reasoningExclude}
                        on:change={handleReasoningExcludeChange}
                      />
                      <span>Exclude reasoning from responses</span>
                    </label>
                  </div>
                </section>
              {/if}

              {#if fields.length}
                <form class="settings-grid">
                  {#each fields as field (field.key)}
                    <label class="setting">
                      <div class="setting-header">
                        <span class="setting-label">{field.label}</span>
                        {#if field.description}
                          <span class="setting-hint">{field.description}</span>
                        {/if}
                      </div>
                      {#if field.type === 'number' || field.type === 'integer'}
                        <input
                          type="number"
                          inputmode="decimal"
                          step={field.step ?? (field.type === 'integer' ? 1 : 'any')}
                          min={field.min ?? undefined}
                          max={field.max ?? undefined}
                          value={numericInputValue(parameters?.[field.key])}
                          on:change={(event) => handleNumberChange(field.key, event)}
                          placeholder="Default"
                        />
                      {:else if field.type === 'boolean'}
                        <div class="setting-boolean">
                          <input
                            id={`field-${field.key}`}
                            type="checkbox"
                            checked={parameters?.[field.key] === true}
                            on:change={(event) => handleBooleanChange(field.key, event)}
                          />
                          <span>Enabled</span>
                        </div>
                      {/if}
                    </label>
                  {/each}
                </form>
              {/if}
            </div>
          {/if}
        {/if}
      </section>
      <footer class="model-settings-footer">
        {#if settingsState.saveError}
          <span class="status error">{settingsState.saveError}</span>
        {:else if settingsState.saving}
          <span class="status">Saving…</span>
        {:else if settingsState.dirty}
          <span class="status">Pending changes…</span>
        {:else}
          <span class="status">Changes are saved automatically.</span>
        {/if}
      </footer>
    </div>
  </div>
{/if}

<style>
  .model-settings-layer {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    z-index: 140;
  }
  .model-settings-backdrop {
    position: absolute;
    inset: 0;
    background: rgba(4, 8, 20, 0.65);
    border: none;
    padding: 0;
    margin: 0;
    cursor: pointer;
  }
  .model-settings-backdrop:focus-visible {
    outline: 2px solid #38bdf8;
  }
  .model-settings-modal {
    position: relative;
    width: min(640px, 100%);
    max-height: min(80vh, 720px);
    background: rgba(10, 16, 28, 0.95);
    border: 1px solid rgba(67, 91, 136, 0.6);
    border-radius: 1rem;
    box-shadow: 0 18px 48px rgba(3, 8, 20, 0.55);
    backdrop-filter: blur(12px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 1;
  }
  .model-settings-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 1.25rem 1.5rem 1rem;
    border-bottom: 1px solid rgba(67, 91, 136, 0.45);
  }
  .model-settings-heading h2 {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }
  .model-settings-subtitle {
    margin: 0.35rem 0 0;
    font-size: 0.8rem;
    color: #8ea7d2;
  }
  .model-settings-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .model-settings-body {
    padding: 1.25rem 1.5rem 1.5rem;
    overflow-y: auto;
  }
  .status {
    margin: 0;
    font-size: 0.85rem;
    color: #9fb3d8;
  }
  .status.error {
    color: #fca5a5;
  }
  .settings-grid {
    display: grid;
    gap: 1rem;
  }
  .settings-stack {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }
  .setting {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.75rem;
    border: 1px solid rgba(67, 91, 136, 0.4);
    border-radius: 0.75rem;
    background: rgba(12, 18, 30, 0.9);
  }
  .setting-header {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .setting-label {
    font-weight: 600;
  }
  .setting-hint {
    font-size: 0.75rem;
    color: #8094bb;
  }
  .setting input[type='number'] {
    width: 100%;
    border-radius: 0.5rem;
    border: 1px solid rgba(82, 108, 158, 0.6);
    background: rgba(14, 20, 32, 0.95);
    color: #f2f4f8;
    padding: 0.4rem 0.6rem;
    font: inherit;
  }
  .setting input[type='number']:focus-visible {
    outline: 2px solid #38bdf8;
    border-color: #38bdf8;
  }
  .reasoning {
    gap: 0.75rem;
  }
  .reasoning-controls {
    display: grid;
    gap: 0.75rem;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }
  .reasoning-field {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }
  .reasoning-field select,
  .reasoning-field input[type='number'] {
    width: 100%;
    border-radius: 0.5rem;
    border: 1px solid rgba(82, 108, 158, 0.6);
    background: rgba(14, 20, 32, 0.95);
    color: #f2f4f8;
    padding: 0.4rem 0.6rem;
    font: inherit;
  }
  .reasoning-field select:focus-visible,
  .reasoning-field input[type='number']:focus-visible {
    outline: 2px solid #38bdf8;
    border-color: #38bdf8;
  }
  .reasoning-field select:disabled,
  .reasoning-field input[type='number']:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .reasoning-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }
  .reasoning-toggle input {
    width: 1.1rem;
    height: 1.1rem;
  }
  .setting-boolean {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
  }
  .setting-boolean input {
    width: 1.1rem;
    height: 1.1rem;
  }
  .model-settings-footer {
    padding: 0.85rem 1.5rem;
    border-top: 1px solid rgba(67, 91, 136, 0.45);
    background: rgba(9, 14, 26, 0.95);
  }
  .ghost {
    background: none;
    border: 1px solid rgba(71, 99, 150, 0.6);
    border-radius: 999px;
    color: #f3f5ff;
    padding: 0.35rem 0.9rem;
    cursor: pointer;
    font-size: 0.75rem;
    transition: border-color 0.2s ease, color 0.2s ease;
  }
  .ghost:hover,
  .ghost:focus-visible {
    border-color: #38bdf8;
    color: #38bdf8;
    outline: none;
  }
  .ghost:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .modal-close {
    background: none;
    border: 1px solid rgba(71, 99, 150, 0.6);
    border-radius: 999px;
    color: #f3f5ff;
    padding: 0.35rem 0.9rem;
    cursor: pointer;
    font-size: 0.75rem;
  }
  .modal-close:hover,
  .modal-close:focus-visible {
    border-color: #38bdf8;
    color: #38bdf8;
    outline: none;
  }
  @media (max-width: 640px) {
    .model-settings-layer {
      padding: 1.5rem;
    }
    .model-settings-modal {
      width: 100%;
    }
  }
</style>
