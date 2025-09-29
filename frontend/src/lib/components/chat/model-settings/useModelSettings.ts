import { onDestroy } from 'svelte';
import { derived, get, writable } from 'svelte/store';
import type {
  ModelHyperparameters,
  ModelRecord,
  ReasoningConfig,
  ReasoningEffort,
} from '../../../api/types';
import {
  buildFieldConfigs,
  collectSupportedParameterTokens,
  extractParameterSchemas,
} from './fields';
import type { ParameterSchema } from './fields';
import {
  hasReasoningEffortSupport,
  normalizeSchemaKeys,
  REASONING_SCHEMA_KEYS,
  REASONING_TOKENS,
} from './reasoning';
import { modelSettingsStore } from '../../../stores/modelSettings';

type HyperparameterKey = keyof ModelHyperparameters;

type ReasoningEnabledSelection = 'default' | 'on' | 'off';

export interface ParameterHandlers {
  onSliderInput: (key: HyperparameterKey, event: Event) => void;
  onRangeReset: (key: HyperparameterKey) => void;
  onNumberChange: (key: HyperparameterKey, event: Event) => void;
  onBooleanChange: (key: HyperparameterKey, event: Event) => void;
}

export interface ReasoningHandlers {
  onEnabledChange: (event: Event) => void;
  onEffortChange: (event: Event) => void;
  onMaxTokensChange: (event: Event) => void;
  onExcludeChange: (event: Event) => void;
}

export interface ReasoningSchemas {
  effort?: ParameterSchema;
  maxTokens?: ParameterSchema;
  exclude?: ParameterSchema;
  enabled?: ParameterSchema;
}

export interface ReasoningState {
  supported: boolean;
  schemas: ReasoningSchemas;
  enabledSelection: ReasoningEnabledSelection;
  options: ReasoningEffort[];
  effort: {
    value: ReasoningEffort | null;
    supported: boolean;
    showField: boolean;
  };
  maxTokens: {
    value: number | null;
    supported: boolean;
    showField: boolean;
  };
  exclude: boolean;
}

export interface ModelSettingsController {
  settingsState: typeof modelSettingsStore;
  parameters: ReturnType<typeof createParametersStore>;
  fields: ReturnType<typeof createFieldsStore>;
  hasCustomParameters: ReturnType<typeof createHasCustomParametersStore>;
  reasoning: ReturnType<typeof createReasoningStore>;
  parameterHandlers: ParameterHandlers;
  reasoningHandlers: ReasoningHandlers;
  resetToDefaults: () => void;
  flushSave: () => Promise<void>;
  sync: (state: { open: boolean; selectedModel: string; model: ModelRecord | null }) => void;
}

function createParametersStore() {
  return derived(modelSettingsStore, (state) => state.data?.parameters ?? null);
}

function createFieldsStore(modelStore: ReturnType<typeof writableModelStore>, parametersStore: ReturnType<typeof createParametersStore>) {
  return derived([modelStore, parametersStore], ([model, parameters]) =>
    buildFieldConfigs(model, parameters),
  );
}

function createHasCustomParametersStore(parametersStore: ReturnType<typeof createParametersStore>) {
  return derived(parametersStore, (parameters) => Boolean(parameters && Object.keys(parameters).length > 0));
}

function createCapabilitySchemasStore(modelStore: ReturnType<typeof writableModelStore>) {
  return derived(modelStore, (model) => extractParameterSchemas(model));
}

function createAvailableTokensStore(modelStore: ReturnType<typeof writableModelStore>) {
  return derived(modelStore, (model) => collectSupportedParameterTokens(model));
}

function createReasoningSchemasStore(
  capabilitySchemasStore: ReturnType<typeof createCapabilitySchemasStore>,
) {
  return derived(capabilitySchemasStore, (capabilitySchemas): ReasoningSchemas => {
    const lookup = (keys: readonly string[]): ParameterSchema | undefined => {
      for (const normalized of normalizeSchemaKeys(keys)) {
        const schema = capabilitySchemas[normalized];
        if (schema) {
          return schema;
        }
      }
      return undefined;
    };

    return {
      effort: lookup(REASONING_SCHEMA_KEYS.effort),
      maxTokens: lookup(REASONING_SCHEMA_KEYS.maxTokens),
      exclude: lookup(REASONING_SCHEMA_KEYS.exclude),
      enabled: lookup(REASONING_SCHEMA_KEYS.enabled),
    };
  });
}

function createReasoningConfigStore(parametersStore: ReturnType<typeof createParametersStore>) {
  return derived(parametersStore, (parameters) => (parameters?.reasoning as ReasoningConfig | null) ?? null);
}

function createReasoningStore(
  parametersStore: ReturnType<typeof createParametersStore>,
  reasoningConfigStore: ReturnType<typeof createReasoningConfigStore>,
  availableTokensStore: ReturnType<typeof createAvailableTokensStore>,
  reasoningSchemasStore: ReturnType<typeof createReasoningSchemasStore>,
  modelStore: ReturnType<typeof writableModelStore>,
) {
  const reasoningEffortOptions: ReasoningEffort[] = ['low', 'medium', 'high'];

  return derived(
    [parametersStore, reasoningConfigStore, availableTokensStore, reasoningSchemasStore, modelStore],
    ([parameters, reasoningConfig, availableTokens, reasoningSchemas, model]) => {
      const effortValue = (reasoningConfig?.effort as ReasoningEffort | null) ?? null;
      const maxTokensValue = reasoningConfig?.max_tokens ?? null;
      const excludeValue = reasoningConfig?.exclude === true;

      const enabledSelection: ReasoningEnabledSelection = (() => {
        if (!reasoningConfig) return 'default';
        if (reasoningConfig.enabled === true) return 'on';
        if (reasoningConfig.enabled === false) return 'off';
        return 'default';
      })();

      const reasoningSupported = (() => {
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

      const reasoningEffortHint = Boolean(
        reasoningSchemas.effort ||
          availableTokens.has('reasoning_effort') ||
          hasReasoningEffortSupport(model),
      );
      const reasoningMaxTokensHint = Boolean(
        reasoningSchemas.maxTokens || availableTokens.has('reasoning_max_tokens'),
      );

      const reasoningEffortConfigured = effortValue !== null;
      const reasoningMaxTokensConfigured = maxTokensValue !== null;

      const effortSupported = reasoningSupported && (reasoningEffortHint || reasoningEffortConfigured);
      const maxTokensSupported = reasoningSupported && (reasoningMaxTokensHint || reasoningMaxTokensConfigured);

      const showEffortField = reasoningEffortHint || reasoningEffortConfigured;
      const showMaxTokensField = reasoningMaxTokensHint || reasoningMaxTokensConfigured;

      return {
        supported: reasoningSupported,
        schemas: reasoningSchemas,
        enabledSelection,
        options: reasoningEffortOptions,
        effort: {
          value: effortValue,
          supported: effortSupported,
          showField: showEffortField,
        },
        maxTokens: {
          value: maxTokensValue,
          supported: maxTokensSupported,
          showField: showMaxTokensField,
        },
        exclude: excludeValue,
      } satisfies ReasoningState;
    },
  );
}

function writableModelStore() {
  return writable<ModelRecord | null>(null);
}

export function useModelSettings(): ModelSettingsController {
  const openStore = writable(false);
  const selectedModelStore = writable('');
  const modelStore = writableModelStore();

  const parametersStore = createParametersStore();
  const fieldsStore = createFieldsStore(modelStore, parametersStore);
  const hasCustomParametersStore = createHasCustomParametersStore(parametersStore);
  const capabilitySchemasStore = createCapabilitySchemasStore(modelStore);
  const availableTokensStore = createAvailableTokensStore(modelStore);
  const reasoningSchemasStore = createReasoningSchemasStore(capabilitySchemasStore);
  const reasoningConfigStore = createReasoningConfigStore(parametersStore);
  const reasoningStore = createReasoningStore(
    parametersStore,
    reasoningConfigStore,
    availableTokensStore,
    reasoningSchemasStore,
    modelStore,
  );

  let lastLoadedModel: string | null = null;

  const loadWatcher = derived(
    [openStore, selectedModelStore, modelSettingsStore],
    ([open, selectedModel, settingsState]) => ({ open, selectedModel, settingsState }),
  );

  const loadUnsubscribe = loadWatcher.subscribe(({ open, selectedModel, settingsState }) => {
    if (!open || !selectedModel) {
      return;
    }

    if (settingsState.data && settingsState.data.model !== selectedModel) {
      modelSettingsStore.setModel(selectedModel);
    }

    if (lastLoadedModel === selectedModel) {
      return;
    }

    lastLoadedModel = selectedModel;
    modelSettingsStore.clearErrors();
    void modelSettingsStore.load(selectedModel);
  });

  onDestroy(() => {
    loadUnsubscribe();
  });

  const parameterHandlers: ParameterHandlers = {
    onSliderInput: (key, event) => {
      const target = event.currentTarget as HTMLInputElement | null;
      if (!target) return;
      const numeric = Number(target.value);
      if (!Number.isFinite(numeric)) {
        return;
      }
      modelSettingsStore.updateParameter(key, numeric);
    },
    onRangeReset: (key) => {
      modelSettingsStore.updateParameter(key, null);
    },
    onNumberChange: (key, event) => {
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
    },
    onBooleanChange: (key, event) => {
      const target = event.currentTarget as HTMLInputElement | null;
      if (!target) return;
      modelSettingsStore.updateParameter(key, target.checked);
    },
  };

  function updateReasoning(mutator: (draft: ReasoningConfig) => void): void {
    const current = (get(reasoningConfigStore) ? { ...get(reasoningConfigStore)! } : {}) as ReasoningConfig;
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

  const reasoningHandlers: ReasoningHandlers = {
    onEnabledChange: (event) => {
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
    },
    onEffortChange: (event) => {
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
    },
    onMaxTokensChange: (event) => {
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
    },
    onExcludeChange: (event) => {
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
    },
  };

  let lastExternalState = { open: false, selectedModel: '', model: null as ModelRecord | null };

  function sync(state: { open: boolean; selectedModel: string; model: ModelRecord | null }): void {
    if (state.open !== lastExternalState.open) {
      openStore.set(state.open);
      lastExternalState.open = state.open;
    }
    if (state.selectedModel !== lastExternalState.selectedModel) {
      selectedModelStore.set(state.selectedModel);
      lastExternalState.selectedModel = state.selectedModel;
    }
    if (state.model !== lastExternalState.model) {
      modelStore.set(state.model);
      lastExternalState.model = state.model;
    }
  }

  return {
    settingsState: modelSettingsStore,
    parameters: parametersStore,
    fields: fieldsStore,
    hasCustomParameters: hasCustomParametersStore,
    reasoning: reasoningStore,
    parameterHandlers,
    reasoningHandlers,
    resetToDefaults: () => modelSettingsStore.resetToDefaults(),
    flushSave: () => modelSettingsStore.flushSave(),
    sync,
  } satisfies ModelSettingsController;
}

export type ParametersStore = ReturnType<typeof createParametersStore>;
export type FieldsStore = ReturnType<typeof createFieldsStore>;
export type HasCustomParametersStore = ReturnType<typeof createHasCustomParametersStore>;
export type ReasoningStore = ReturnType<typeof createReasoningStore>;

