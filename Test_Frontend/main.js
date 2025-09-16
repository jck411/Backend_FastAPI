const chatLog = document.querySelector('#chat-log');
const messageTemplate = document.querySelector('#message-template');
const modelSelect = document.querySelector('#model-select');
const modelFilter = document.querySelector('#model-filter');
const form = document.querySelector('#chat-form');
const messageInput = document.querySelector('#message-input');
const clearButton = document.querySelector('#clear-chat');
const sendButton = document.querySelector('#send-button');

const conversation = [];
let sessionId = null;
let isStreaming = false;
let availableModels = [];

async function initialize() {
  await loadModels();
  if (modelFilter) {
    modelFilter.addEventListener('change', async () => {
      await loadModels(true);
    });
  }
  form.addEventListener('submit', handleSubmit);
  clearButton.addEventListener('click', (event) => {
    event.preventDefault();
    resetConversation(true).catch((error) => {
      console.error('Reset failed', error);
    });
  });
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
  chatLog.innerHTML = '';
  addMessage('assistant', 'Conversation reset. Start with a message!');
}

resetConversation(false).catch(() => {
  // ignore initial reset errors
});

async function loadModels(triggeredByChange = false) {
  try {
    modelSelect.disabled = true;
    if (modelFilter) modelFilter.disabled = true;

    const toolsOnly = modelFilter && modelFilter.value === 'tools';
    const url = toolsOnly ? '/api/models?tools_only=true' : '/api/models';
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
    if (modelFilter) modelFilter.disabled = false;
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

  updateFilterState();
  // availableModels already reflects current filter when server-side filtering in use
  updateModelSelect(availableModels);
}

function updateFilterState() {
  if (!modelFilter) {
    return;
  }

  const hasToolModels = availableModels.some((model) => model.supportsTools);
  // Keep filter enabled even if no tool-capable models; selecting "tools" will show an empty message.
  // Optionally normalize value if previously set to tools with none available.
  if (!hasToolModels && modelFilter.value === 'tools') {
    modelFilter.value = 'all';
  }
}

function applyModelFilter() {
  const filtered = modelFilter && modelFilter.value === 'tools'
    ? availableModels.filter((model) => model.supportsTools)
    : availableModels;
  updateModelSelect(filtered);
}

function updateModelSelect(models) {
  const previous = modelSelect.value;
  modelSelect.innerHTML = '';

  if (!models.length) {
    const option = document.createElement('option');
    option.value = '';
    const filteringForTools = modelFilter && modelFilter.value === 'tools';
    option.textContent = filteringForTools
      ? 'No tool-enabled models available'
      : 'No models available (check server/API key)';
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

  const hasPrevious = models.some((model) => model.id === previous);
  modelSelect.value = hasPrevious ? previous : models[0].id;
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
