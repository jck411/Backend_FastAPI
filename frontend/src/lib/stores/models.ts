import { derived, writable } from 'svelte/store';
import { fetchModels } from '../api/client';
import type { ModelListResponse, ModelRecord } from '../api/types';
import {
  asNumeric,
  derivePromptPrice,
  extractContextLength,
  extractInputModalities,
  extractModeration,
  extractOutputModalities,
  extractProviderName,
  extractSeries,
  extractSupportedParameters,
} from '../models/utils';

export type ModelSort = 'newness' | 'price' | 'context';

interface ModelFilters {
  search: string;
  inputModalities: string[];
  outputModalities: string[];
  minContext: number | null;
  minPromptPrice: number | null;
  maxPromptPrice: number | null;
  sort: ModelSort;
  series: string[];
  providers: string[];
  supportedParameters: string[];
  moderation: string[];
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

const initialFilters: ModelFilters = {
  search: '',
  inputModalities: [],
  outputModalities: [],
  minContext: null,
  minPromptPrice: null,
  maxPromptPrice: null,
  sort: 'newness',
  series: [],
  providers: [],
  supportedParameters: [],
  moderation: [],
};

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
  filters: { ...initialFilters },
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

function matchesModality(filterValues: string[], modelModalities: string[]): boolean {
  if (filterValues.length === 0) return true;
  if (modelModalities.length === 0) return false;
  const set = new Set(modelModalities);
  return filterValues.some((value) => set.has(value));
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
      const haystack = [model.id, model.name, model.description, (model.tags ?? []).join(' ') ]
        .join(' ')
        .toLowerCase();
      const matches = searchTerms.every((term) => haystack.includes(term));
      if (!matches) return false;
    }

    if (!matchesModality(filters.inputModalities, extractInputModalities(model))) {
      return false;
    }

    if (!matchesModality(filters.outputModalities, extractOutputModalities(model))) {
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

    if (filters.series.length > 0) {
      const seriesValues = extractSeries(model).map((value) => value.toLowerCase());
      if (!matchesModality(filters.series.map((value) => value.toLowerCase()), seriesValues)) {
        return false;
      }
    }

    if (filters.providers.length > 0) {
      const provider = extractProviderName(model)?.toLowerCase() ?? null;
      if (!provider || !filters.providers.some((value) => provider === value.toLowerCase())) {
        return false;
      }
    }

    if (filters.supportedParameters.length > 0) {
      const parameters = extractSupportedParameters(model).map((value) => value.toLowerCase());
      if (!matchesModality(filters.supportedParameters.map((value) => value.toLowerCase()), parameters)) {
        return false;
      }
    }

    if (filters.moderation.length > 0) {
      const moderation = extractModeration(model)?.toLowerCase() ?? null;
      if (!moderation || !filters.moderation.some((value) => moderation === value.toLowerCase())) {
        return false;
      }
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

function toggleValue(values: string[], value: string): string[] {
  const normalized = value.toLowerCase();
  if (!normalized) return values;
  if (values.includes(normalized)) {
    return values.filter((item) => item !== normalized);
  }
  return [...values, normalized];
}

function sanitizeFilterValue(value: number | null): number | null {
  if (value === null) return null;
  if (Number.isNaN(value)) return null;
  if (!Number.isFinite(value)) return null;
  if (value < 0) return null;
  return value;
}

function hasAnyFilters(filters: ModelFilters): boolean {
  return Boolean(
    filters.search.trim() ||
      filters.inputModalities.length ||
      filters.outputModalities.length ||
      filters.series.length ||
      filters.providers.length ||
      filters.supportedParameters.length ||
      filters.moderation.length ||
      filters.minContext !== null ||
      filters.minPromptPrice !== null ||
      filters.maxPromptPrice !== null,
  );
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
        // Reset filters to defaults when the catalog refreshes.
        filters: { ...initialFilters },
      }));
      return response;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      store.set({
        models: [],
        loading: false,
        error: message,
        filters: { ...initialFilters },
        facets: { ...emptyFacets },
      });
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
        inputModalities: toggleValue(value.filters.inputModalities, modality),
      },
    }));
  }

  function toggleOutputModality(modality: string): void {
    store.update((value) => ({
      ...value,
      filters: {
        ...value.filters,
        outputModalities: toggleValue(value.filters.outputModalities, modality),
      },
    }));
  }

  function toggleSeries(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        series: toggleValue(state.filters.series, value),
      },
    }));
  }

  function toggleProvider(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        providers: toggleValue(state.filters.providers, value),
      },
    }));
  }

  function toggleSupportedParameter(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        supportedParameters: toggleValue(state.filters.supportedParameters, value),
      },
    }));
  }

  function toggleModeration(value: string): void {
    store.update((state) => ({
      ...state,
      filters: {
        ...state.filters,
        moderation: toggleValue(state.filters.moderation, value),
      },
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
    store.update((value) => ({
      ...value,
      filters: { ...initialFilters, sort: value.filters.sort },
    }));
  }

  const models = derived(store, (state) => state.models);
  const loading = derived(store, (state) => state.loading);
  const error = derived(store, (state) => state.error);
  const filters = derived(store, (state) => state.filters);
  const facets = derived(store, (state) => state.facets);
  const filtered = derived(store, (state) => filterAndSortModels(state));
  const activeFilters = derived(store, (state) => hasAnyFilters(state.filters));

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
    setMinContext,
    setMinPromptPrice,
    setMaxPromptPrice,
    setSort,
    resetFilters,
    models,
    loading,
    error,
    filters,
    facets,
    filtered,
    activeFilters,
  };
}

export const modelStore = createModelStore();
