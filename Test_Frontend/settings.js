import {
  configureSlider,
  isSliderControl,
  parseSliderValue,
  setSliderValue,
} from './slider-fields.js';

const searchInput = document.querySelector('#model-search');
const clearButton = document.querySelector('#clear-filters');
const modelGrid = document.querySelector('#model-grid');
const resultSummary = document.querySelector('#result-summary');
const sortButtons = {
  newness: document.querySelector('#sort-newness'),
  price: document.querySelector('#sort-price'),
  context: document.querySelector('#sort-context'),
};
const SELECTED_MODEL_LS_KEY = 'chat.selectedModel.v1';

const settingsForm = document.querySelector('#model-settings-form');
const settingsControls = {
  modelSelect: document.querySelector('#active-model'),
  providerSort: document.querySelector('#provider-sort'),
  providerDataCollection: document.querySelector('#provider-data-collection'),
  providerAllowFallbacks: document.querySelector('#provider-allow-fallbacks'),
  providerRequireParameters: document.querySelector('#provider-require-parameters'),
  temperature: document.querySelector('#param-temperature'),
  topP: document.querySelector('#param-top-p'),
  topK: document.querySelector('#param-top-k'),
  minP: document.querySelector('#param-min-p'),
  topA: document.querySelector('#param-top-a'),
  maxTokens: document.querySelector('#param-max-tokens'),
  frequencyPenalty: document.querySelector('#param-frequency-penalty'),
  presencePenalty: document.querySelector('#param-presence-penalty'),
  repetitionPenalty: document.querySelector('#param-repetition-penalty'),
  seed: document.querySelector('#param-seed'),
  stop: document.querySelector('#param-stop'),
  parallelToolCalls: document.querySelector('#param-parallel-tool-calls'),
  safePrompt: document.querySelector('#param-safe-prompt'),
  rawMode: document.querySelector('#param-raw-mode'),
  submitButton: document.querySelector('#settings-submit'),
  status: document.querySelector('#settings-status'),
  updatedAt: document.querySelector('#settings-updated-at'),
};

const integerFormatter = new Intl.NumberFormat();
const settingsSliderConfigurations = [
  { control: settingsControls.temperature, defaultValue: 1, maximumFractionDigits: 2 },
  { control: settingsControls.topP, defaultValue: 1, maximumFractionDigits: 2 },
  { control: settingsControls.topK, defaultValue: 0, maximumFractionDigits: 0, format: (value) => (value <= 0 ? 'Auto' : integerFormatter.format(value)) },
  { control: settingsControls.minP, defaultValue: 0, maximumFractionDigits: 2 },
  { control: settingsControls.topA, defaultValue: 0, maximumFractionDigits: 2 },
  {
    control: settingsControls.maxTokens,
    defaultValue: 0,
    maximumFractionDigits: 0,
    format: (value) => (value <= 0 ? 'Unset' : integerFormatter.format(value)),
  },
  { control: settingsControls.frequencyPenalty, defaultValue: 0, maximumFractionDigits: 2 },
  { control: settingsControls.presencePenalty, defaultValue: 0, maximumFractionDigits: 2 },
  { control: settingsControls.repetitionPenalty, defaultValue: 1, maximumFractionDigits: 2 },
  { control: settingsControls.seed, defaultValue: 0, maximumFractionDigits: 0, format: (value) => integerFormatter.format(value) },
];

settingsSliderConfigurations.forEach(({ control, ...options }) => {
  if (control) {
    configureSlider(control, options);
  }
});

const settingsSliderControls = settingsSliderConfigurations
  .map(({ control }) => control)
  .filter((control) => !!control);

const resetHyperparametersButton = document.querySelector('#reset-hyperparameters');
resetHyperparametersButton?.addEventListener('click', (event) => {
  event.preventDefault();
  settingsSliderControls.forEach((control) => {
    setSliderValue(control, null);
  });
});

const settingsState = {
  availableModels: [],
  selectedModel: null,
  saving: false,
  initialized: false,
  current: null,
};

const containers = {
  inputModalities: document.querySelector('#input-modalities-options'),
  outputModalities: document.querySelector('#output-modalities-options'),
  contextLength: document.querySelector('#context-length-options'),
  promptPrice: document.querySelector('#prompt-price-options'),
  series: document.querySelector('#series-options'),
  supportedParameters: document.querySelector('#supported-parameters-options'),
  moderation: document.querySelector('#moderation-options'),
};

const INPUT_MODALITY_OPTIONS = [
  { label: 'Text', value: 'text' },
  { label: 'Image', value: 'image' },
  { label: 'File', value: 'file' },
  { label: 'Audio', value: 'audio' },
];

const OUTPUT_MODALITY_OPTIONS = [
  { label: 'Text', value: 'text' },
  { label: 'Image', value: 'image' },
];

const MODERATION_OPTIONS = [
  { label: 'Moderated', value: 'true' },
  { label: 'Unmoderated', value: 'false' },
];

// Slider defaults; will be replaced by backend-provided facet ranges on first load
const DEFAULT_CONTEXT_RANGE = { min: 0, max: 1_000_000, step: 1_000 };
const DEFAULT_PRICE_RANGE = { min: 0, max: 10_000, step: 1 };
const LS_KEY = 'model-explorer.filters.v1';

const SERIES_OPTIONS = [
  'GPT',
  'Claude',
  'Gemini',
  'Grok',
  'Cohere',
  'Nova',
  'Qwen',
  'Yi',
  'DeepSeek',
  'Mistral',
  'Llama2',
  'Llama3',
  'Llama4',
  'RWKV',
  'Qwen3',
  'Router',
  'Media',
  'Other',
  'PaLM',
];

const SUPPORTED_PARAMETER_ALIAS_MAP = new Map([]);

function normalizeSupportedParameterValue(value) {
  if (typeof value !== 'string') return null;
  const token = value.trim().toLowerCase();
  if (!token) return null;
  return SUPPORTED_PARAMETER_ALIAS_MAP.get(token) ?? token;
}

const SUPPORTED_PARAMETER_OPTIONS = [
  'tools',
  'temperature',
  'top_p',
  'top_k',
  'min_p',
  'top_a',
  'frequency_penalty',
  'presence_penalty',
  'repetition_penalty',
  'max_tokens',
  'logit_bias',
  'logprobs',
  'top_logprobs',
  'seed',
  'response_format',
  'structured_outputs',
  'stop',
  'parallel_tool_calls',
  'reasoning',
  'web_search_options',
  'verbosity',
];

const state = {
  search: '',
  inputModalities: new Map(), // value -> 'include' | 'exclude'
  outputModalities: new Map(),
  series: new Map(),
  supportedParameters: new Map(),
  moderation: new Map(),
  // slider values
  contextValue: null,
  priceValue: null,
  priceFreeOnly: false,
  ranges: {
    context: { ...DEFAULT_CONTEXT_RANGE },
    price: { ...DEFAULT_PRICE_RANGE },
    initialized: false,
  },
  prefsLoaded: false,
  sortBy: 'newness',
  sortDir: 'desc',
};

let requestCounter = 0;
let debounceTimer = null;

async function initialize() {
  // Load saved preferences so initial UI reflects prior choices
  loadPreferences();
  if (searchInput) {
    searchInput.value = state.search;
  }
  renderThreeStateMultiSelect(containers.inputModalities, INPUT_MODALITY_OPTIONS, state.inputModalities);
  renderThreeStateMultiSelect(containers.outputModalities, OUTPUT_MODALITY_OPTIONS, state.outputModalities);
  renderContextSlider();
  renderPriceSlider();
  renderThreeStateMultiSelect(
    containers.series,
    SERIES_OPTIONS.map((value) => ({ label: value, value })),
    state.series,
  );
  renderThreeStateMultiSelect(
    containers.supportedParameters,
    SUPPORTED_PARAMETER_OPTIONS.map((value) => ({ label: value, value })),
    state.supportedParameters,
  );
  renderThreeStateMultiSelect(containers.moderation, MODERATION_OPTIONS, state.moderation);

  searchInput.addEventListener('input', handleSearchInput);
  clearButton.addEventListener('click', clearAllFilters);
  wireSortButtons();

  savePreferences();

  try {
    await refreshResults();
  } catch (error) {
    console.error('Failed to load initial models', error);
  }

  try {
    await initializeModelSettings();
  } catch (error) {
    console.error('Failed to initialize model settings panel', error);
  }
}

function renderThreeStateMultiSelect(container, options, targetMap) {
  container.innerHTML = '';
  for (const option of options) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'filter-option';
    button.textContent = option.label;
    button.dataset.value = option.value;

    const state = targetMap.get(option.value);
    if (state === 'include') {
      button.classList.add('is-active');
    } else if (state === 'exclude') {
      button.classList.add('is-excluded');
    }

    button.addEventListener('click', async () => {
      const currentState = targetMap.get(option.value);

      // Cycle through states: inactive -> include -> exclude -> inactive
      if (!currentState) {
        targetMap.set(option.value, 'include');
        button.classList.add('is-active');
        button.classList.remove('is-excluded');
      } else if (currentState === 'include') {
        targetMap.set(option.value, 'exclude');
        button.classList.remove('is-active');
        button.classList.add('is-excluded');
      } else {
        targetMap.delete(option.value);
        button.classList.remove('is-active');
        button.classList.remove('is-excluded');
      }

      savePreferences();
      await refreshResults();
    });

    container.appendChild(button);
  }
}

function renderContextSlider() {
  const wrapper = document.createElement('div');
  wrapper.className = 'range-control';

  const row = document.createElement('div');
  row.className = 'range-row';

  // Define discrete context values: 4k, 16k, 42k, etc.
  const contextValues = [0, 4000, 16000, 42000, 128000, 200000, 1000000, 2000000];

  const input = document.createElement('input');
  input.type = 'range';
  input.id = 'context-length-range';
  input.min = '0';
  input.max = String(contextValues.length - 1);
  input.step = '1';

  // Find closest index for current value
  let currentIndex = 0;
  if (typeof state.contextValue === 'number') {
    currentIndex = contextValues.findIndex(val => val >= state.contextValue);
    if (currentIndex === -1) currentIndex = contextValues.length - 1;
  }
  input.value = String(currentIndex);

  const output = document.createElement('output');
  output.id = 'context-length-value';
  output.className = 'range-output';
  {
    const idx = Number(input.value);
    const val = contextValues[idx];
    output.textContent = val === 0 ? 'Any' : `${formatContextLength(val)}+`;
  }

  input.addEventListener('input', () => {
    const idx = Number(input.value);
    const val = contextValues[idx];
    state.contextValue = val;
    output.textContent = val === 0 ? 'Any' : `${formatContextLength(val)}+`;
    savePreferences();
  });
  input.addEventListener('change', async () => {
    await refreshResults();
  });

  row.appendChild(input);
  row.appendChild(output);
  wrapper.appendChild(row);
  containers.contextLength.innerHTML = '';
  containers.contextLength.appendChild(wrapper);
}

function renderPriceSlider() {
  const wrapper = document.createElement('div');
  wrapper.className = 'range-control';

  const row = document.createElement('div');
  row.className = 'range-row';

  // Define discrete price values: 0.1, 0.2, 0.5, 1, 5, 10, and infinity (Any)
  const priceValues = [0.1, 0.2, 0.5, 1, 5, 10, Infinity];

  const input = document.createElement('input');
  input.type = 'range';
  input.id = 'prompt-price-range';
  input.min = '0';
  input.max = String(priceValues.length - 1);
  input.step = '1';

  // Find closest index for current value
  let currentIndex = priceValues.length - 1; // Default to 'Any'
  if (state.priceFreeOnly) {
    currentIndex = 0;
  } else if (typeof state.priceValue === 'number' && isFinite(state.priceValue)) {
    currentIndex = priceValues.findIndex(val => val >= state.priceValue);
    if (currentIndex === -1) currentIndex = priceValues.length - 1;
  }
  input.value = String(currentIndex);

  const output = document.createElement('output');
  output.id = 'prompt-price-value';
  output.className = 'range-output';
  {
    const idx = Number(input.value);
    const val = priceValues[idx];
    output.textContent = state.priceFreeOnly
      ? 'Free only'
      : val === Infinity
        ? 'Any'
        : `Max ${formatPromptPrice(val)}`;
  }

  input.addEventListener('input', () => {
    const idx = Number(input.value);
    const val = priceValues[idx];
    state.priceValue = val === Infinity ? Infinity : val;
    // moving the slider cancels free-only preset
    if (state.priceFreeOnly) {
      state.priceFreeOnly = false;
      updateFreeOnlyUi(false);
    }
    output.textContent = val === Infinity ? 'Any' : `Max ${formatPromptPrice(val)}`;
    savePreferences();
  });
  input.addEventListener('change', async () => {
    await refreshResults();
  });

  row.appendChild(input);
  row.appendChild(output);
  wrapper.appendChild(row);

  // Presets
  const presets = document.createElement('div');
  presets.className = 'range-presets';
  const freeBtn = document.createElement('button');
  freeBtn.type = 'button';
  freeBtn.className = 'filter-option';
  freeBtn.id = 'free-only-toggle';
  freeBtn.textContent = 'Free only';
  if (state.priceFreeOnly) freeBtn.classList.add('is-active');
  freeBtn.addEventListener('click', async () => {
    state.priceFreeOnly = !state.priceFreeOnly;
    updateFreeOnlyUi(state.priceFreeOnly);
    const slider = document.querySelector('#prompt-price-range');
    const priceOut = document.querySelector('#prompt-price-value');
    if (state.priceFreeOnly) {
      state.priceValue = 0;
      if (slider) slider.value = '0';
      if (priceOut) priceOut.textContent = 'Free only';
    } else {
      const val = typeof state.priceValue === 'number' && isFinite(state.priceValue) ? state.priceValue : Infinity;
      const idx = val === Infinity ? priceValues.length - 1 : priceValues.findIndex(v => v >= val);
      if (slider) slider.value = String(idx === -1 ? priceValues.length - 1 : idx);
      if (priceOut) priceOut.textContent = val === Infinity ? 'Any' : `Max ${formatPromptPrice(val)}`;
    }
    savePreferences();
    await refreshResults();
  });
  presets.appendChild(freeBtn);
  wrapper.appendChild(presets);
  containers.promptPrice.innerHTML = '';
  containers.promptPrice.appendChild(wrapper);
}

function handleSearchInput(event) {
  state.search = event.target.value.trim();
  savePreferences();
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(() => {
    refreshResults().catch((error) => console.error('Search refresh failed', error));
  }, 250);
}

function clearAllFilters() {
  state.search = '';
  searchInput.value = '';
  state.inputModalities.clear();
  state.outputModalities.clear();
  state.series.clear();
  state.supportedParameters.clear();
  state.moderation.clear();

  // Reset sliders to neutral (no-op) positions
  const contextValues = [0, 4000, 16000, 42000, 128000, 200000, 1000000, 2000000];
  const priceValues = [0.1, 0.2, 0.5, 1, 5, 10, Infinity];

  state.contextValue = 0; // 'Any'
  state.priceValue = Infinity; // 'Any'
  state.priceFreeOnly = false;

  const ctx = document.querySelector('#context-length-range');
  const ctxOut = document.querySelector('#context-length-value');
  if (ctx && ctxOut) {
    ctx.value = '0';
    ctxOut.textContent = 'Any';
  }
  const price = document.querySelector('#prompt-price-range');
  const priceOut = document.querySelector('#prompt-price-value');
  const freeBtn = document.querySelector('#free-only-toggle');
  if (price && priceOut) {
    price.value = String(priceValues.length - 1);
    priceOut.textContent = 'Any';
  }
  if (freeBtn) freeBtn.classList.remove('is-active');

  savePreferences();

  document.querySelectorAll('.filter-option').forEach((button) => {
    button.classList.remove('is-active');
    button.classList.remove('is-excluded');
  });
  refreshResults().catch((error) => console.error('Failed to refresh after clearing filters', error));
}

async function refreshResults() {
  const params = new URLSearchParams();
  if (state.search) {
    params.set('search', state.search);
  }

  const filterPayload = buildFilterPayload();
  if (Object.keys(filterPayload).length > 0) {
    params.set('filters', JSON.stringify(filterPayload));
  }

  const query = params.toString();
  const url = query ? `/api/models?${query}` : '/api/models';

  const currentRequest = ++requestCounter;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    const payload = await response.json();
    if (currentRequest !== requestCounter) {
      return;
    }
    // Initialize or update facets-driven slider ranges
    const facets = payload?.metadata?.facets;
    if (facets) {
      syncRangesFromFacets(facets);
    }
    renderResults(payload);
  } catch (error) {
    if (currentRequest === requestCounter) {
      renderResults({ data: [], metadata: { total: 0, base_count: 0, count: 0 } });
    }
    throw error;
  }
}

function buildFilterPayload() {
  const filters = {};

  // Helper function to build filter arrays from Maps
  const buildFilterFromMap = (filterMap) => {
    const included = [];
    const excluded = [];

    for (const [value, state] of filterMap) {
      if (state === 'include') {
        included.push(value);
      } else if (state === 'exclude') {
        excluded.push(value);
      }
    }

    if (included.length > 0 && excluded.length > 0) {
      // If we have both includes and excludes, use a complex filter
      return {
        "in": included,    // Must be one of these values (backend supports "in")
        "not": excluded    // Must NOT be any of these values
      };
    } else if (included.length > 0) {
      return included;
    } else if (excluded.length > 0) {
      return { "not": excluded };
    }

    return null;
  };

  const inputModalitiesFilter = buildFilterFromMap(state.inputModalities);
  if (inputModalitiesFilter) {
    filters.input_modalities = inputModalitiesFilter;
  }

  const outputModalitiesFilter = buildFilterFromMap(state.outputModalities);
  if (outputModalitiesFilter) {
    filters.output_modalities = outputModalitiesFilter;
  }

  const seriesFilter = buildFilterFromMap(state.series);
  if (seriesFilter) {
    filters.series = seriesFilter;
  }

  const supportedParametersFilter = buildFilterFromMap(state.supportedParameters);
  if (supportedParametersFilter) {
    filters.supported_parameters_normalized = supportedParametersFilter;
  }

  const moderationFilter = buildFilterFromMap(state.moderation);
  if (moderationFilter) {
    // Convert string values to boolean for the API filter
    if (Array.isArray(moderationFilter)) {
      filters['top_provider.is_moderated'] = moderationFilter.map(val => val === 'true');
    } else if (moderationFilter.not && !moderationFilter.in) {
      filters['top_provider.is_moderated'] = { "not": moderationFilter.not.map(val => val === 'true') };
    } else if (moderationFilter.in && moderationFilter.not) {
      filters['top_provider.is_moderated'] = {
        "in": moderationFilter.in.map(val => val === 'true'),
        "not": moderationFilter.not.map(val => val === 'true')
      };
    } else if (moderationFilter.in) {
      filters['top_provider.is_moderated'] = moderationFilter.in.map(val => val === 'true');
    }
  }

  // Slider-based filters (unchanged)
  if (typeof state.contextValue === 'number' && state.contextValue > 0) {
    filters.context_length = { min: state.contextValue };
  }
  if (state.priceFreeOnly) {
    filters.prompt_price_per_million = { min: 0, max: 0 };
  } else if (typeof state.priceValue === 'number' && isFinite(state.priceValue)) {
    filters.prompt_price_per_million = { max: state.priceValue };
  }

  return filters;
} function renderResults(payload) {
  const models = Array.isArray(payload?.data) ? payload.data.slice() : [];
  applySort(models);
  updateActiveModelOptions(models);
  const meta = payload?.metadata ?? {};
  const total = typeof meta.total === 'number' ? meta.total : models.length;
  const baseCount = typeof meta.base_count === 'number' ? meta.base_count : models.length;
  const shown = typeof meta.count === 'number' ? meta.count : models.length;

  const excludeIndicator = '';
  resultSummary.textContent = `${shown} shown • ${baseCount} filtered • ${total} total${excludeIndicator}`;
  clearButton.disabled = !hasActiveFilters();

  modelGrid.innerHTML = '';
  if (!models.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'No models match the current filters. Adjust your selections to see more results.';
    modelGrid.appendChild(empty);
    return;
  }

  const template = document.querySelector('#model-card-template');
  for (const model of models) {
    const instance = template.content.cloneNode(true);
    populateCard(instance, model);
    modelGrid.appendChild(instance);
  }
}

function applySort(models) {
  const by = state.sortBy || 'newness';
  const dir = state.sortDir === 'asc' ? 1 : -1;
  const collator = new Intl.Collator(undefined, { sensitivity: 'base', numeric: true });
  const getLabel = (m) => (typeof m?.name === 'string' && m.name.trim()) || (typeof m?.id === 'string' && m.id.trim()) || '';
  if (by === 'price') {
    models.sort((a, b) => {
      const av = typeof a?.prompt_price_per_million === 'number' ? a.prompt_price_per_million : Infinity;
      const bv = typeof b?.prompt_price_per_million === 'number' ? b.prompt_price_per_million : Infinity;
      return (av - bv) * dir;
    });
    return;
  }
  if (by === 'context') {
    models.sort((a, b) => {
      const av = typeof a?.context_length === 'number' ? a.context_length : -1;
      const bv = typeof b?.context_length === 'number' ? b.context_length : -1;
      return (bv - av) * (dir === 1 ? -1 : 1); // invert when asc
    });
    return;
  }
  if (by === 'newness') {
    // Use OpenRouter-provided updated_at if available, else prefer known series recency by heuristic
    models.sort((a, b) => {
      const ad = pickNewestTimestampMs(a);
      const bd = pickNewestTimestampMs(b);
      return (bd - ad) * (dir === 1 ? -1 : 1); // desc = newest first
    });
    return;
  }
  // default fallback: name
  models.sort((a, b) => collator.compare(getLabel(a), getLabel(b)) * dir);
}

function toDateMs(value) {
  if (!value) return null;
  const d = new Date(value);
  const t = d.getTime();
  return Number.isNaN(t) ? null : t;
}

function pickNewestTimestampMs(model) {
  const keys = [
    'created', // OpenRouter creation timestamp (Unix seconds)
    'updated_at', 'updatedAt',
    'release_date', 'releaseDate',
    'created_at', 'createdAt',
    'published_at', 'publishedAt',
  ];
  let best = 0;
  for (const k of keys) {
    let v;
    if (k === 'created' && typeof model?.[k] === 'number') {
      // Convert Unix timestamp (seconds) to milliseconds for consistency
      v = model[k] * 1000;
    } else {
      v = toDateMs(model?.[k]);
    }
    if (v && v > best) best = v;
  }
  return best;
}

function hasActiveFilters() {
  return (
    state.search ||
    state.inputModalities.size ||
    state.outputModalities.size ||
    state.series.size ||
    state.supportedParameters.size ||
    state.moderation.size ||
    // slider active only when deviating from neutral bounds
    (typeof state.contextValue === 'number' && state.contextValue > 0) ||
    state.priceFreeOnly ||
    (typeof state.priceValue === 'number' && isFinite(state.priceValue))
  );
}

function populateCard(fragment, model) {
  const card = fragment.querySelector('.model-card');
  const name = fragment.querySelector('.model-name');
  name.textContent = model.name || model.id || 'Unknown model';

  const id = fragment.querySelector('.model-id');
  id.textContent = model.id || '';

  const context = fragment.querySelector('.model-context');
  context.textContent = formatContextLengthForCard(model.context_length);

  const price = fragment.querySelector('.model-price');
  if (model.id && model.id.includes('auto')) {
    price.innerHTML = 'Variable';
  } else {
    price.innerHTML = formatDetailedPricing(model.pricing);
  }

  const modalities = fragment.querySelector('.model-modalities');
  const input = Array.isArray(model.input_modalities) ? model.input_modalities : [];
  const output = Array.isArray(model.output_modalities) ? model.output_modalities : [];
  modalities.innerHTML = `In: ${formatList(input)}<br>Out: ${formatList(output)}`;

  const created = fragment.querySelector('.model-created');
  created.textContent = formatCreatedDate(model.created);

  // Tags removed - users can search, filter and sort instead

  if (card && model && model.id) {
    attachCardInteractions(card, model);
  }
}

function attachCardInteractions(card, model) {
  card.classList.add('is-clickable');
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');

  const activate = () => {
    persistSelectedModel(model);
    window.location.href = '/';
  };

  card.addEventListener('click', (event) => {
    event.preventDefault();
    activate();
  });

  card.addEventListener('keydown', (event) => {
    const key = event.key;
    if (key === 'Enter' || key === ' ') {
      event.preventDefault();
      activate();
    }
  });
}

function formatContextLength(value) {
  if (typeof value !== 'number' || Number.isNaN(value) || value <= 0) {
    return '—';
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${Math.round(value / 1_000)}K`;
  }
  return `${value}`;
}

function formatContextLengthForCard(value) {
  if (typeof value !== 'number' || Number.isNaN(value) || value <= 0) {
    return '—';
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M tokens`;
  }
  if (value >= 1_000) {
    return `${Math.round(value / 1_000)}K tokens`;
  }
  return `${value} tokens`;
}

function formatPromptPrice(value) {
  if (value === undefined || value === null) {
    return 'Unknown';
  }
  if (value === 0) {
    return 'Free';
  }
  if (value < 0.01) {
    return `$${value.toFixed(3)}`;
  }
  if (value < 1) {
    return `$${value.toFixed(2)}`;
  }
  return `$${value.toFixed(1)}`;
}

function formatDetailedPricing(pricing) {
  if (!pricing || typeof pricing !== 'object') {
    return 'Unknown';
  }

  const promptPrice = parseFloat(pricing.prompt || 0);
  const completionPrice = parseFloat(pricing.completion || 0);

  if (promptPrice === 0 && completionPrice === 0) {
    return 'Free';
  }

  const formatPrice = (price) => {
    const perMillion = price * 1000000;
    if (perMillion < 0.01) {
      return `$${perMillion.toFixed(3)}`;
    }
    if (perMillion < 1) {
      return `$${perMillion.toFixed(2)}`;
    }
    return `$${perMillion.toFixed(1)}`;
  };

  const inputFormatted = formatPrice(promptPrice);
  const outputFormatted = formatPrice(completionPrice);

  return `${inputFormatted}/M input<br>${outputFormatted}/M output`;
}

function formatList(values) {
  if (!Array.isArray(values) || !values.length) {
    return '—';
  }
  return values.map((value) => value.charAt(0).toUpperCase() + value.slice(1)).join(', ');
}

function formatCreatedDate(timestamp) {
  if (typeof timestamp !== 'number' || Number.isNaN(timestamp) || timestamp <= 0) {
    return '—';
  }

  // Convert Unix timestamp (seconds) to JavaScript Date (milliseconds)
  const date = new Date(timestamp * 1000);

  // Check if the date is valid
  if (Number.isNaN(date.getTime())) {
    return '—';
  }

  // Format as a readable date string
  const now = new Date();
  const diffTime = now.getTime() - date.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays < 1) {
    return 'Today';
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return weeks === 1 ? '1 week ago' : `${weeks} weeks ago`;
  } else if (diffDays < 365) {
    const months = Math.floor(diffDays / 30);
    return months === 1 ? '1 month ago' : `${months} months ago`;
  } else {
    const years = Math.floor(diffDays / 365);
    if (years === 1) {
      return '1 year ago';
    } else if (years < 3) {
      return `${years} years ago`;
    } else {
      // For older models, show the actual date
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short'
      });
    }
  }
}

function makeTag(text) {
  const span = document.createElement('span');
  span.className = 'tag';
  span.textContent = text;
  return span;
}

function syncRangesFromFacets(facets) {
  // Context length
  const ctx = facets?.context_length || {};
  const price = facets?.prompt_price_per_million || {};

  const ctxMin = typeof ctx.min === 'number' && isFinite(ctx.min) ? Math.max(0, Math.floor(ctx.min)) : DEFAULT_CONTEXT_RANGE.min;
  const ctxMax = typeof ctx.max === 'number' && isFinite(ctx.max) ? Math.max(ctxMin, Math.ceil(ctx.max)) : DEFAULT_CONTEXT_RANGE.max;
  const priceMin = 0; // we always allow starting at free
  const priceMax = typeof price.max === 'number' && isFinite(price.max) ? Math.max(1, Math.ceil(price.max)) : DEFAULT_PRICE_RANGE.max;

  const needInit = !state.ranges.initialized;
  state.ranges.context = { min: ctxMin, max: ctxMax, step: inferContextStep(ctxMax) };
  state.ranges.price = { min: priceMin, max: priceMax, step: inferPriceStep(priceMax) };
  state.ranges.initialized = true;

  // Update DOM controls with discrete values
  const contextValues = [0, 4000, 16000, 42000, 128000, 200000, 1000000, 2000000];
  const priceValues = [0.1, 0.2, 0.5, 1, 5, 10, Infinity];

  const ctxInput = document.querySelector('#context-length-range');
  if (ctxInput) {
    if (needInit) {
      let preferred = 0;
      if (typeof state.contextValue === 'number') {
        const idx = contextValues.findIndex(val => val >= state.contextValue);
        preferred = idx === -1 ? contextValues.length - 1 : idx;
      }
      ctxInput.value = String(preferred);
      state.contextValue = contextValues[preferred];
    } else if (typeof state.contextValue === 'number') {
      const idx = contextValues.findIndex(val => val >= state.contextValue);
      const preferred = idx === -1 ? contextValues.length - 1 : idx;
      ctxInput.value = String(preferred);
      state.contextValue = contextValues[preferred];
    }
    const out = document.querySelector('#context-length-value');
    if (out) {
      const idx = Number(ctxInput.value);
      const val = contextValues[idx];
      out.textContent = val === 0 ? 'Any' : `${formatContextLength(val)}+`;
    }
  }

  const priceInput = document.querySelector('#prompt-price-range');
  if (priceInput) {
    if (needInit) {
      if (state.priceFreeOnly) {
        priceInput.value = '0';
        state.priceValue = 0;
      } else {
        let preferred = priceValues.length - 1; // Default to 'Any'
        if (typeof state.priceValue === 'number' && isFinite(state.priceValue)) {
          const idx = priceValues.findIndex(val => val >= state.priceValue);
          preferred = idx === -1 ? priceValues.length - 1 : idx;
        }
        priceInput.value = String(preferred);
        state.priceValue = priceValues[preferred];
      }
    } else if (!state.priceFreeOnly && typeof state.priceValue === 'number') {
      const idx = isFinite(state.priceValue) ? priceValues.findIndex(val => val >= state.priceValue) : priceValues.length - 1;
      const preferred = idx === -1 ? priceValues.length - 1 : idx;
      priceInput.value = String(preferred);
      state.priceValue = priceValues[preferred];
    }
    const out = document.querySelector('#prompt-price-value');
    if (out) {
      const idx = Number(priceInput.value);
      const val = priceValues[idx];
      out.textContent = state.priceFreeOnly
        ? 'Free only'
        : (val === Infinity ? 'Any' : `Max ${formatPromptPrice(val)}`);
    }
    updateFreeOnlyUi(state.priceFreeOnly);
  }
  savePreferences();
}

function inferContextStep(max) {
  // dynamic step for smoother control across ranges
  if (max >= 2_000_000) return 5_000;
  if (max >= 200_000) return 2_000;
  if (max >= 50_000) return 1_000;
  return 500;
}

function inferPriceStep(max) {
  if (max >= 10_000) return 50;
  if (max >= 2_000) return 10;
  if (max >= 200) return 5;
  if (max >= 20) return 1;
  if (max >= 2) return 0.1;
  return 0.01;
}

function renderContextTicks() {
  const host = document.querySelector('#context-length-ticks');
  if (!host) return;
  host.innerHTML = '';
  const { min, max } = state.ranges.context;
  if (!(max > min)) return;

  // Use OpenRouter's exact tick marks: 4K, 64K, 1M
  const openRouterTicks = [4000, 64000, 1000000];
  const marks = openRouterTicks.filter((v) => v >= min && v <= max);

  for (const v of marks) {
    const percent = ((v - min) / (max - min)) * 100;
    const tick = document.createElement('div');
    tick.className = 'range-tick';
    tick.style.left = `${percent}%`;
    const label = document.createElement('span');
    label.className = 'range-tick-label';
    label.textContent = formatContextTickLabel(v);
    tick.appendChild(label);
    host.appendChild(tick);
  }
}

function formatContextTickLabel(value) {
  if (value >= 1000000) {
    return `${(value / 1000000).toFixed(0)}M`;
  }
  if (value >= 1000) {
    return `${Math.round(value / 1000)}K`;
  }
  return `${value}`;
}

function pickContextTicks(min, max) {
  // Use OpenRouter's exact tick marks: 4K, 64K, 1M
  const openRouterTicks = [4000, 64000, 1000000];
  return openRouterTicks.filter((v) => v >= min && v <= max);
}

function renderPriceTicks() {
  const host = document.querySelector('#prompt-price-ticks');
  if (!host) return;
  host.innerHTML = '';
  const { min, max } = state.ranges.price;
  if (!(max > min)) return;

  // Use OpenRouter's exact tick marks: FREE, $0.5, $10+
  const openRouterPriceTicks = [0, 0.5, 10];
  const marks = openRouterPriceTicks.filter((v) => v >= min && v <= max);

  for (const v of marks) {
    const percent = ((v - min) / (max - min)) * 100;
    const tick = document.createElement('div');
    tick.className = 'range-tick';
    tick.style.left = `${percent}%`;
    const label = document.createElement('span');
    label.className = 'range-tick-label';
    label.textContent = formatPriceTickLabel(v, max);
    tick.appendChild(label);
    host.appendChild(tick);
  }
}

function formatPriceTickLabel(value, max) {
  if (value === 0) {
    return 'FREE';
  }
  if (value >= 10 && value >= max * 0.9) {
    return '$10+';
  }
  return `$${value}`;
}

function updateFreeOnlyUi(active) {
  const btn = document.querySelector('#free-only-toggle');
  if (!btn) return;
  btn.classList.toggle('is-active', !!active);
}

function persistSelectedModel(model) {
  if (!supportsLocalStorage() || !model || !model.id) {
    return;
  }

  try {
    const payload = {
      id: model.id,
      label: model.name || model.id,
    };
    window.localStorage.setItem(SELECTED_MODEL_LS_KEY, JSON.stringify(payload));
  } catch (error) {
    console.warn('Failed to persist selected model', error);
  }
}

function supportsLocalStorage() {
  return typeof window !== 'undefined' && !!window.localStorage;
}

function savePreferences() {
  try {
    const data = {
      search: state.search,
      inputModalities: Array.from(state.inputModalities.entries()),
      outputModalities: Array.from(state.outputModalities.entries()),
      series: Array.from(state.series.entries()),
      supportedParameters: Array.from(state.supportedParameters.entries()),
      moderation: Array.from(state.moderation.entries()),
      contextValue: typeof state.contextValue === 'number' ? state.contextValue : null,
      priceValue: Number.isFinite(state.priceValue) ? state.priceValue : null,
      priceFreeOnly: !!state.priceFreeOnly,
      sortBy: state.sortBy || 'newness',
      sortDir: state.sortDir || 'desc',
      filters: buildFilterPayload(),
    };
    localStorage.setItem(LS_KEY, JSON.stringify(data));
  } catch (_) {
    // ignore storage errors
  }
}

function loadPreferences() {
  if (state.prefsLoaded) return;
  state.prefsLoaded = true;
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (data && typeof data === 'object') {
      if (typeof data.search === 'string') state.search = data.search;
      if (Array.isArray(data.inputModalities)) {
        state.inputModalities = new Map(data.inputModalities);
      }
      if (Array.isArray(data.outputModalities)) {
        state.outputModalities = new Map(data.outputModalities);
      }
      if (Array.isArray(data.series)) {
        state.series = new Map(data.series);
      }
      if (Array.isArray(data.supportedParameters)) {
        const normalizedParams = data.supportedParameters
          .map(([value, filterState]) => [normalizeSupportedParameterValue(value), filterState])
          .filter(([value]) => value);
        state.supportedParameters = new Map(normalizedParams);
      }
      if (Array.isArray(data.moderation)) {
        state.moderation = new Map(data.moderation);
      }
      if (typeof data.contextValue === 'number') state.contextValue = data.contextValue;
      if (typeof data.priceValue === 'number') state.priceValue = data.priceValue;
      else state.priceValue = null;
      if (typeof data.priceFreeOnly === 'boolean') state.priceFreeOnly = data.priceFreeOnly;
      if (typeof data.sortBy === 'string') state.sortBy = data.sortBy;
      if (data.sortDir === 'asc' || data.sortDir === 'desc') state.sortDir = data.sortDir;
    }
  } catch (_) {
    // ignore
  }
}

function wireSortButtons() {
  const setActive = (key) => {
    for (const [k, btn] of Object.entries(sortButtons)) {
      if (!btn) continue;
      const isActive = k === key;
      btn.classList.toggle('is-active', isActive);
      btn.setAttribute('aria-pressed', String(isActive));
      // Update arrow indicator
      const label = btn.textContent.replace(/[\s▲▼]+$/, '');
      if (isActive) {
        const arrow = state.sortDir === 'asc' ? '▲' : '▼';
        btn.textContent = `${label} ${arrow}`;
      } else {
        btn.textContent = label;
      }
    }
  };

  const onClick = (key) => async () => {
    if (state.sortBy === key) {
      state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      state.sortBy = key;
      // default dir: newness desc (new→old), price asc (low→high), context desc (high→low)
      state.sortDir = key === 'price' ? 'asc' : 'desc';
    }
    savePreferences();
    setActive(state.sortBy);
    await refreshResults();
  };

  if (sortButtons.newness) sortButtons.newness.addEventListener('click', onClick('newness'));
  if (sortButtons.price) sortButtons.price.addEventListener('click', onClick('price'));
  if (sortButtons.context) sortButtons.context.addEventListener('click', onClick('context'));

  // Initialize active state
  setActive(state.sortBy);
}

async function initializeModelSettings() {
  if (!settingsForm) return;
  if (!settingsState.initialized) {
    settingsState.initialized = true;
    if (settingsControls.modelSelect) {
      settingsControls.modelSelect.addEventListener('change', () => {
        settingsState.selectedModel = settingsControls.modelSelect.value || null;
      });
    }
    settingsForm.addEventListener('submit', handleModelSettingsSubmit);
  }
  await loadModelSettings();
}

async function loadModelSettings() {
  if (!settingsForm) return;
  try {
    const response = await fetch('/api/settings/model');
    if (!response.ok) {
      throw new Error(`Request failed (${response.status})`);
    }
    const data = await response.json();
    populateModelSettingsForm(data);
  } catch (error) {
    console.error('Unable to load model settings', error);
    setSettingsStatus('Unable to load settings', { variant: 'error' });
  }
}

async function handleModelSettingsSubmit(event) {
  event.preventDefault();
  if (settingsState.saving) return;

  setSavingState(true);
  setSettingsStatus('Saving…', { variant: 'pending' });

  try {
    const payload = buildModelSettingsPayload();
    const response = await fetch('/api/settings/model', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Request failed (${response.status})`);
    }
    const data = await response.json();
    populateModelSettingsForm(data);
    setSettingsStatus('Saved', { variant: 'success' });
  } catch (error) {
    console.error('Failed to save model settings', error);
    setSettingsStatus(error.message || 'Save failed', { variant: 'error' });
  } finally {
    setSavingState(false);
  }
}

function populateModelSettingsForm(settings) {
  if (!settingsForm) return;
  settingsState.current = settings || null;
  settingsState.selectedModel = settings?.model || null;
  applySelectedModel();

  const provider = settings?.provider || {};
  const params = settings?.parameters || {};

  if (settingsControls.providerSort) {
    settingsControls.providerSort.value = provider.sort || '';
  }
  if (settingsControls.providerDataCollection) {
    settingsControls.providerDataCollection.value = provider.data_collection || '';
  }
  setBooleanSelect(settingsControls.providerAllowFallbacks, provider.allow_fallbacks);
  setBooleanSelect(settingsControls.providerRequireParameters, provider.require_parameters);



  setNumberInput(settingsControls.temperature, params.temperature);
  setNumberInput(settingsControls.topP, params.top_p);
  setIntegerInput(settingsControls.topK, params.top_k);
  setNumberInput(settingsControls.minP, params.min_p);
  setNumberInput(settingsControls.topA, params.top_a);
  setIntegerInput(settingsControls.maxTokens, params.max_tokens);
  setNumberInput(settingsControls.frequencyPenalty, params.frequency_penalty);
  setNumberInput(settingsControls.presencePenalty, params.presence_penalty);
  setNumberInput(settingsControls.repetitionPenalty, params.repetition_penalty);
  setIntegerInput(settingsControls.seed, params.seed);

  if (settingsControls.stop) {
    if (Array.isArray(params.stop)) {
      settingsControls.stop.value = params.stop.join('\n');
    } else if (typeof params.stop === 'string') {
      settingsControls.stop.value = params.stop;
    } else {
      settingsControls.stop.value = '';
    }
  }

  setBooleanSelect(settingsControls.parallelToolCalls, params.parallel_tool_calls);
  setBooleanSelect(settingsControls.safePrompt, params.safe_prompt);
  setBooleanSelect(settingsControls.rawMode, params.raw_mode);

  updateUpdatedAtDisplay(settings?.updated_at);
  syncStoredSelectedModel(settingsState.selectedModel);
  setSettingsStatus('', { variant: '' });
}

function applySelectedModel() {
  const select = settingsControls.modelSelect;
  if (!select) return;
  const target = settingsState.selectedModel;
  if (target) {
    const exists = Array.from(select.options).some((option) => option.value === target);
    if (exists) {
      select.value = target;
      return;
    }
  }
  if (select.options.length) {
    select.selectedIndex = 0;
    settingsState.selectedModel = select.value || null;
  } else {
    settingsState.selectedModel = null;
  }
}

function updateActiveModelOptions(models = []) {
  if (!settingsForm || !settingsControls.modelSelect) return;
  // keep select ordered by current sort for consistency
  settingsState.availableModels = Array.isArray(models) ? models.slice() : [];
  const select = settingsControls.modelSelect;
  const previous = select.value;
  select.innerHTML = '';

  const fragment = document.createDocumentFragment();
  const seen = new Set();
  for (const model of models) {
    if (!model || typeof model !== 'object') continue;
    const id = typeof model.id === 'string' ? model.id.trim() : '';
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const option = document.createElement('option');
    option.value = id;
    option.textContent = formatModelLabel(model);
    fragment.appendChild(option);
  }

  if (!seen.size && settingsState.current?.model) {
    const fallback = document.createElement('option');
    fallback.value = settingsState.current.model;
    fallback.textContent = settingsState.current.model;
    fragment.appendChild(fallback);
    seen.add(settingsState.current.model);
  }

  select.appendChild(fragment);

  if (settingsState.selectedModel && seen.has(settingsState.selectedModel)) {
    select.value = settingsState.selectedModel;
  } else if (previous && seen.has(previous)) {
    select.value = previous;
    settingsState.selectedModel = previous;
  } else if (select.options.length) {
    select.selectedIndex = 0;
    settingsState.selectedModel = select.value || null;
  } else {
    settingsState.selectedModel = null;
  }
}

function buildModelSettingsPayload() {
  const model = settingsControls.modelSelect?.value || settingsState.selectedModel || 'openrouter/auto';
  const payload = { model };

  const provider = {};
  const params = {};

  const sort = settingsControls.providerSort?.value?.trim();
  if (sort) provider.sort = sort;

  const dataCollection = settingsControls.providerDataCollection?.value?.trim();
  if (dataCollection) provider.data_collection = dataCollection;

  const allowFallbacks = parseBooleanSelect(settingsControls.providerAllowFallbacks);
  if (allowFallbacks !== null) provider.allow_fallbacks = allowFallbacks;

  const requireParameters = parseBooleanSelect(settingsControls.providerRequireParameters);
  if (requireParameters !== null) provider.require_parameters = requireParameters;

  if (Object.keys(provider).length) {
    payload.provider = provider;
  }

  const temperature = parseNumberField(settingsControls.temperature);
  if (temperature !== null) params.temperature = temperature;

  const topP = parseNumberField(settingsControls.topP);
  if (topP !== null) params.top_p = topP;

  const topK = parseIntegerField(settingsControls.topK);
  if (topK !== null) params.top_k = topK;

  const minP = parseNumberField(settingsControls.minP);
  if (minP !== null) params.min_p = minP;

  const topA = parseNumberField(settingsControls.topA);
  if (topA !== null) params.top_a = topA;

  const maxTokens = parseIntegerField(settingsControls.maxTokens);
  if (maxTokens !== null) params.max_tokens = maxTokens;

  const frequencyPenalty = parseNumberField(settingsControls.frequencyPenalty);
  if (frequencyPenalty !== null) params.frequency_penalty = frequencyPenalty;

  const presencePenalty = parseNumberField(settingsControls.presencePenalty);
  if (presencePenalty !== null) params.presence_penalty = presencePenalty;

  const repetitionPenalty = parseNumberField(settingsControls.repetitionPenalty);
  if (repetitionPenalty !== null) params.repetition_penalty = repetitionPenalty;

  const seed = parseIntegerField(settingsControls.seed);
  if (seed !== null) params.seed = seed;

  const stopSequences = parseStopField(settingsControls.stop);
  if (stopSequences) {
    params.stop = stopSequences.length === 1 ? stopSequences[0] : stopSequences;
  }

  const parallelToolCalls = parseBooleanSelect(settingsControls.parallelToolCalls);
  if (parallelToolCalls !== null) params.parallel_tool_calls = parallelToolCalls;

  const safePrompt = parseBooleanSelect(settingsControls.safePrompt);
  if (safePrompt !== null) params.safe_prompt = safePrompt;

  const rawMode = parseBooleanSelect(settingsControls.rawMode);
  if (rawMode !== null) params.raw_mode = rawMode;

  if (Object.keys(params).length) {
    payload.parameters = params;
  }

  return payload;
}

function parseNumberField(control) {
  if (!control) return null;
  if (isSliderControl(control)) {
    return parseSliderValue(control);
  }
  const raw = control.value?.trim();
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function parseIntegerField(control) {
  if (!control) return null;
  if (isSliderControl(control)) {
    return parseSliderValue(control, { integer: true });
  }
  const value = parseNumberField(control);
  if (value === null) return null;
  const intValue = Math.trunc(value);
  return Number.isFinite(intValue) ? intValue : null;
}

function parseBooleanSelect(control) {
  if (!control) return null;
  const value = control.value;
  if (value === 'true') return true;
  if (value === 'false') return false;
  return null;
}

function parseStopField(control) {
  if (!control) return null;
  const raw = control.value || '';
  const entries = raw
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
  return entries.length ? entries : null;
}

function setNumberInput(control, value) {
  if (!control) return;
  if (isSliderControl(control)) {
    setSliderValue(control, value);
    return;
  }
  if (value === undefined || value === null || value === '') {
    control.value = '';
  } else {
    control.value = String(value);
  }
}

function setIntegerInput(control, value) {
  setNumberInput(control, value);
}

function setBooleanSelect(control, value) {
  if (!control) return;
  if (value === true) {
    control.value = 'true';
  } else if (value === false) {
    control.value = 'false';
  } else {
    control.value = '';
  }
}

function setSavingState(isSaving) {
  settingsState.saving = !!isSaving;
  if (settingsControls.submitButton) {
    settingsControls.submitButton.disabled = !!isSaving;
  }
}

function setSettingsStatus(message, { variant } = {}) {
  const node = settingsControls.status;
  if (!node) return;
  node.textContent = message || '';
  if (variant) {
    node.dataset.variant = variant;
  } else {
    delete node.dataset.variant;
  }
}

function updateUpdatedAtDisplay(value) {
  const node = settingsControls.updatedAt;
  if (!node) return;
  const text = formatTimestamp(value);
  node.textContent = text;
  node.hidden = !text;
}

function syncStoredSelectedModel(modelId) {
  if (!modelId || typeof persistSelectedModel !== 'function') return;
  const match = settingsState.availableModels.find((entry) => entry && entry.id === modelId);
  if (match) {
    persistSelectedModel(match);
  } else {
    persistSelectedModel({ id: modelId, name: modelId });
  }
}

function formatTimestamp(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return `Updated ${date.toLocaleString()}`;
}

function formatModelLabel(model) {
  const id = typeof model?.id === 'string' ? model.id : '';
  const name = typeof model?.name === 'string' ? model.name : '';
  if (!id) return name || 'Unknown model';
  if (name && name !== id) {
    return `${name} (${id})`;
  }
  return id;
}

function clamp(v, min, max) {
  return Math.min(Math.max(v, min), max);
}

initialize().catch((error) => console.error('Settings init failed', error));
