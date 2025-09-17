import { createModelSettingsController } from './model-settings.js';

const chatLog = document.querySelector('#chat-log');
const messageTemplate = document.querySelector('#message-template');
const modelSelect = document.querySelector('#model-select');
const form = document.querySelector('#chat-form');
const messageInput = document.querySelector('#message-input');
const clearButton = document.querySelector('#clear-chat');
const sendButton = document.querySelector('#send-button');

const openSettingsButton = document.querySelector('#open-settings');
const settingsModal = document.querySelector('#model-settings-modal');
const settingsBackdrop = document.querySelector('#model-settings-backdrop');
const closeSettingsButton = document.querySelector('#close-settings');

const conversation = [];
let sessionId = null;
let isStreaming = false;
let availableModels = [];
const MODEL_FILTER_LS_KEY = 'model-explorer.filters.v1';
const SELECTED_MODEL_LS_KEY = 'chat.selectedModel.v1';
const CHAT_STORAGE_KEY = 'chat.conversation.v1';

const modelSettingsController = createModelSettingsController({
  modelSelect,
  openSettingsButton,
  settingsModal,
  settingsBackdrop,
  closeSettingsButton,
  loadModels,
  persistSelectedModel: (value) => persistSelectedModel(value),
  getAvailableModels: () => availableModels,
});

async function initialize() {
  restoreConversationFromStorage();
  await loadModels();
  if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
    window.addEventListener('storage', handleModelFilterChange);
  }
  if (modelSelect) {
    modelSelect.addEventListener('change', handleModelSelectChange);
  }
  form.addEventListener('submit', handleSubmit);
  clearButton.addEventListener('click', (event) => {
    event.preventDefault();
    resetConversation(true).catch((error) => {
      console.error('Reset failed', error);
    });
  });

  modelSettingsController.initialize();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initialize);
} else {
  // DOM is already parsed; initialize immediately
  initialize().catch((err) => console.error('Init failed', err));
}

function addMessage(role, content, options = {}) {
  const fragment = messageTemplate.content.cloneNode(true);
  const article = fragment.querySelector('.message');
  article.classList.add(role);
  if (options.variant) {
    article.classList.add(options.variant);
  }
  const meta = fragment.querySelector('.meta');
  if (options.meta) {
    meta.textContent = options.meta;
  } else {
    meta.textContent = role === 'user' ? 'You' : 'Assistant';
  }
  const contentNode = fragment.querySelector('.content');
  contentNode.textContent = content;
  chatLog.appendChild(fragment);
  chatLog.scrollTop = chatLog.scrollHeight;
  return {
    element: article, setContent: (value) => {
      contentNode.textContent = value;
      chatLog.scrollTop = chatLog.scrollHeight;
    }
  };
}

async function handleSubmit(event) {
  event.preventDefault();
  if (isStreaming) {
    return;
  }

  const text = messageInput.value.trim();
  if (!text) {
    return;
  }

  conversation.push({ role: 'user', content: text });
  persistConversationState();
  addMessage('user', text);
  messageInput.value = '';
  messageInput.focus();

  try {
    await requestStream(text);
  } catch (error) {
    console.error(error);
  }
}

async function requestStream(latestUserMessage) {
  isStreaming = true;
  sendButton.disabled = true;
  messageInput.disabled = true;
  modelSelect.disabled = true;

  let assistantText = '';
  const assistantMessage = addMessage('assistant', '');

  try {
    const model = modelSelect.value || 'openrouter/auto';
    const payload = {
      model,
      session_id: sessionId,
      messages: [
        {
          role: 'user',
          content: latestUserMessage,
        },
      ],
    };

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Streaming failed (${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    outer: while (true) {
      const { value, done } = await reader.read();
      if (value) {
        // Normalize CRLF to LF to make parsing robust across servers
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      }

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const chunk = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');

        const event = parseSseChunk(chunk);
        if (!event.data) {
          continue;
        }

        if (event.event === 'session') {
          try {
            const info = JSON.parse(event.data);
            if (info && info.session_id) {
              sessionId = info.session_id;
              persistConversationState();
            }
          } catch (error) {
            console.warn('Failed to parse session event', error);
          }
          continue;
        }

        if (event.event === 'tool') {
          try {
            const details = JSON.parse(event.data);
            announceToolEvent(details);
          } catch (error) {
            console.warn('Failed to parse tool event', error);
          }
          continue;
        }

        if (event.data.trim() === '[DONE]') {
          break outer;
        }

        try {
          const parsed = JSON.parse(event.data);
          if (!parsed || !Array.isArray(parsed.choices)) {
            continue;
          }

          for (const choice of parsed.choices) {
            const delta = choice.delta || {};
            if (typeof delta.content === 'string') {
              assistantText += delta.content;
              assistantMessage.setContent(assistantText);
            }
          }
        } catch (error) {
          console.warn('Failed to parse SSE payload', error);
        }
      }

      if (done) {
        // Flush any remaining buffered chunk
        const leftover = buffer.trim();
        if (leftover) {
          const event = parseSseChunk(leftover);
          if (event.data && event.data.trim() !== '[DONE]') {
            try {
              const parsed = JSON.parse(event.data);
              if (parsed && Array.isArray(parsed.choices)) {
                for (const choice of parsed.choices) {
                  const delta = choice.delta || {};
                  if (typeof delta.content === 'string') {
                    assistantText += delta.content;
                    assistantMessage.setContent(assistantText);
                  }
                }
              }
            } catch (_) {
              // ignore
            }
          }
        }
        break;
      }
    }

    if (assistantText.trim()) {
      conversation.push({ role: 'assistant', content: assistantText });
      persistConversationState();
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    assistantMessage.setContent(`Error: ${message}`);
    assistantMessage.element.classList.add('error');
    throw error;
  } finally {
    sendButton.disabled = false;
    messageInput.disabled = false;
    modelSelect.disabled = false;
    isStreaming = false;
    messageInput.focus();
  }
}

function parseSseChunk(chunk) {
  const lines = chunk.split(/\r?\n/);
  const data = [];
  let eventName = null;
  let eventId = null;

  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith('data:')) {
      let value = line.slice(5);
      if (value.startsWith(' ')) value = value.slice(1);
      data.push(value);
    } else if (line.startsWith('event:')) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith('id:')) {
      eventId = line.slice(3).trim();
    }
  }

  return {
    data: data.join('\n'),
    event: eventName,
    id: eventId,
  };
}

function announceToolEvent(details) {
  if (!details || !details.name) {
    return;
  }

  const status = details.status || 'started';
  let text = `[tool] ${details.name} ${status}`;
  if (status === 'finished' && typeof details.result === 'string') {
    text += ` -> ${details.result}`;
  }
  if (status === 'error' && typeof details.result === 'string') {
    text += ` (${details.result})`;
  }

  conversation.push({ role: 'assistant', content: text, meta: 'Tool', variant: 'tool' });
  persistConversationState();
  addMessage('assistant', text, { meta: 'Tool', variant: 'tool' });
}

async function resetConversation(notifyServer = true) {
  if (isStreaming) {
    return;
  }

  if (notifyServer && sessionId) {
    try {
      await fetch(`/api/chat/session/${sessionId}`, { method: 'DELETE' });
    } catch (error) {
      console.warn('Failed to clear server session', error);
    }
  }

  sessionId = null;
  conversation.length = 0;
  clearStoredConversation();
  renderConversationFromState();
}

async function loadModels() {
  try {
    modelSelect.disabled = true;

    const url = buildModelFetchUrl();
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error('Failed to load models');
    }
    const payload = await response.json();
    console.debug('[models] raw payload', payload);
    const models = Array.isArray(payload?.data) ? payload.data : [];
    console.debug('[models] data length', models.length);

    setAvailableModels(models);
  } catch (error) {
    console.error('Unable to fetch models', error);
    setAvailableModels([{ id: 'openrouter/auto', name: 'openrouter/auto' }]);
  } finally {
    modelSelect.disabled = false;
  }
}

function setAvailableModels(models) {
  availableModels = normalizeModels(models);
  if (!availableModels.length) {
    availableModels = normalizeModels([
      { id: 'openrouter/auto', name: 'openrouter/auto', supports_tools: false },
    ]);
  }
  console.debug('[models] normalized length', availableModels.length);

  // Populate the selector with the latest normalized set
  updateModelSelect(availableModels);
}

function updateModelSelect(models) {
  const previous = modelSelect.value;
  const stored = readStoredSelectedModel();
  modelSelect.innerHTML = '';

  if (!models.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No models available (check server/API key)';
    option.disabled = true;
    option.selected = true;
    modelSelect.appendChild(option);
    return;
  }

  for (const model of models) {
    const option = document.createElement('option');
    option.value = model.id;
    option.textContent = model.label;
    option.dataset.supportsTools = String(model.supportsTools);
    modelSelect.appendChild(option);
  }

  const hasStored = stored && models.some((model) => model.id === stored.id);
  const hasPrevious = models.some((model) => model.id === previous);

  let nextValue;
  if (hasStored) {
    nextValue = stored.id;
  } else if (hasPrevious) {
    nextValue = previous;
  } else {
    nextValue = models[0].id;
  }

  modelSelect.value = nextValue;
  persistSelectedModel(nextValue);
  modelSettingsController.syncActiveModelDisplay();
}

function buildModelFetchUrl() {
  const params = new URLSearchParams();
  const stored = readStoredModelFilters();

  if (stored.search) {
    params.set('search', stored.search);
  }

  if (stored.filters && Object.keys(stored.filters).length) {
    try {
      params.set('filters', JSON.stringify(stored.filters));
    } catch (error) {
      console.warn('Failed to serialize stored filters', error);
    }
  }

  const query = params.toString();
  return query ? `/api/models?${query}` : '/api/models';
}

function readStoredModelFilters() {
  if (typeof window === 'undefined' || !window.localStorage) {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(MODEL_FILTER_LS_KEY);
    if (!raw) {
      return {};
    }
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') {
      return {};
    }

    const search = typeof data.search === 'string' ? data.search : '';
    let filters = null;
    if (data.filters && typeof data.filters === 'object' && !Array.isArray(data.filters)) {
      filters = data.filters;
    } else {
      filters = deriveFiltersFromLegacyData(data);
    }

    if (filters && Object.keys(filters).length === 0) {
      filters = null;
    }

    return { search, filters };
  } catch (error) {
    console.warn('Failed to read stored model filters', error);
    return {};
  }
}

function deriveFiltersFromLegacyData(data) {
  if (!data || typeof data !== 'object') {
    return null;
  }

  const filters = {};
  if (Array.isArray(data.inputModalities) && data.inputModalities.length) {
    filters.input_modalities = data.inputModalities;
  }
  if (Array.isArray(data.outputModalities) && data.outputModalities.length) {
    filters.output_modalities = data.outputModalities;
  }
  if (Array.isArray(data.series) && data.series.length) {
    filters.series = data.series;
  }
  if (Array.isArray(data.supportedParameters) && data.supportedParameters.length) {
    filters.supported_parameters_normalized = data.supportedParameters;
  }

  const contextValue = typeof data.contextValue === 'number' ? data.contextValue : null;
  if (typeof contextValue === 'number' && contextValue > 0) {
    filters.context_length = { min: contextValue };
  }

  const priceFreeOnly = typeof data.priceFreeOnly === 'boolean' ? data.priceFreeOnly : false;
  const priceValue = typeof data.priceValue === 'number' ? data.priceValue : null;
  if (priceFreeOnly) {
    filters.prompt_price_per_million = { min: 0, max: 0 };
  } else if (typeof priceValue === 'number' && Number.isFinite(priceValue)) {
    filters.prompt_price_per_million = { max: priceValue };
  }

  return filters;
}

function handleModelFilterChange(event) {
  if (!event || event.key !== MODEL_FILTER_LS_KEY) {
    return;
  }

  loadModels().catch((error) => console.error('Failed to refresh models after filter change', error));
}

function handleModelSelectChange() {
  persistSelectedModel(modelSelect.value);
  modelSettingsController.syncActiveModelDisplay();
}

function persistSelectedModel(modelId) {
  if (!supportsLocalStorage()) {
    return;
  }

  try {
    if (!modelId) {
      window.localStorage.removeItem(SELECTED_MODEL_LS_KEY);
      return;
    }

    const match = availableModels.find((model) => model.id === modelId);
    const payload = {
      id: modelId,
      label: match?.label || modelId,
    };
    window.localStorage.setItem(SELECTED_MODEL_LS_KEY, JSON.stringify(payload));
  } catch (error) {
    console.warn('Failed to persist selected model', error);
  }
}

function readStoredSelectedModel() {
  if (!supportsLocalStorage()) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(SELECTED_MODEL_LS_KEY);
    if (!raw) {
      return null;
    }

    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') {
      return null;
    }

    const id = typeof data.id === 'string' ? data.id.trim() : '';
    if (!id) {
      return null;
    }

    const label = typeof data.label === 'string' && data.label.trim() ? data.label : null;
    return { id, label }; // label optional; we rebuild from available models when needed
  } catch (error) {
    console.warn('Failed to read stored selected model', error);
    return null;
  }
}

function restoreConversationFromStorage() {
  const stored = readStoredConversation();

  sessionId = stored.sessionId || null;
  conversation.length = 0;
  for (const message of stored.conversation) {
    conversation.push({ ...message });
  }

  renderConversationFromState();
}

function renderConversationFromState() {
  if (!chatLog) {
    return;
  }

  chatLog.innerHTML = '';
  if (!conversation.length) {
    addMessage('assistant', 'Conversation reset. Start with a message!');
    return;
  }

  for (const entry of conversation) {
    const options = {};
    if (entry.meta) options.meta = entry.meta;
    if (entry.variant) options.variant = entry.variant;
    addMessage(entry.role, entry.content, options);
  }
}

function readStoredConversation() {
  if (!supportsLocalStorage()) {
    return { sessionId: null, conversation: [] };
  }

  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (!raw) {
      return { sessionId: null, conversation: [] };
    }

    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') {
      return { sessionId: null, conversation: [] };
    }

    const session = typeof data.sessionId === 'string' && data.sessionId ? data.sessionId : null;
    const messages = Array.isArray(data.conversation) ? data.conversation : [];

    const sanitized = [];
    for (const entry of messages) {
      if (!entry || typeof entry !== 'object') {
        continue;
      }

      const role = entry.role === 'assistant' ? 'assistant' : entry.role === 'user' ? 'user' : null;
      const content = typeof entry.content === 'string' ? entry.content : null;
      if (!role || content == null) {
        continue;
      }

      const meta = typeof entry.meta === 'string' ? entry.meta : undefined;
      const variant = typeof entry.variant === 'string' ? entry.variant : undefined;
      const record = { role, content };
      if (meta) record.meta = meta;
      if (variant) record.variant = variant;
      sanitized.push(record);
    }

    return { sessionId: session, conversation: sanitized };
  } catch (error) {
    console.warn('Failed to read stored conversation', error);
    return { sessionId: null, conversation: [] };
  }
}

function persistConversationState() {
  if (!supportsLocalStorage()) {
    return;
  }

  try {
    if (!sessionId && conversation.length === 0) {
      window.localStorage.removeItem(CHAT_STORAGE_KEY);
      return;
    }

    const payload = {
      sessionId,
      conversation: conversation.map((entry) => {
        const record = { role: entry.role, content: entry.content };
        if (entry.meta) record.meta = entry.meta;
        if (entry.variant) record.variant = entry.variant;
        return record;
      }),
    };
    window.localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    console.warn('Failed to persist conversation', error);
  }
}

function clearStoredConversation() {
  if (!supportsLocalStorage()) {
    return;
  }
  try {
    window.localStorage.removeItem(CHAT_STORAGE_KEY);
  } catch (error) {
    console.warn('Failed to clear stored conversation', error);
  }
}

function supportsLocalStorage() {
  return typeof window !== 'undefined' && !!window.localStorage;
}

function normalizeModels(models) {
  if (!Array.isArray(models)) {
    return [];
  }

  const normalized = models
    .map((model) => normalizeModel(model))
    .filter((value) => value !== null);

  normalized.sort((a, b) => a.label.localeCompare(b.label));
  return normalized;
}

function normalizeModel(model) {
  if (!model || typeof model !== 'object') {
    return null;
  }

  const id = model.id || model.slug || model.name;
  if (!id) {
    return null;
  }

  const label = model.name || model.id || model.slug || id;
  const supportsTools = detectToolSupport(model);
  return { id, label, supportsTools };
}

function detectToolSupport(model) {
  if (!model || typeof model !== 'object') {
    return false;
  }

  const capabilities = model.capabilities;
  if (capabilities && typeof capabilities === 'object') {
    for (const key of ['tools', 'functions', 'function_calling', 'tool_choice', 'tool_calls']) {
      if (isTruthy(capabilities[key])) {
        return true;
      }
    }
  }

  for (const key of ['tools', 'functions', 'supports_tools', 'supports_functions', 'supportsTools', 'supportsFunctions']) {
    if (isTruthy(model[key])) {
      return true;
    }
  }

  return false;
}

function isTruthy(value) {
  if (typeof value === 'boolean') {
    return value;
  }
  if (value == null) {
    return false;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const lowered = value.trim().toLowerCase();
    return !['', 'false', '0', 'none', 'null', 'no', 'disabled'].includes(lowered);
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === 'object') {
    return Object.keys(value).length > 0;
  }
  return true;
}
