import { derived, get, writable } from 'svelte/store';
import { fetchModels } from '../api/client';
import type { ModelListResponse, ModelRecord } from '../api/types';
import {
  derivePromptPrice,
  extractContextLength,
  extractInputModalities,
  extractModeration,
  extractOutputModalities,
  extractProviderName,
  extractSeries,
  extractSupportedParameters
} from '../models/utils';

export type ModelSort = 'newness' | 'price' | 'context';

export interface MultiSelectFilter {
  include: string[];
  exclude: string[];
}

export type MultiSelectKey =
  | 'inputModalities'
  | 'outputModalities'
  | 'series'
  | 'providers'
  | 'supportedParameters'
  | 'moderation';

export type MultiSelectState = 'include' | 'exclude' | 'neutral';

export interface ModelFilters {
  search: string;
  inputModalities: MultiSelectFilter;
  outputModalities: MultiSelectFilter;
  minContext: number | null;
  minPromptPrice: number | null;
  maxPromptPrice: number | null;
  sort: ModelSort;
  series: MultiSelectFilter;
  providers: MultiSelectFilter;
  supportedParameters: MultiSelectFilter;
  moderation: MultiSelectFilter;
}

// Serializable filters for presets (excludes search)
export interface PresetModelFilters {
  inputModalities?: MultiSelectFilter;
  outputModalities?: MultiSelectFilter;
  minContext?: number | null;
  minPromptPrice?: number | null;
  maxPromptPrice?: number | null;
  sort?: ModelSort;
  series?: MultiSelectFilter;
  providers?: MultiSelectFilter;
  supportedParameters?: MultiSelectFilter;
  moderation?: MultiSelectFilter;
}

interface ModelFacets {
  inputModalities: string[];
  outputModalities: string[];
  minContext: number | null;
  maxContext: number | null;
  minPromptPrice: number | null;
  maxPromptPrice: number | null;
  series: string[];
  providers: string[];
  supportedParameters: string[];
  moderation: string[];
}

interface ModelState {
  models: ModelRecord[];
  loading: boolean;
  error: string | null;
  filters: ModelFilters;
  facets: ModelFacets;
}

type SelectableModelsSelector = (
  selectedModelId: string | null | undefined,
) => ModelRecord[];

type ActiveModelSelector = (
  selectedModelId: string | null | undefined,
) => ModelRecord | null;

function createEmptyMultiSelect(): MultiSelectFilter {
  return { include: [], exclude: [] };
}

function createInitialFilters(): ModelFilters {
  return {
    search: '',
    inputModalities: createEmptyMultiSelect(),
    outputModalities: createEmptyMultiSelect(),
    minContext: null,
    minPromptPrice: null,
    maxPromptPrice: null,
    sort: 'newness',
    series: createEmptyMultiSelect(),
    providers: createEmptyMultiSelect(),
    supportedParameters: createEmptyMultiSelect(),
    moderation: createEmptyMultiSelect(),
  };
}

const emptyFacets: ModelFacets = {
  inputModalities: [],
  outputModalities: [],
  minContext: null,
  maxContext: null,
  minPromptPrice: null,
  maxPromptPrice: null,
  series: [],
  providers: [],
  supportedParameters: [],
  moderation: [],
};

const initialState: ModelState = {
  models: [],
  loading: false,
  error: null,
  filters: createInitialFilters(),
  facets: { ...emptyFacets },
};

function computeFacets(models: ModelRecord[]): ModelFacets {
  const inputSet = new Set<string>();
  const outputSet = new Set<string>();
  let minContext: number | null = null;
  let maxContext: number | null = null;
  let minPromptPrice: number | null = null;
  let maxPromptPrice: number | null = null;
  const seriesSet = new Set<string>();
  const providerSet = new Set<string>();
  const parameterSet = new Set<string>();
  const moderationSet = new Set<string>();

  for (const model of models) {
    for (const modality of extractInputModalities(model)) {
      inputSet.add(modality);
    }
    for (const modality of extractOutputModalities(model)) {
      outputSet.add(modality);
    }

    const contextLength = extractContextLength(model);
    if (contextLength !== null) {
      minContext = minContext === null ? contextLength : Math.min(minContext, contextLength);
      maxContext = maxContext === null ? contextLength : Math.max(maxContext, contextLength);
    }

    const promptPrice = derivePromptPrice(model);
    if (promptPrice !== null) {
      minPromptPrice = minPromptPrice === null ? promptPrice : Math.min(minPromptPrice, promptPrice);
      maxPromptPrice = maxPromptPrice === null ? promptPrice : Math.max(maxPromptPrice, promptPrice);
    }

    for (const label of extractSeries(model)) {
      seriesSet.add(label);
    }

    const provider = extractProviderName(model);
    if (provider) {
      providerSet.add(provider);
    }

    for (const parameter of extractSupportedParameters(model)) {
      parameterSet.add(parameter);
    }

    const moderation = extractModeration(model);
    if (moderation) {
      moderationSet.add(moderation);
    }

  }

  return {
    inputModalities: Array.from(inputSet).sort(),
    outputModalities: Array.from(outputSet).sort(),
    minContext,
    maxContext,
    minPromptPrice,
    maxPromptPrice,
    series: Array.from(seriesSet).sort(),
    providers: Array.from(providerSet).sort(),
    supportedParameters: Array.from(parameterSet).sort(),
    moderation: Array.from(moderationSet).sort(),
  };
}

function normalizeToken(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim().toLowerCase();
  return normalized ? normalized : null;
}

function normalizeList(values: readonly string[]): string[] {
  const tokens: string[] = [];
  for (const value of values) {
    const token = normalizeToken(value);
    if (token) {
      tokens.push(token);
    }
  }
  return tokens;
}

function getSelectionState(selection: MultiSelectFilter, token: string): MultiSelectState {
  if (selection.include.includes(token)) {
    return 'include';
  }
  if (selection.exclude.includes(token)) {
    return 'exclude';
  }
  return 'neutral';
}

function setSelectionByToken(
  selection: MultiSelectFilter,
  token: string,
  nextState: MultiSelectState,
): MultiSelectFilter {
  const include = selection.include.filter((item) => item !== token);
  const exclude = selection.exclude.filter((item) => item !== token);

  if (nextState === 'include') {
    return {
      include: [...include, token],
      exclude,
    };
  }

  if (nextState === 'exclude') {
    return {
      include,
      exclude: [...exclude, token],
    };
  }

  return {
    include,
    exclude,
  };
}

function applySelectionState(
  selection: MultiSelectFilter,
  rawValue: string,
  nextState: MultiSelectState,
): MultiSelectFilter {
  const token = normalizeToken(rawValue);
  if (!token) {
    return selection;
  }
  return setSelectionByToken(selection, token, nextState);
}

function matchesMultiSelect(filter: MultiSelectFilter, modelValues: string[]): boolean {
  const include = normalizeList(filter.include);
  const exclude = normalizeList(filter.exclude);

  if (include.length === 0 && exclude.length === 0) {
    return true;
  }

  const available = new Set(normalizeList(modelValues));

  if (include.length > 0) {
    for (const value of include) {
      if (!available.has(value)) {
        return false;
      }
    }
  }

  if (exclude.length > 0) {
    for (const value of exclude) {
      if (available.has(value)) {
        return false;
      }
    }
  }

  return true;
}

function filterAndSortModels(state: ModelState): ModelRecord[] {
  const { models, filters } = state;
  if (!Array.isArray(models) || models.length === 0) {
    return [];
  }

  const searchTerms = filters.search
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  const filtered = models.filter((model) => {
    if (searchTerms.length > 0) {
      const haystack = [model.id, model.name, model.description, (model.tags ?? []).join(' ')]
        .join(' ')
        .toLowerCase();
      const matches = searchTerms.every((term) => haystack.includes(term));
      if (!matches) return false;
    }

    if (!matchesMultiSelect(filters.inputModalities, extractInputModalities(model))) {
      return false;
    }

    if (!matchesMultiSelect(filters.outputModalities, extractOutputModalities(model))) {
      return false;
    }

    const contextLength = extractContextLength(model);
    if (filters.minContext !== null) {
      if (contextLength === null || contextLength < filters.minContext) {
        return false;
      }
    }

    const promptPrice = derivePromptPrice(model);
    if (filters.minPromptPrice !== null) {
      if (promptPrice === null || promptPrice < filters.minPromptPrice) {
        return false;
      }
    }
    if (filters.maxPromptPrice !== null) {
      if (promptPrice === null || promptPrice > filters.maxPromptPrice) {
        return false;
      }
    }

    if (!matchesMultiSelect(filters.series, extractSeries(model))) {
      return false;
    }

    const provider = extractProviderName(model);
    if (!matchesMultiSelect(filters.providers, provider ? [provider] : [])) {
      return false;
    }

    if (!matchesMultiSelect(filters.supportedParameters, extractSupportedParameters(model))) {
      return false;
    }

    const moderation = extractModeration(model);
    if (!matchesMultiSelect(filters.moderation, moderation ? [moderation] : [])) {
      return false;
    }

    return true;
  });

  const sorter: Record<ModelSort, (a: ModelRecord, b: ModelRecord) => number> = {
    newness: (a, b) => {
      const aDate = Date.parse((a as Record<string, unknown>).created_at as string ?? '') || 0;
      const bDate = Date.parse((b as Record<string, unknown>).created_at as string ?? '') || 0;
      return bDate - aDate;
    },
    price: (a, b) => {
      const aPrice = derivePromptPrice(a);
      const bPrice = derivePromptPrice(b);
      const left = aPrice ?? Number.POSITIVE_INFINITY;
      const right = bPrice ?? Number.POSITIVE_INFINITY;
      if (left === right) return 0;
      return left < right ? -1 : 1;
    },
    context: (a, b) => {
      const aContext = extractContextLength(a);
      const bContext = extractContextLength(b);
      const left = aContext ?? -Infinity;
      const right = bContext ?? -Infinity;
      if (left === right) return 0;
      return right - left;
    },
  };

  const comparator = sorter[filters.sort] ?? sorter.newness;
  return filtered.slice().sort(comparator);
}

function cycleMultiSelect(selection: MultiSelectFilter, rawValue: string): MultiSelectFilter {
  const token = normalizeToken(rawValue);
  if (!token) {
    return selection;
  }

  const current = getSelectionState(selection, token);
  const next: MultiSelectState =
    current === 'include' ? 'exclude' : current === 'exclude' ? 'neutral' : 'include';

  return setSelectionByToken(selection, token, next);
}

function setMultiSelectStateForKey(
  filters: ModelFilters,
  key: MultiSelectKey,
  rawValue: string,
  nextState: MultiSelectState,
): ModelFilters {
  const nextFilters = { ...filters };
  nextFilters[key] = applySelectionState(filters[key], rawValue, nextState);
  return nextFilters;
}

function sanitizeFilterValue(value: number | null): number | null {
  if (value === null) return null;
  if (Number.isNaN(value)) return null;
  if (!Number.isFinite(value)) return null;
  if (value < 0) return null;
  return value;
}

function hasAnySelection(filter: MultiSelectFilter): boolean {
  return filter.include.length > 0 || filter.exclude.length > 0;
}

function hasAnyFilters(filters: ModelFilters): boolean {
  return Boolean(
    filters.search.trim() ||
    hasAnySelection(filters.inputModalities) ||
    hasAnySelection(filters.outputModalities) ||
    hasAnySelection(filters.series) ||
    hasAnySelection(filters.providers) ||
    hasAnySelection(filters.supportedParameters) ||
    hasAnySelection(filters.moderation) ||
    filters.minContext !== null ||
    filters.minPromptPrice !== null ||
    filters.maxPromptPrice !== null,
  );
}

function ensureSelectableModels(
  base: ModelRecord[] | undefined,
  allModels: ModelRecord[],
  selectedModelId: string | null | undefined,
  activeFilters: boolean,
): ModelRecord[] {
  if (!Array.isArray(base) || base.length === 0) {
    return [];
  }

  if (!selectedModelId) {
    return base;
  }

  if (base.some((model) => model.id === selectedModelId)) {
    return base;
  }

  // When filters are active, don't add back a model that doesn't match
  if (activeFilters) {
    return base;
  }

  const selectedModel = allModels.find((model) => model.id === selectedModelId);
  if (!selectedModel) {
    return base;
  }

  return [selectedModel, ...base];
}

function findModelById(
  models: ModelRecord[] | undefined,
  selectedModelId: string | null | undefined,
): ModelRecord | null {
  if (!Array.isArray(models) || models.length === 0) {
    return null;
  }

  if (!selectedModelId) {
    return null;
  }

  const current = models.find((model) => model.id === selectedModelId);
  return current ?? null;
}

function createModelStore() {
  const store = writable<ModelState>({ ...initialState });

  async function loadModels(): Promise<ModelListResponse | void> {
    store.update((value) => ({ ...value, loading: true, error: null }));
    try {
      const response = await fetchModels();
      const models = Array.isArray(response.data) ? response.data : [];
      const facets = computeFacets(models);
      store.update((value) => ({
        ...value,
        models,
        facets,
        loading: false,
        error: null,
      }));
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      store.update((value) => ({
        ...value,
        loading: false,
        error: message,
        // Preserve existing filters and data; surface error state only.
      }));
    }
  }

  function setSearch(search: string): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        search,
      },
    }));
  }

  function toggleInputModality(modality: string): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        inputModalities: cycleMultiSelect(value.filters.inputModalities, modality),
      },
    }));
  }

  function toggleOutputModality(modality: string): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        outputModalities: cycleMultiSelect(value.filters.outputModalities, modality),
      },
    }));
  }

  function toggleSeries(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        series: cycleMultiSelect(state.filters.series, value),
      },
    }));
  }

  function toggleProvider(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        providers: cycleMultiSelect(state.filters.providers, value),
      },
    }));
  }

  function toggleSupportedParameter(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        supportedParameters: cycleMultiSelect(state.filters.supportedParameters, value),
      },
    }));
  }

  function toggleModeration(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        moderation: cycleMultiSelect(state.filters.moderation, value),
      },
    }));
  }

  function setSelectionState(
    key: MultiSelectKey,
    value: string,
    nextState: MultiSelectState,
  ): void {
    store.update((state) => ({
      ...state,
      filters: setMultiSelectStateForKey(state.filters, key, value, nextState),
    }));
  }

  function setMinContext(minContext: number | null): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        minContext: sanitizeFilterValue(minContext),
      },
    }));
  }

  function setMinPromptPrice(minPromptPrice: number | null): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        minPromptPrice: sanitizeFilterValue(minPromptPrice),
      },
    }));
  }

  function setMaxPromptPrice(maxPromptPrice: number | null): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        maxPromptPrice: sanitizeFilterValue(maxPromptPrice),
      },
    }));
  }

  function setSort(sort: ModelSort): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        sort,
      },
    }));
  }

  function resetFilters(): void {
    store.update((value) => {
      const nextFilters = createInitialFilters();
      nextFilters.sort = value.filters.sort;
      return {
        ...value,
        filters: nextFilters,
      };
    });
  }

  function getFilters(): PresetModelFilters {
    const currentFilters = get(store).filters;
    // Exclude search field and only return filters with values
    const filters: PresetModelFilters = {};

    if (hasAnySelection(currentFilters.inputModalities)) {
      filters.inputModalities = currentFilters.inputModalities;
    }
    if (hasAnySelection(currentFilters.outputModalities)) {
      filters.outputModalities = currentFilters.outputModalities;
    }
    if (currentFilters.minContext !== null) {
      filters.minContext = currentFilters.minContext;
    }
    if (currentFilters.minPromptPrice !== null) {
      filters.minPromptPrice = currentFilters.minPromptPrice;
    }
    if (currentFilters.maxPromptPrice !== null) {
      filters.maxPromptPrice = currentFilters.maxPromptPrice;
    }
    if (hasAnySelection(currentFilters.series)) {
      filters.series = currentFilters.series;
    }
    if (hasAnySelection(currentFilters.providers)) {
      filters.providers = currentFilters.providers;
    }
    if (hasAnySelection(currentFilters.supportedParameters)) {
      filters.supportedParameters = currentFilters.supportedParameters;
    }
    if (hasAnySelection(currentFilters.moderation)) {
      filters.moderation = currentFilters.moderation;
    }
    // Always include sort
    filters.sort = currentFilters.sort;

    return filters;
  }

  function setFilters(savedFilters: PresetModelFilters): void {
    store.update((value) => {
      // Start with clean filters but preserve search
      const nextFilters = createInitialFilters();
      nextFilters.search = value.filters.search;

      // Apply each filter if present and valid
      if (savedFilters.inputModalities) {
        nextFilters.inputModalities = savedFilters.inputModalities;
      }
      if (savedFilters.outputModalities) {
        nextFilters.outputModalities = savedFilters.outputModalities;
      }
      if (savedFilters.minContext !== undefined) {
        nextFilters.minContext = sanitizeFilterValue(savedFilters.minContext);
      }
      if (savedFilters.minPromptPrice !== undefined) {
        nextFilters.minPromptPrice = sanitizeFilterValue(savedFilters.minPromptPrice);
      }
      if (savedFilters.maxPromptPrice !== undefined) {
        nextFilters.maxPromptPrice = sanitizeFilterValue(savedFilters.maxPromptPrice);
      }
      if (savedFilters.series) {
        nextFilters.series = savedFilters.series;
      }
      if (savedFilters.providers) {
        nextFilters.providers = savedFilters.providers;
      }
      if (savedFilters.supportedParameters) {
        nextFilters.supportedParameters = savedFilters.supportedParameters;
      }
      if (savedFilters.moderation) {
        nextFilters.moderation = savedFilters.moderation;
      }
      if (savedFilters.sort) {
        nextFilters.sort = savedFilters.sort;
      }

      return {
        ...value,
        filters: nextFilters,
      };
    });
  }

  const models = derived(store, (state) => state.models);
  const loading = derived(store, (state) => state.loading);
  const error = derived(store, (state) => state.error);
  const filters = derived(store, (state) => state.filters);
  const facets = derived(store, (state) => state.facets);
  const filtered = derived(store, (state) => filterAndSortModels(state));
  const activeFilters = derived(store, (state) => hasAnyFilters(state.filters));
  const selectable = derived<[typeof filtered, typeof models, typeof activeFilters], SelectableModelsSelector>(
    [filtered, models, activeFilters],
    ([$filtered, $models, $activeFilters]) => {
      const base = $activeFilters ? $filtered : $models;
      return (selectedModelId: string | null | undefined) =>
        ensureSelectableModels(base, $models, selectedModelId, $activeFilters);
    },
  );

  const activeFor = derived<typeof models, ActiveModelSelector>(models, ($models) => {
    return (selectedModelId: string | null | undefined) =>
      findModelById($models, selectedModelId);
  });

  return {
    subscribe: store.subscribe,
    loadModels,
    setSearch,
    toggleInputModality,
    toggleOutputModality,
    toggleSeries,
    toggleProvider,
    toggleSupportedParameter,
    toggleModeration,
    setSelectionState,
    setMinContext,
    setMinPromptPrice,
    setMaxPromptPrice,
    setSort,
    resetFilters,
    getFilters,
    setFilters,
    models,
    loading,
    error,
    filters,
    facets,
    filtered,
    activeFilters,
    selectable,
    activeFor,
  };
}

export const modelStore = createModelStore();

export const __filterInternals = {
  matchesMultiSelect,
  cycleMultiSelect,
  applySelectionState,
};

export const __selectorInternals = {
  ensureSelectableModels,
  findModelById,
};
