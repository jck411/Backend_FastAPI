const searchInput = document.querySelector('#model-search');
const clearButton = document.querySelector('#clear-filters');
const modelGrid = document.querySelector('#model-grid');
const resultSummary = document.querySelector('#result-summary');
const SELECTED_MODEL_LS_KEY = 'chat.selectedModel.v1';

const containers = {
  inputModalities: document.querySelector('#input-modalities-options'),
  outputModalities: document.querySelector('#output-modalities-options'),
  contextLength: document.querySelector('#context-length-options'),
  promptPrice: document.querySelector('#prompt-price-options'),
  series: document.querySelector('#series-options'),
  supportedParameters: document.querySelector('#supported-parameters-options'),
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
  'include_reasoning',
  'reasoning',
  'web_search_options',
  'verbosity',
];

const state = {
  search: '',
  inputModalities: new Set(),
  outputModalities: new Set(),
  series: new Set(),
  supportedParameters: new Set(),
  // slider values
  contextValue: null, // numeric value of slider (min context). When equal to range.min, filter effectively off.
  priceValue: null,   // numeric value of slider (max price). When equal to range.max, filter effectively off.
  priceFreeOnly: false, // when true, force min=0 and max=0 for price
  ranges: {
    context: { ...DEFAULT_CONTEXT_RANGE },
    price: { ...DEFAULT_PRICE_RANGE },
    initialized: false,
  },
  prefsLoaded: false,
};

let requestCounter = 0;
let debounceTimer = null;

function initialize() {
  // Load saved preferences so initial UI reflects prior choices
  loadPreferences();
  if (searchInput) {
    searchInput.value = state.search;
  }
  renderMultiSelect(containers.inputModalities, INPUT_MODALITY_OPTIONS, state.inputModalities);
  renderMultiSelect(containers.outputModalities, OUTPUT_MODALITY_OPTIONS, state.outputModalities);
  renderContextSlider();
  renderPriceSlider();
  renderMultiSelect(
    containers.series,
    SERIES_OPTIONS.map((value) => ({ label: value, value })),
    state.series,
  );
  renderMultiSelect(
    containers.supportedParameters,
    SUPPORTED_PARAMETER_OPTIONS.map((value) => ({ label: value, value })),
    state.supportedParameters,
  );

  searchInput.addEventListener('input', handleSearchInput);
  clearButton.addEventListener('click', clearAllFilters);

  savePreferences();
  refreshResults().catch((error) => console.error('Failed to load initial models', error));
}

function renderMultiSelect(container, options, targetSet) {
  container.innerHTML = '';
  for (const option of options) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'filter-option';
    button.textContent = option.label;
    button.dataset.value = option.value;
    if (targetSet.has(option.value)) {
      button.classList.add('is-active');
    }

    button.addEventListener('click', async () => {
      if (targetSet.has(option.value)) {
        targetSet.delete(option.value);
        button.classList.remove('is-active');
      } else {
        targetSet.add(option.value);
        button.classList.add('is-active');
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
    output.textContent = val === 0 ? 'Any' : `Min ${formatContextLength(val)}`;
  }

  input.addEventListener('input', () => {
    const idx = Number(input.value);
    const val = contextValues[idx];
    state.contextValue = val;
    output.textContent = val === 0 ? 'Any' : `Min ${formatContextLength(val)}`;
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

  document.querySelectorAll('.filter-option').forEach((button) => button.classList.remove('is-active'));
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
  if (state.inputModalities.size) {
    filters.input_modalities = Array.from(state.inputModalities);
  }
  if (state.outputModalities.size) {
    filters.output_modalities = Array.from(state.outputModalities);
  }
  if (state.series.size) {
    filters.series = Array.from(state.series);
  }
  if (state.supportedParameters.size) {
    filters.supported_parameters_normalized = Array.from(state.supportedParameters);
  }
  // Slider-based filters
  if (typeof state.contextValue === 'number' && state.contextValue > 0) {
    filters.context_length = { min: state.contextValue };
  }
  if (state.priceFreeOnly) {
    filters.prompt_price_per_million = { min: 0, max: 0 };
  } else if (typeof state.priceValue === 'number' && isFinite(state.priceValue)) {
    filters.prompt_price_per_million = { max: state.priceValue };
  }
  return filters;
}

function renderResults(payload) {
  const models = Array.isArray(payload?.data) ? payload.data : [];
  const meta = payload?.metadata ?? {};
  const total = typeof meta.total === 'number' ? meta.total : models.length;
  const baseCount = typeof meta.base_count === 'number' ? meta.base_count : models.length;
  const shown = typeof meta.count === 'number' ? meta.count : models.length;

  resultSummary.textContent = `${shown} shown • ${baseCount} filtered • ${total} total`;
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

function hasActiveFilters() {
  return (
    state.search ||
    state.inputModalities.size ||
    state.outputModalities.size ||
    state.series.size ||
    state.supportedParameters.size ||
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
  context.textContent = formatContextLength(model.context_length);

  const price = fragment.querySelector('.model-price');
  price.textContent = formatPromptPrice(model.prompt_price_per_million);

  const modalities = fragment.querySelector('.model-modalities');
  const input = Array.isArray(model.input_modalities) ? model.input_modalities : [];
  const output = Array.isArray(model.output_modalities) ? model.output_modalities : [];
  modalities.textContent = `In: ${formatList(input)} • Out: ${formatList(output)}`;

  const tagContainer = fragment.querySelector('.model-tags');
  if (model.supports_tools) {
    tagContainer.appendChild(makeTag('Tools'));
  }
  const series = Array.isArray(model.series) ? model.series : [];
  series.slice(0, 3).forEach((entry) => tagContainer.appendChild(makeTag(entry)));
  const params = Array.isArray(model.supported_parameters) ? model.supported_parameters : [];
  params.slice(0, 4).forEach((entry) => tagContainer.appendChild(makeTag(entry)));

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

function formatList(values) {
  if (!Array.isArray(values) || !values.length) {
    return '—';
  }
  return values.map((value) => value.charAt(0).toUpperCase() + value.slice(1)).join(', ');
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
      out.textContent = val === 0 ? 'Any' : `Min ${formatContextLength(val)}`;
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
      inputModalities: Array.from(state.inputModalities),
      outputModalities: Array.from(state.outputModalities),
      series: Array.from(state.series),
      supportedParameters: Array.from(state.supportedParameters),
      contextValue: typeof state.contextValue === 'number' ? state.contextValue : null,
      priceValue: Number.isFinite(state.priceValue) ? state.priceValue : null,
      priceFreeOnly: !!state.priceFreeOnly,
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
      if (Array.isArray(data.inputModalities)) state.inputModalities = new Set(data.inputModalities);
      if (Array.isArray(data.outputModalities)) state.outputModalities = new Set(data.outputModalities);
      if (Array.isArray(data.series)) state.series = new Set(data.series);
      if (Array.isArray(data.supportedParameters)) state.supportedParameters = new Set(data.supportedParameters);
      if (typeof data.contextValue === 'number') state.contextValue = data.contextValue;
      if (typeof data.priceValue === 'number') state.priceValue = data.priceValue;
      else state.priceValue = null;
      if (typeof data.priceFreeOnly === 'boolean') state.priceFreeOnly = data.priceFreeOnly;
    }
  } catch (_) {
    // ignore
  }
}

function clamp(v, min, max) {
  return Math.min(Math.max(v, min), max);
}

initialize();
