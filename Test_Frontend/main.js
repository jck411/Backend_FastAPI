const chatLog = document.querySelector('#chat-log');
const messageTemplate = document.querySelector('#message-template');
const modelSelect = document.querySelector('#model-select');
const form = document.querySelector('#chat-form');
const messageInput = document.querySelector('#message-input');
const clearButton = document.querySelector('#clear-chat');
const sendButton = document.querySelector('#send-button');

const conversation = [];
let isStreaming = false;

async function initialize() {
  await loadModels();
  form.addEventListener('submit', handleSubmit);
  clearButton.addEventListener('click', resetConversation);
}

document.addEventListener('DOMContentLoaded', initialize);

function addMessage(role, content) {
  const fragment = messageTemplate.content.cloneNode(true);
  const article = fragment.querySelector('.message');
  article.classList.add(role);
  const meta = fragment.querySelector('.meta');
  meta.textContent = role === 'user' ? 'You' : 'Assistant';
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
    await requestStream();
  } catch (error) {
    console.error(error);
  }
}

async function requestStream() {
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
      messages: [...conversation],
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

function resetConversation() {
  if (isStreaming) {
    return;
  }

  conversation.length = 0;
  chatLog.innerHTML = '';
  addMessage('assistant', 'Conversation reset. Start with a message!');
}

resetConversation();

async function loadModels() {
  try {
    modelSelect.disabled = true;
    const response = await fetch('/api/models');
    if (!response.ok) {
      throw new Error('Failed to load models');
    }
    const payload = await response.json();
    const models = Array.isArray(payload?.data) ? payload.data : [];

    renderModels(models);
  } catch (error) {
    console.error('Unable to fetch models', error);
    renderModels([{ id: 'openrouter/auto', name: 'openrouter/auto' }]);
  } finally {
    modelSelect.disabled = false;
  }
}

function renderModels(models) {
  const sorted = models
    .map((model) => ({
      id: model.id || model.slug || model.name,
      label: model.name || model.id || model.slug,
    }))
    .filter((model) => Boolean(model.id));

  if (!sorted.length) {
    sorted.push({ id: 'openrouter/auto', label: 'openrouter/auto' });
  }

  sorted.sort((a, b) => a.label.localeCompare(b.label));

  modelSelect.innerHTML = '';
  for (const model of sorted) {
    const option = document.createElement('option');
    option.value = model.id;
    option.textContent = model.label;
    modelSelect.appendChild(option);
  }

  const auto = sorted.find((model) => model.id === 'openrouter/auto');
  modelSelect.value = auto ? auto.id : sorted[0].id;
}
