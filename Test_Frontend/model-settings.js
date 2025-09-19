import {
  configureSlider,
  isSliderControl,
  parseSliderValue,
  setSliderValue,
} from './slider-fields.js';

export function createModelSettingsController({
  modelSelect,
  openSettingsButton,
  settingsModal,
  settingsBackdrop,
  closeSettingsButton,
  loadModels,
  persistSelectedModel,
  getAvailableModels,
  getSupportedParametersForModel,
}) {
  const controls = {
    form: document.querySelector('#model-settings-form'),
    activeModelDisplay: document.querySelector('#active-model-display'),
    modelDescriptionDetails: document.querySelector('#model-description-details'),
    modelDescriptionContent: document.querySelector('#model-description-content'),
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
    toolChoice: document.querySelector('#param-tool-choice'),
    safePrompt: document.querySelector('#param-safe-prompt'),
    rawMode: document.querySelector('#param-raw-mode'),
    structuredOutputs: document.querySelector('#param-structured-outputs'),
    responseFormat: document.querySelector('#param-response-format'),
    reasoningEffort: document.querySelector('#param-reasoning-effort'),
    reasoningMaxTokens: document.querySelector('#param-reasoning-max-tokens'),
    reasoningExclude: document.querySelector('#param-reasoning-exclude'),
    status: document.querySelector('#settings-status'),
    updatedAt: document.querySelector('#settings-updated-at'),
    submitButton: document.querySelector('#settings-submit'),
  };

  const integerFormatter = new Intl.NumberFormat();
  const sliderConfigurations = [
    { control: controls.temperature, defaultValue: 1, maximumFractionDigits: 2 },
    { control: controls.topP, defaultValue: 1, maximumFractionDigits: 2 },
    { control: controls.topK, defaultValue: 0, maximumFractionDigits: 0, format: (value) => (value <= 0 ? 'Auto' : integerFormatter.format(value)) },
    { control: controls.minP, defaultValue: 0, maximumFractionDigits: 2 },
    { control: controls.topA, defaultValue: 0, maximumFractionDigits: 2 },
    {
      control: controls.maxTokens,
      defaultValue: 0,
      maximumFractionDigits: 0,
      format: (value) => (value <= 0 ? 'Unset' : integerFormatter.format(value)),
    },
    { control: controls.frequencyPenalty, defaultValue: 0, maximumFractionDigits: 2 },
    { control: controls.presencePenalty, defaultValue: 0, maximumFractionDigits: 2 },
    { control: controls.repetitionPenalty, defaultValue: 1, maximumFractionDigits: 2 },
    { control: controls.seed, defaultValue: 0, maximumFractionDigits: 0, format: (value) => integerFormatter.format(value) },
    {
      control: controls.reasoningMaxTokens,
      defaultValue: 0,
      maximumFractionDigits: 0,
      format: (value) => (value <= 0 ? 'Unset' : integerFormatter.format(value))
    },
  ];

  sliderConfigurations.forEach(({ control, ...options }) => {
    if (control) {
      configureSlider(control, options);
    }
  });

  const sliderControls = sliderConfigurations
    .map(({ control }) => control)
    .filter((control) => !!control);

  const resetHyperparametersButton = document.querySelector('#reset-hyperparameters');
  resetHyperparametersButton?.addEventListener('click', (event) => {
    event.preventDefault();

    // Reset all slider controls to their defaults
    sliderControls.forEach((control) => {
      setSliderValue(control, null);
    });

    // Reset all select controls to their defaults (empty string = first option)
    const selectControls = [
      controls.providerSort,
      controls.providerDataCollection,
      controls.providerAllowFallbacks,
      controls.providerRequireParameters,
      controls.parallelToolCalls,
      controls.toolChoice,
      controls.safePrompt,
      controls.rawMode,
      controls.structuredOutputs,
      controls.responseFormat,
      controls.reasoningEffort,
      controls.reasoningExclude
    ];

    selectControls.forEach((control) => {
      if (control) {
        control.value = '';
      }
    });

    // Reset textarea controls to empty
    if (controls.stop) {
      controls.stop.value = '';
    }
  }); const state = {
    visible: false,
    saving: false,
    initialized: false,
    current: null,
  };

  async function openModal() {
    if (!settingsModal || !controls.form || state.visible) {
      return;
    }

    state.visible = true;
    settingsModal.classList.add('is-visible');
    settingsModal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    document.addEventListener('keydown', handleModalKeydown);

    setModalStatus('', null);
    setModalSavingState(false);
    updateActiveModelDisplay();
    await loadModalSettings();

    const focusTarget =
      controls.providerSort ||
      controls.providerDataCollection ||
      controls.temperature ||
      controls.submitButton;

    if (focusTarget) {
      window.setTimeout(() => {
        focusTarget.focus();
      }, 0);
    }
  }

  function closeModal() {
    if (!settingsModal || !state.visible) {
      return;
    }

    state.visible = false;
    settingsModal.classList.remove('is-visible');
    settingsModal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    document.removeEventListener('keydown', handleModalKeydown);
  }

  function handleModalKeydown(event) {
    if (event.key === 'Escape') {
      closeModal();
    }
  }

  async function loadModalSettings() {
    if (!controls.form) {
      return;
    }

    setModalStatus('Loading…', 'pending');
    try {
      const response = await fetch('/api/settings/model');
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed (${response.status})`);
      }
      const data = await response.json();
      await populateForm(data);
      setModalStatus('', null);
    } catch (error) {
      console.error('Unable to load model settings', error);
      setModalStatus(error.message || 'Unable to load settings', 'error');
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (state.saving || !controls.form) {
      return;
    }

    setModalSavingState(true);
    setModalStatus('Saving…', 'pending');

    try {
      const payload = buildSettingsPayload();
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
      await populateForm(data);
      setModalStatus('Saved', 'success');

      const activeModel = typeof data?.model === 'string' ? data.model : null;
      if (activeModel) {
        persistSelectedModel?.(activeModel);
      }

      try {
        await loadModels?.();

        const available = typeof getAvailableModels === 'function' ? getAvailableModels() || [] : [];
        if (
          activeModel &&
          modelSelect &&
          available.some((model) => model?.id === activeModel)
        ) {
          modelSelect.value = activeModel;
        }
        updateActiveModelDisplay();
      } catch (loadError) {
        console.error('Failed to refresh models after saving settings', loadError);
      }
    } catch (error) {
      console.error('Failed to save model settings', error);
      setModalStatus(error.message || 'Save failed', 'error');
    } finally {
      setModalSavingState(false);
    }
  }

  async function populateForm(settings) {
    if (!controls.form) {
      return;
    }

    state.current = settings || null;
    updateActiveModelDisplay();

    const provider = settings?.provider || {};
    // Handle both old nested "parameters" format and new flattened format
    const params = settings?.parameters || settings || {};

    if (controls.providerSort) {
      controls.providerSort.value = provider.sort || '';
    }
    if (controls.providerDataCollection) {
      controls.providerDataCollection.value = provider.data_collection || '';
    }
    setBooleanSelect(controls.providerAllowFallbacks, provider.allow_fallbacks);
    setBooleanSelect(controls.providerRequireParameters, provider.require_parameters);

    setNumberInput(controls.temperature, params.temperature);
    setNumberInput(controls.topP, params.top_p);
    setIntegerInput(controls.topK, params.top_k);
    setNumberInput(controls.minP, params.min_p);
    setNumberInput(controls.topA, params.top_a);
    setIntegerInput(controls.maxTokens, params.max_tokens);
    setNumberInput(controls.frequencyPenalty, params.frequency_penalty);
    setNumberInput(controls.presencePenalty, params.presence_penalty);
    setNumberInput(controls.repetitionPenalty, params.repetition_penalty);
    setIntegerInput(controls.seed, params.seed);

    if (controls.stop) {
      if (Array.isArray(params.stop)) {
        controls.stop.value = params.stop.join('\n');
      } else if (typeof params.stop === 'string') {
        controls.stop.value = params.stop;
      } else {
        controls.stop.value = '';
      }
    }

    setBooleanSelect(controls.parallelToolCalls, params.parallel_tool_calls);
    setStringSelect(controls.toolChoice, params.tool_choice);
    setBooleanSelect(controls.safePrompt, params.safe_prompt);
    setBooleanSelect(controls.rawMode, params.raw_mode);
    setBooleanSelect(controls.structuredOutputs, params.structured_outputs);
    setStringSelect(controls.responseFormat, params.response_format?.type);

    // Handle reasoning parameters (complex object)
    const reasoning = params.reasoning || {};
    setStringSelect(controls.reasoningEffort, reasoning.effort);
    setIntegerInput(controls.reasoningMaxTokens, reasoning.max_tokens);
    setBooleanSelect(controls.reasoningExclude, reasoning.exclude);

    updateModalUpdatedAt(settings?.updated_at);
    updateParameterVisibility();
  }

  function buildSettingsPayload() {
    const model = modelSelect?.value || 'openrouter/auto';
    const payload = { model };
    const provider = {};
    const params = {};

    const sort = controls.providerSort?.value?.trim();
    if (sort) provider.sort = sort;

    const dataCollection = controls.providerDataCollection?.value?.trim();
    if (dataCollection) provider.data_collection = dataCollection;

    const allowFallbacks = parseBooleanSelect(controls.providerAllowFallbacks);
    if (allowFallbacks !== null) provider.allow_fallbacks = allowFallbacks;

    const requireParameters = parseBooleanSelect(controls.providerRequireParameters);
    if (requireParameters !== null) provider.require_parameters = requireParameters;

    if (Object.keys(provider).length) {
      payload.provider = provider;
    }

    // Add all parameters to the nested params object for settings API
    const temperature = parseNumberField(controls.temperature);
    if (temperature !== null) params.temperature = temperature;

    const topP = parseNumberField(controls.topP);
    if (topP !== null) params.top_p = topP;

    const topK = parseIntegerField(controls.topK);
    if (topK !== null) params.top_k = topK;

    const minP = parseNumberField(controls.minP);
    if (minP !== null) params.min_p = minP;

    const topA = parseNumberField(controls.topA);
    if (topA !== null) params.top_a = topA;

    const maxTokens = parseIntegerField(controls.maxTokens);
    if (maxTokens !== null) params.max_tokens = maxTokens;

    const frequencyPenalty = parseNumberField(controls.frequencyPenalty);
    if (frequencyPenalty !== null) params.frequency_penalty = frequencyPenalty;

    const presencePenalty = parseNumberField(controls.presencePenalty);
    if (presencePenalty !== null) params.presence_penalty = presencePenalty;

    const repetitionPenalty = parseNumberField(controls.repetitionPenalty);
    if (repetitionPenalty !== null) params.repetition_penalty = repetitionPenalty;

    const seed = parseIntegerField(controls.seed);
    if (seed !== null) params.seed = seed;

    const stopSequences = parseStopField(controls.stop);
    if (stopSequences) {
      params.stop = stopSequences.length === 1 ? stopSequences[0] : stopSequences;
    }

    const parallelToolCalls = parseBooleanSelect(controls.parallelToolCalls);
    if (parallelToolCalls !== null) params.parallel_tool_calls = parallelToolCalls;

    const toolChoice = parseStringSelect(controls.toolChoice);
    if (toolChoice) params.tool_choice = toolChoice;

    const safePrompt = parseBooleanSelect(controls.safePrompt);
    if (safePrompt !== null) params.safe_prompt = safePrompt;

    const rawMode = parseBooleanSelect(controls.rawMode);
    if (rawMode !== null) params.raw_mode = rawMode;

    const structuredOutputs = parseBooleanSelect(controls.structuredOutputs);
    if (structuredOutputs !== null) params.structured_outputs = structuredOutputs;

    const responseFormat = parseStringSelect(controls.responseFormat);
    if (responseFormat) {
      params.response_format = { type: responseFormat };
    }

    // Build reasoning object if any reasoning parameters are set
    const reasoningEffort = parseStringSelect(controls.reasoningEffort);
    const reasoningMaxTokens = parseIntegerField(controls.reasoningMaxTokens);
    const reasoningExclude = parseBooleanSelect(controls.reasoningExclude);

    if (reasoningEffort || reasoningMaxTokens !== null || reasoningExclude !== null) {
      const reasoning = {};
      if (reasoningEffort) reasoning.effort = reasoningEffort;
      if (reasoningMaxTokens !== null && reasoningMaxTokens > 0) reasoning.max_tokens = reasoningMaxTokens;
      if (reasoningExclude !== null) reasoning.exclude = reasoningExclude;
      if (Object.keys(reasoning).length > 0) {
        params.reasoning = reasoning;
      }
    }

    // Only add parameters object if it has content
    if (Object.keys(params).length) {
      payload.parameters = params;
    }

    return payload;
  }

  function buildPayload() {
    const model = modelSelect?.value || 'openrouter/auto';
    const payload = { model };
    const provider = {};

    const sort = controls.providerSort?.value?.trim();
    if (sort) provider.sort = sort;

    const dataCollection = controls.providerDataCollection?.value?.trim();
    if (dataCollection) provider.data_collection = dataCollection;

    const allowFallbacks = parseBooleanSelect(controls.providerAllowFallbacks);
    if (allowFallbacks !== null) provider.allow_fallbacks = allowFallbacks;

    const requireParameters = parseBooleanSelect(controls.providerRequireParameters);
    if (requireParameters !== null) provider.require_parameters = requireParameters;

    if (Object.keys(provider).length) {
      payload.provider = provider;
    }

    // Add all parameters directly to the payload (not nested under "parameters")
    const temperature = parseNumberField(controls.temperature);
    if (temperature !== null) payload.temperature = temperature;

    const topP = parseNumberField(controls.topP);
    if (topP !== null) payload.top_p = topP;

    const topK = parseIntegerField(controls.topK);
    if (topK !== null) payload.top_k = topK;

    const minP = parseNumberField(controls.minP);
    if (minP !== null) payload.min_p = minP;

    const topA = parseNumberField(controls.topA);
    if (topA !== null) payload.top_a = topA;

    const maxTokens = parseIntegerField(controls.maxTokens);
    if (maxTokens !== null) payload.max_tokens = maxTokens;

    const frequencyPenalty = parseNumberField(controls.frequencyPenalty);
    if (frequencyPenalty !== null) payload.frequency_penalty = frequencyPenalty;

    const presencePenalty = parseNumberField(controls.presencePenalty);
    if (presencePenalty !== null) payload.presence_penalty = presencePenalty;

    const repetitionPenalty = parseNumberField(controls.repetitionPenalty);
    if (repetitionPenalty !== null) payload.repetition_penalty = repetitionPenalty;

    const seed = parseIntegerField(controls.seed);
    if (seed !== null) payload.seed = seed;

    const stopSequences = parseStopField(controls.stop);
    if (stopSequences) {
      payload.stop = stopSequences.length === 1 ? stopSequences[0] : stopSequences;
    }

    const parallelToolCalls = parseBooleanSelect(controls.parallelToolCalls);
    if (parallelToolCalls !== null) payload.parallel_tool_calls = parallelToolCalls;

    const toolChoice = parseStringSelect(controls.toolChoice);
    if (toolChoice) payload.tool_choice = toolChoice;

    const safePrompt = parseBooleanSelect(controls.safePrompt);
    if (safePrompt !== null) payload.safe_prompt = safePrompt;

    const rawMode = parseBooleanSelect(controls.rawMode);
    if (rawMode !== null) payload.raw_mode = rawMode;

    const structuredOutputs = parseBooleanSelect(controls.structuredOutputs);
    if (structuredOutputs !== null) payload.structured_outputs = structuredOutputs;

    const responseFormat = parseStringSelect(controls.responseFormat);
    if (responseFormat) {
      payload.response_format = { type: responseFormat };
    }

    // Build reasoning object if any reasoning parameters are set
    const reasoningEffort = parseStringSelect(controls.reasoningEffort);
    const reasoningMaxTokens = parseIntegerField(controls.reasoningMaxTokens);
    const reasoningExclude = parseBooleanSelect(controls.reasoningExclude);

    if (reasoningEffort || reasoningMaxTokens !== null || reasoningExclude !== null) {
      const reasoning = {};
      if (reasoningEffort) reasoning.effort = reasoningEffort;
      if (reasoningMaxTokens !== null && reasoningMaxTokens > 0) reasoning.max_tokens = reasoningMaxTokens;
      if (reasoningExclude !== null) reasoning.exclude = reasoningExclude;
      if (Object.keys(reasoning).length > 0) {
        payload.reasoning = reasoning;
      }
    }

    return payload;
  }

  function setModalSavingState(isSaving) {
    state.saving = !!isSaving;
    if (controls.submitButton) {
      controls.submitButton.disabled = !!isSaving;
    }
  }

  function setModalStatus(message, variant) {
    const node = controls.status;
    if (!node) {
      return;
    }
    node.textContent = message || '';
    if (variant) {
      node.dataset.variant = variant;
    } else {
      delete node.dataset.variant;
    }
  }

  function updateModalUpdatedAt(value) {
    const node = controls.updatedAt;
    if (!node) {
      return;
    }
    const text = formatTimestamp(value);
    node.textContent = text;
    node.hidden = !text;
  }

  function updateActiveModelDisplay() {
    const node = controls.activeModelDisplay;
    const descriptionDetails = controls.modelDescriptionDetails;
    const descriptionContent = controls.modelDescriptionContent;

    if (!node) {
      return;
    }

    if (!modelSelect) {
      node.textContent = 'No model selected';
      delete node.dataset.modelId;
      if (descriptionDetails) {
        descriptionDetails.hidden = true;
      }
      return;
    }

    const option = modelSelect.options?.[modelSelect.selectedIndex] || null;
    const value = modelSelect.value?.trim();
    const label = option?.textContent?.trim();
    const text = label || value || 'No model selected';

    node.textContent = text;
    if (value) {
      node.dataset.modelId = value;
    } else {
      delete node.dataset.modelId;
    }

    // Update model description
    if (descriptionDetails && descriptionContent) {
      const availableModels = typeof getAvailableModels === 'function' ? getAvailableModels() : [];
      const currentModel = availableModels.find(model => model?.id === value);
      const description = currentModel?.description?.trim();

      if (description) {
        descriptionContent.textContent = description;
        descriptionDetails.hidden = false;
        // Ensure it starts collapsed
        descriptionDetails.open = false;
      } else {
        descriptionDetails.hidden = true;
      }
    }
  }

  // Update parameter visibility based on current model's supported parameters
  function updateParameterVisibility() {
    const currentModelId = modelSelect?.value?.trim();
    if (!currentModelId || typeof getSupportedParametersForModel !== 'function') {
      return;
    }

    const supportedParams = getSupportedParametersForModel(currentModelId);
    const normalizedSupported = supportedParams.map(p => p.toLowerCase().trim());

    // Define parameter mappings from control to API parameter names
    const parameterMappings = [
      { control: controls.temperature, paramName: 'temperature' },
      { control: controls.topP, paramName: 'top_p' },
      { control: controls.topK, paramName: 'top_k' },
      { control: controls.minP, paramName: 'min_p' },
      { control: controls.topA, paramName: 'top_a' },
      { control: controls.maxTokens, paramName: 'max_tokens' },
      { control: controls.frequencyPenalty, paramName: 'frequency_penalty' },
      { control: controls.presencePenalty, paramName: 'presence_penalty' },
      { control: controls.repetitionPenalty, paramName: 'repetition_penalty' },
      { control: controls.seed, paramName: 'seed' },
      { control: controls.stop, paramName: 'stop' },
      { control: controls.parallelToolCalls, paramName: 'parallel_tool_calls' },
      { control: controls.toolChoice, paramName: 'tool_choice' },
      { control: controls.safePrompt, paramName: 'safe_prompt' },
      { control: controls.rawMode, paramName: 'raw_mode' },
      { control: controls.structuredOutputs, paramName: 'structured_outputs' },
      { control: controls.responseFormat, paramName: 'response_format' },
      { control: controls.reasoningEffort, paramName: 'reasoning' },
      { control: controls.reasoningMaxTokens, paramName: 'reasoning' },
      { control: controls.reasoningExclude, paramName: 'reasoning' }
    ];

    parameterMappings.forEach(({ control, paramName }) => {
      if (!control) return;

      const isSupported = isParameterSupportedByModel(paramName, normalizedSupported);
      const fieldGroup = control.closest('.field-group') || control.closest('.slider-field');

      if (fieldGroup) {
        if (isSupported) {
          fieldGroup.classList.remove('parameter-unsupported');
          fieldGroup.removeAttribute('title');
          control.disabled = false;
        } else {
          fieldGroup.classList.add('parameter-unsupported');
          fieldGroup.setAttribute('title', `This parameter is not supported by ${currentModelId}`);
          control.disabled = true;

          // Set safe default values for unsupported fields
          if (control.tagName === 'SELECT') {
            // For select elements, set to empty string (first option is usually the default)
            control.value = '';
          } else if (control.tagName === 'TEXTAREA') {
            // For textarea elements, set to empty string
            control.value = '';
          } else if (control.type === 'range') {
            // For sliders, use the data-default-value attribute
            const defaultValue = control.getAttribute('data-default-value');
            if (defaultValue !== null) {
              control.value = defaultValue;
              // Trigger any associated slider update logic
              if (isSliderControl(control)) {
                setSliderValue(control, parseFloat(defaultValue));
              }
            }
          }
        }
      }
    });
  }

  // Check if a parameter is supported by checking various alias forms
  function isParameterSupportedByModel(paramName, normalizedSupported) {
    const paramAliases = {
      'temperature': ['temperature'],
      'top_p': ['top_p', 'top-p'],
      'top_k': ['top_k', 'top-k'],
      'max_tokens': ['max_tokens', 'max-tokens', 'maxtokens'],
      'frequency_penalty': ['frequency_penalty', 'frequency-penalty'],
      'presence_penalty': ['presence_penalty', 'presence-penalty'],
      'repetition_penalty': ['repetition_penalty', 'repetition-penalty'],
      'stop': ['stop'],
      'seed': ['seed'],
      'parallel_tool_calls': ['parallel_tool_calls', 'parallel-tool-calls'],
      'tool_choice': ['tool_choice', 'tool-choice'],
      'safe_prompt': ['safe_prompt', 'safe-prompt'],
      'raw_mode': ['raw_mode', 'raw-mode'],
      'min_p': ['min_p', 'min-p'],
      'top_a': ['top_a', 'top-a'],
      'structured_outputs': ['structured_outputs', 'structured-outputs'],
      'response_format': ['response_format', 'response-format'],
      'reasoning': ['reasoning', 'reasoning_effort', 'reasoning-effort', 'reasoning_max_tokens', 'reasoning-max-tokens', 'reasoning_exclude', 'reasoning-exclude']
    };

    const aliases = paramAliases[paramName] || [paramName];
    return aliases.some(alias => normalizedSupported.includes(alias));
  }

  function formatSortLabel(value) {
    switch (value) {
      case 'price':
        return 'Sorted by price';
      case 'throughput':
        return 'Sorted by throughput';
      case 'latency':
        return 'Sorted by latency';
      default:
        return '';
    }
  }

  async function applyProviderSortStrategy(sortStrategy) {
    try {
      setModalStatus('Applying provider sort strategy...', 'pending');

      // Build and save the payload with the new sort strategy
      const payload = buildPayload();

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
      await populateForm(data);

      // Show success message briefly
      setModalStatus(`Applied ${formatSortLabel(sortStrategy)} sorting`, 'success');
      setTimeout(() => {
        setModalStatus('', null);
      }, 2000);

    } catch (error) {
      console.error('Failed to apply provider sort strategy:', error);
      setModalStatus(`Failed to apply sorting: ${error.message}`, 'error');
      // Revert the UI if there was an error
      await loadModalSettings();
    }
  } function initialize() {
    if (state.initialized || !controls.form) {
      return;
    }

    state.initialized = true;

    openSettingsButton?.addEventListener('click', () => {
      openModal().catch((error) => {
        console.error('Failed to open model settings', error);
      });
    });

    closeSettingsButton?.addEventListener('click', () => {
      closeModal();
    });

    settingsBackdrop?.addEventListener('click', () => {
      closeModal();
    });

    controls.form.addEventListener('submit', handleSubmit);

    const providerControls = [
      controls.providerSort,
      controls.providerDataCollection,
      controls.providerAllowFallbacks,
      controls.providerRequireParameters,
    ];
    providerControls.forEach((control) => {
      control?.addEventListener('change', async () => {
        try {
          // If the sort strategy changed, automatically determine and apply the best provider
          if (control === controls.providerSort && control.value) {
            await applyProviderSortStrategy(control.value);
          }
        } catch (error) {
          console.error('Failed to update provider routing:', error);
        }
      });
    });

    // Auto-set reasoning effort based on reasoning exclude setting
    controls.reasoningExclude?.addEventListener('change', () => {
      if (!controls.reasoningEffort) return;

      const excludeValue = controls.reasoningExclude.value;
      if (excludeValue === 'true') {
        // If excluding reasoning, set effort to default (empty)
        controls.reasoningEffort.value = '';
      } else if (excludeValue === 'false') {
        // If including reasoning, set effort to high
        controls.reasoningEffort.value = 'high';
      }
      // If excludeValue is empty/default, don't change reasoning effort
    });
  }

  return {
    initialize,
    syncActiveModelDisplay: () => {
      updateActiveModelDisplay();
      updateParameterVisibility();
    },
  };
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

function setStringSelect(control, value) {
  if (!control) return;
  if (value && typeof value === 'string') {
    control.value = value;
  } else {
    control.value = '';
  }
}

function parseStringSelect(control) {
  if (!control) return null;
  const value = control.value?.trim();
  return value || null;
}

function formatTimestamp(value) {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return `Updated ${date.toLocaleString()}`;
}
