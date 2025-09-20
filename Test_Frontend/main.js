import { renderMarkdown } from './markdown.js';
import { createModelSettingsController } from './model-settings.js';
import { createSpeechSettingsController, getSpeechSettings, SPEECH_SETTINGS_LS_KEY } from './speech-settings.js';

const chatLog = document.querySelector('#chat-log');
const messageTemplate = document.querySelector('#message-template');
const modelSelect = document.querySelector('#model-select');
const form = document.querySelector('#chat-form');
const messageInput = document.querySelector('#message-input');
const clearButton = document.querySelector('#clear-chat');
const stopButton = document.querySelector('#stop-button');
const voiceButton = document.querySelector('#voice-button');
const modelExplorerButton = document.querySelector('#model-explorer-button');
const webSearchButton = document.querySelector('#toggle-web-search');

const openSettingsButton = document.querySelector('#open-settings');
const settingsModal = document.querySelector('#model-settings-modal');
const settingsBackdrop = document.querySelector('#model-settings-backdrop');
const closeSettingsButton = document.querySelector('#close-settings');
const openSpeechSettingsButton = document.querySelector('#open-speech-settings');
const speechSettingsModal = document.querySelector('#speech-settings-modal');
const speechSettingsBackdrop = document.querySelector('#speech-settings-backdrop');
const closeSpeechSettingsButton = document.querySelector('#close-speech-settings');
const metadataModal = document.querySelector('#message-metadata-modal');
const closeMetadataButton = document.querySelector('#close-message-metadata');
const metadataContent = document.querySelector('#message-metadata-content');

const conversation = [];
let sessionId = null;
let isStreaming = false;
let availableModels = [];
let metadataModalVisible = false;
const MODEL_FILTER_LS_KEY = 'model-explorer.filters.v1';
const SELECTED_MODEL_LS_KEY = 'chat.selectedModel.v1';
const CHAT_STORAGE_KEY = 'chat.conversation.v1';
const WEB_SEARCH_PREF_KEY = 'chat.webSearchEnabled.v1';
const DEFAULT_WEB_SEARCH_RESULTS = 3;
const metadataNumberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 2,
});
const metadataCreditFormatter = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 6,
});
const generationDetailsCache = new Map();
let activeMetadataRecord = null;
let metadataMoreInfoState = {
  generationId: null,
  expanded: false,
  loading: false,
  data: null,
  error: null,
};
let currentStreamAbortController = null;
let stopRequested = false;
let isChatLogPinnedToBottom = true;
let pendingScrollAnimationFrame = null;
let webSearchEnabled = false;

let wakewordSource = null;

function startWakewordListener() {
  try {
    fetch('/api/stt/wakeword/listener/start', { method: 'POST' }).catch(() => { });
  } catch (_) {
    // ignore
  }
}

function stopWakewordListener() {
  try {
    fetch('/api/stt/wakeword/listener/stop', { method: 'POST' }).catch(() => { });
  } catch (_) {
    // ignore
  }
}

function updateWakewordSubscription() {
  try {
    const settings = getSpeechSettings();
    const enabled = !!(settings && settings.wakeword && settings.wakeword.enabled);
    if (enabled) {
      // Ensure backend listener process is running
      startWakewordListener();

      // Create SSE subscription if not already connected
      if (!wakewordSource) {
        wakewordSource = new EventSource('/api/stt/wakeword/stream');
        wakewordSource.addEventListener('wakeword', (ev) => {
          try {
            const data = JSON.parse(ev.data || '{}');
            if (data && data.type === 'wakeword') {
              console.log('🎤 Wakeword detected, triggering voice input...', { isRecording, isStreaming });
              // Only trigger if not already recording to avoid interrupting ongoing session
              if (!isRecording && !isStreaming) {
                handleVoiceClick();
              } else {
                console.log('🎤 Ignoring wakeword - already recording or streaming');
              }
            }
          } catch (_) {
            // ignore parse errors
          }
        });
        wakewordSource.onerror = () => {
          // keep connection; browser will auto-reconnect
        };
      }
    } else {
      // Close SSE and stop backend listener process
      if (wakewordSource) {
        try { wakewordSource.close(); } catch (_) { }
        wakewordSource = null;
      }
      stopWakewordListener();
    }
  } catch (err) {
    console.warn('Wakeword subscription error', err);
  }
}

function handleSpeechSettingsStorageChange(event) {
  if (!event || event.key !== SPEECH_SETTINGS_LS_KEY) {
    return;
  }
  updateWakewordSubscription();
}

// STT state
let isRecording = false;
let dgSocket = null;
let mediaStream = null;
let mediaRecorder = null;
let lastFinalTranscript = '';
let voiceInputPreviousValue = '';
let conversationModeActive = false; // Track if conversation mode initiated the current interaction
let listeningTimeoutId = null; // Track the listening timeout
let countdownIntervalId = null; // Track the countdown interval
let countdownSecondsRemaining = 0; // Track remaining seconds for countdown
let countdownTimeoutMs = 0; // Store the original timeout value for resetting

// Function to reset countdown when speech is detected
function resetCountdown() {
  if (!countdownIntervalId || countdownTimeoutMs === 0) return;

  console.log('🎤 Speech detected - resetting countdown');

  // Clear existing timeout and interval
  if (listeningTimeoutId) {
    clearTimeout(listeningTimeoutId);
    listeningTimeoutId = null;
  }
  if (countdownIntervalId) {
    clearInterval(countdownIntervalId);
    countdownIntervalId = null;
  }

  // Reset countdown to full value
  countdownSecondsRemaining = Math.ceil(countdownTimeoutMs / 1000);
  updateVoiceUi(true, countdownSecondsRemaining);

  // Restart countdown interval
  countdownIntervalId = setInterval(() => {
    countdownSecondsRemaining--;
    if (countdownSecondsRemaining > 0) {
      updateVoiceUi(true, countdownSecondsRemaining);
    }
  }, 1000);

  // Restart timeout
  const sttSettings = getSpeechSettings()?.stt || {};
  listeningTimeoutId = setTimeout(() => {
    console.log('🎤 Listening timeout reached');

    // Clear countdown
    if (countdownIntervalId) {
      clearInterval(countdownIntervalId);
      countdownIntervalId = null;
    }
    countdownSecondsRemaining = 0;

    // Check if we have any transcript when timeout occurs
    const currentText = (messageInput?.value || '').trim() || lastFinalTranscript;
    const autoSubmitEnabled = sttSettings.auto_submit !== false;

    if (currentText && autoSubmitEnabled) {
      console.log('🎤 Timeout with transcript - auto-submitting');
      stopVoiceInput(true).catch((err) => console.warn('Timeout auto-submit failed', err));
    } else {
      console.log('🎤 Timeout without valid transcript or auto-submit disabled');
      stopVoiceInput(false).catch((err) => console.warn('Timeout stop failed', err));
    }
  }, countdownTimeoutMs);
}

// Clear button double-click state
let lastClearClickTime = 0;
const CLEAR_DOUBLE_CLICK_TIMEOUT = 500; // 500ms window for double-click

const COPY_BUTTON_RESET_DELAY = 2000;

const SUPPORTED_PARAMETER_ALIAS_MAP = new Map([]);

function normalizeSupportedParameterValue(value) {
  if (typeof value !== 'string') {
    return null;
  }
  const token = value.trim().toLowerCase();
  if (!token) {
    return null;
  }
  return SUPPORTED_PARAMETER_ALIAS_MAP.get(token) ?? token;
}

function renderMessageContent(target, value) {
  if (!target) {
    return;
  }
  try {
    const html = renderMarkdown(value ?? '');
    target.innerHTML = html;
    enhanceCodeBlocks(target);
  } catch (error) {
    console.error('Markdown render failed', error);
    target.textContent = value ?? '';
  }
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    await navigator.clipboard.writeText(text);
    return;
  }

  if (typeof document === 'undefined' || typeof document.execCommand !== 'function') {
    throw new Error('Clipboard API unavailable');
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'absolute';
  textarea.style.left = '-9999px';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  const successful = document.execCommand('copy');
  textarea.remove();
  if (!successful) {
    throw new Error('Clipboard command failed');
  }
}

function enhanceCodeBlocks(container) {
  if (!container) {
    return;
  }

  const codeNodes = container.querySelectorAll('pre > code');
  codeNodes.forEach((codeNode) => {
    const preNode = codeNode.parentElement;
    if (!preNode || preNode.parentElement?.classList.contains('code-block')) {
      return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'code-block';

    preNode.replaceWith(wrapper);
    wrapper.appendChild(preNode);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'code-copy-button';
    button.textContent = 'Copy';
    button.setAttribute('aria-label', 'Copy code to clipboard');

    button.addEventListener('click', async () => {
      const codeText = codeNode.textContent || '';
      try {
        await copyTextToClipboard(codeText);
        button.textContent = 'Copied!';
        button.classList.add('code-copy-button--success');
      } catch (error) {
        console.warn('Copy failed', error);
        button.textContent = 'Failed';
        button.classList.add('code-copy-button--error');
      } finally {
        window.setTimeout(() => {
          button.textContent = 'Copy';
          button.classList.remove('code-copy-button--success', 'code-copy-button--error');
        }, COPY_BUTTON_RESET_DELAY);
      }
    });

    wrapper.insertBefore(button, preNode);
  });
}

function normalizeReasoningSegments(value) {
  if (value == null) {
    return [];
  }

  const segments = [];

  const append = (text, type) => {
    if (text == null) {
      return;
    }
    const normalizedText = String(text);
    if (!normalizedText) {
      return;
    }
    const normalizedType = typeof type === 'string' && type.trim() ? type.trim() : null;
    segments.push(
      normalizedType ? { text: normalizedText, type: normalizedType } : { text: normalizedText }
    );
  };

  const visit = (payload, contextType = null) => {
    if (payload == null) {
      return;
    }
    if (typeof payload === 'string' || typeof payload === 'number' || typeof payload === 'boolean') {
      append(payload, contextType);
      return;
    }
    if (Array.isArray(payload)) {
      payload.forEach((item) => visit(item, contextType));
      return;
    }
    if (isPlainObject(payload)) {
      const nextType =
        typeof payload.type === 'string' && payload.type.trim()
          ? payload.type.trim()
          : contextType;

      if (Object.prototype.hasOwnProperty.call(payload, 'text')) {
        append(payload.text, nextType);
      }

      for (const key of ['content', 'output', 'reasoning', 'message', 'details', 'explanation']) {
        if (Object.prototype.hasOwnProperty.call(payload, key)) {
          visit(payload[key], nextType);
        }
      }
      return;
    }

    append(payload, contextType);
  };

  visit(value, null);
  return segments;
}

function combineReasoningText(segments) {
  if (!Array.isArray(segments) || !segments.length) {
    return '';
  }

  let buffer = '';
  for (const segment of segments) {
    if (!segment || typeof segment.text !== 'string') {
      continue;
    }
    const fragment = segment.text;
    if (!fragment) {
      continue;
    }

    if (!buffer) {
      buffer = fragment;
      continue;
    }

    const needsSpace =
      !buffer.endsWith(' ') &&
      !buffer.endsWith('\n') &&
      !/^[,.;:!?)]/.test(fragment) &&
      !buffer.endsWith('(');

    buffer += needsSpace ? ` ${fragment}` : fragment;
  }

  return buffer
    .replace(/\s+([,.;:!?])/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

function renderReasoningSegments(container, segments) {
  if (!container) {
    return;
  }

  container.innerHTML = '';
  if (!Array.isArray(segments) || !segments.length) {
    return;
  }

  const combined = combineReasoningText(segments);
  if (!combined) {
    return;
  }

  const textNode = document.createElement('div');
  textNode.className = 'reasoning__text';
  textNode.textContent = combined;
  container.appendChild(textNode);
}

// Helper function to get supported parameters for a model
function getSupportedParametersForModel(modelId) {
  if (!modelId || !availableModels.length) {
    return [];
  }
  const model = availableModels.find(m => m.id === modelId);
  return model?.supported_parameters || [];
}

// Helper function to check if a parameter is supported by the current model
function isParameterSupported(parameterName, modelId) {
  const supportedParams = getSupportedParametersForModel(modelId);
  const normalizedParams = supportedParams.map(p => p.toLowerCase().trim());
  const normalizedParam = parameterName.toLowerCase().trim();

  // Handle common parameter name variations
  const parameterAliases = {
    'temperature': ['temperature'],
    'top_p': ['top_p', 'top-p'],
    'top_k': ['top_k', 'top-k'],
    'max_tokens': ['max_tokens', 'max-tokens', 'maxTokens'],
    'frequency_penalty': ['frequency_penalty', 'frequency-penalty'],
    'presence_penalty': ['presence_penalty', 'presence-penalty'],
    'repetition_penalty': ['repetition_penalty', 'repetition-penalty'],
    'stop': ['stop'],
    'seed': ['seed'],
    'tools': ['tools', 'functions', 'function_calling'],
    'parallel_tool_calls': ['parallel_tool_calls', 'parallel-tool-calls'],
    'safe_prompt': ['safe_prompt', 'safe-prompt'],
    'raw_mode': ['raw_mode', 'raw-mode'],
    'min_p': ['min_p', 'min-p'],
    'top_a': ['top_a', 'top-a']
  };

  const aliases = parameterAliases[normalizedParam] || [normalizedParam];
  return aliases.some(alias => normalizedParams.includes(alias));
}

const modelSettingsController = createModelSettingsController({
  modelSelect,
  openSettingsButton,
  settingsModal,
  settingsBackdrop,
  closeSettingsButton,
  loadModels,
  persistSelectedModel: (value) => persistSelectedModel(value),
  getAvailableModels: () => availableModels,
  getSupportedParametersForModel,
});

const speechSettingsController = createSpeechSettingsController({
  openButton: openSpeechSettingsButton,
  modal: speechSettingsModal,
  backdrop: speechSettingsBackdrop,
  closeButton: closeSpeechSettingsButton,
});

async function initialize() {
  restoreConversationFromStorage();
  await loadModels();
  if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
    window.addEventListener('storage', handleModelFilterChange);
    window.addEventListener('storage', handleSpeechSettingsStorageChange);
    window.addEventListener('speechsettings:updated', () => updateWakewordSubscription());
  }
  if (chatLog) {
    chatLog.addEventListener('scroll', handleChatLogScroll);
    scheduleScrollToBottom(true);
  }
  if (modelSelect) {
    modelSelect.addEventListener('change', handleModelSelectChange);
  }

  webSearchEnabled = readStoredWebSearchPreference();
  updateWebSearchButton();
  if (webSearchButton) {
    webSearchButton.addEventListener('click', handleWebSearchToggle);
  }

  form.addEventListener('submit', handleSubmit);
  if (messageInput) {
    messageInput.addEventListener('keydown', handleMessageInputKeyDown);
  }
  if (modelExplorerButton) {
    modelExplorerButton.addEventListener('click', handleModelExplorerClick);
  }
  if (stopButton) {
    stopButton.addEventListener('click', handleStopClick);
  }
  if (voiceButton) {
    voiceButton.addEventListener('click', handleVoiceClick);
  }
  clearButton.addEventListener('click', (event) => {
    event.preventDefault();

    const currentTime = Date.now();
    const timeSinceLastClick = currentTime - lastClearClickTime;

    // Check if this is a double-click (second click within timeout window)
    if (timeSinceLastClick < CLEAR_DOUBLE_CLICK_TIMEOUT) {
      // Double-click: clear both conversation and input field
      console.log('Clear button double-clicked - clearing conversation and input field');
      if (messageInput) {
        messageInput.value = '';
        messageInput.focus();
      }
      resetConversation(true).catch((error) => {
        console.error('Reset failed', error);
      });
      // Reset the timer to prevent triple-clicks from triggering again
      lastClearClickTime = 0;
    } else {
      // Single-click: only clear conversation
      console.log('Clear button single-clicked - clearing conversation only');
      resetConversation(true).catch((error) => {
        console.error('Reset failed', error);
      });
      // Record this click time for potential double-click detection
      lastClearClickTime = currentTime;
    }
  });

  initializeMetadataModal();
  modelSettingsController.initialize();
  speechSettingsController.initialize();
  updateWakewordSubscription();
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
  const metaContainer = fragment.querySelector('.meta');
  const metaLabel = metaContainer?.querySelector('.meta__label') || metaContainer;
  const defaultMetaLabel = options.meta || (role === 'user' ? 'You' : 'Assistant');
  if (metaLabel) {
    metaLabel.textContent = defaultMetaLabel;
  }

  const applyMetaLabel = (metadataCandidate) => {
    if (!metaLabel || options.meta) {
      return;
    }
    const label =
      metadataCandidate && typeof metadataCandidate.model === 'string'
        ? metadataCandidate.model.trim()
        : '';
    metaLabel.textContent = label || defaultMetaLabel;
  };

  const metadataButton = metaContainer?.querySelector('.metadata-button');
  if (metadataButton) {
    metadataButton.hidden = true;
    metadataButton.disabled = true;
    metadataButton.type = 'button';
    metadataButton.setAttribute('aria-label', 'View usage details');
    metadataButton.addEventListener('click', () => {
      if (article.__metadata) {
        openMetadataModal(article.__metadata);
      }
    });
  }

  const contentNode = fragment.querySelector('.content');
  renderMessageContent(contentNode, content);

  const reasoningDetails = fragment.querySelector('.reasoning');
  const reasoningContent = fragment.querySelector('.reasoning__content');
  const reasoningSummary = fragment.querySelector('.reasoning__summary');
  if (reasoningDetails) {
    reasoningDetails.hidden = true;
    reasoningDetails.open = false;
  }
  if (reasoningSummary) {
    reasoningSummary.textContent = 'Reasoning';
  }
  chatLog.appendChild(fragment);
  scheduleScrollToBottom(true);

  const setReasoning = (value, options = {}) => {
    const normalized = normalizeReasoningSegments(value);
    const combinedText = combineReasoningText(normalized);
    const existing = typeof article.__reasoning === 'string' ? article.__reasoning : '';
    if (!reasoningDetails || !reasoningContent) {
      return combinedText || (options.preserveExisting ? existing : '');
    }

    if (!combinedText) {
      if (options.preserveExisting && existing) {
        return existing;
      }
      reasoningDetails.hidden = true;
      reasoningDetails.open = false;
      reasoningContent.innerHTML = '';
      article.__reasoning = undefined;
      if (reasoningSummary) {
        reasoningSummary.textContent = 'Reasoning';
      }
      return '';
    }

    reasoningDetails.hidden = false;
    if (reasoningSummary) {
      reasoningSummary.textContent = 'Reasoning';
    }
    renderReasoningSegments(reasoningContent, normalized);
    article.__reasoning = combinedText;
    return combinedText;
  };

  const setMetadata = (metadata) => {
    const sanitized = sanitizeMetadata(metadata);
    applyMetaLabel(sanitized);

    if (!metadataButton) {
      if (sanitized && Object.prototype.hasOwnProperty.call(sanitized, 'reasoning')) {
        const combined = setReasoning(sanitized.reasoning, { preserveExisting: true });
        if (combined) {
          sanitized.reasoning = combined;
        } else {
          delete sanitized.reasoning;
        }
      }
      return sanitized;
    }

    const hasUsage = sanitized && isPlainObject(sanitized.usage);
    const hasGenerationId =
      sanitized && typeof sanitized.generation_id === 'string' && sanitized.generation_id.trim();
    let combinedReasoning = '';
    if (sanitized && Object.prototype.hasOwnProperty.call(sanitized, 'reasoning')) {
      combinedReasoning = setReasoning(sanitized.reasoning, { preserveExisting: true });
      if (combinedReasoning) {
        sanitized.reasoning = combinedReasoning;
      } else {
        delete sanitized.reasoning;
      }
    }

    if (sanitized && (hasUsage || hasGenerationId)) {
      article.__metadata = sanitized;
      metadataButton.hidden = false;
      metadataButton.disabled = false;
    } else {
      article.__metadata = undefined;
      metadataButton.hidden = true;
      metadataButton.disabled = true;
    }
    return sanitized;
  };

  if (options.metadata) {
    setMetadata(options.metadata);
  } else if (metadataButton) {
    metadataButton.hidden = true;
    metadataButton.disabled = true;
  }

  if (options.reasoning) {
    const combined = setReasoning(options.reasoning);
    if (options.metadata && typeof options.metadata === 'object') {
      options.metadata.reasoning = combined;
    }
  }

  return {
    element: article,
    setContent: (value) => {
      renderMessageContent(contentNode, value);
      scheduleScrollToBottom();
    },
    setMetadata,
    setReasoning,
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

  // Check if conversation mode should be activated for manual submissions
  const speechSettings = getSpeechSettings();
  const conversationEnabled = speechSettings?.conversation?.enabled === true;
  if (conversationEnabled) {
    conversationModeActive = true;
    console.log('🎤 Conversation mode: Manual submission with conversation mode enabled');
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

function handleMessageInputKeyDown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) {
    return;
  }

  event.preventDefault();

  if (isStreaming) {
    return;
  }

  if (typeof form.requestSubmit === 'function') {
    form.requestSubmit();
  } else {
    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  }
}

function handleModelExplorerClick(event) {
  if (event) {
    event.preventDefault();
  }
  window.location.href = '/settings';
}

function handleStopClick(event) {
  if (event) {
    event.preventDefault();
  }
  if (!currentStreamAbortController || stopRequested) {
    return;
  }

  stopRequested = true;

  // Reset conversation mode when user manually stops streaming
  if (conversationModeActive) {
    console.log('🎤 Conversation mode: User manually stopped streaming, disabling auto-restart');
    conversationModeActive = false;
  }

  if (stopButton) {
    stopButton.disabled = true;
    stopButton.textContent = 'Stopping...';
  }

  try {
    currentStreamAbortController.abort();
  } catch (error) {
    console.warn('Failed to cancel the active stream', error);
  }
}

function handleChatLogScroll() {
  if (!chatLog) {
    return;
  }

  const distanceFromBottom = chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight;
  isChatLogPinnedToBottom = distanceFromBottom <= 48;
}

function scheduleScrollToBottom(force = false) {
  if (!chatLog) {
    return;
  }

  if (force) {
    isChatLogPinnedToBottom = true;
  } else if (!isChatLogPinnedToBottom) {
    return;
  }

  if (pendingScrollAnimationFrame != null) {
    window.cancelAnimationFrame(pendingScrollAnimationFrame);
  }

  pendingScrollAnimationFrame = window.requestAnimationFrame(() => {
    chatLog.scrollTop = chatLog.scrollHeight;
    pendingScrollAnimationFrame = null;
  });
}

function initializeMetadataModal() {
  if (!metadataModal) {
    return;
  }

  const closeTargets = metadataModal.querySelectorAll('[data-close-metadata]');
  closeTargets.forEach((element) => {
    element.addEventListener('click', () => {
      closeMetadataModal();
    });
  });
}

function openMetadataModal(metadata) {
  if (!metadataModal) {
    return;
  }

  const sanitized = sanitizeMetadata(metadata);
  activeMetadataRecord = sanitized;
  metadataMoreInfoState = createMoreInfoState(sanitized);
  renderMetadataModalContent(activeMetadataRecord);

  if (!metadataModalVisible) {
    metadataModal.classList.add('is-visible');
    metadataModal.setAttribute('aria-hidden', 'false');
    metadataModalVisible = true;
    updateBodyModalClass();
    document.addEventListener('keydown', handleMetadataModalKeydown);

    if (closeMetadataButton) {
      window.setTimeout(() => {
        closeMetadataButton.focus();
      }, 0);
    }
  }
}

function closeMetadataModal() {
  if (!metadataModal || !metadataModalVisible) {
    return;
  }

  metadataModal.classList.remove('is-visible');
  metadataModal.setAttribute('aria-hidden', 'true');
  metadataModalVisible = false;
  document.removeEventListener('keydown', handleMetadataModalKeydown);
  updateBodyModalClass();
  activeMetadataRecord = null;
  metadataMoreInfoState = {
    generationId: null,
    expanded: false,
    loading: false,
    data: null,
    error: null,
  };
}

function handleMetadataModalKeydown(event) {
  if (event.key === 'Escape') {
    closeMetadataModal();
  }
}

function renderMetadataModalContent(metadata) {
  if (!metadataContent) {
    return;
  }

  metadataContent.innerHTML = '';

  if (!isPlainObject(metadata) || Object.keys(metadata).length === 0) {
    appendUsageUnavailableMessage();
    renderMoreInfoSection(null);
    return;
  }

  const summaryEntries = [];
  if (typeof metadata.model === 'string' && metadata.model.trim()) {
    summaryEntries.push(['Model', metadata.model.trim()]);
  }
  if (metadata.finish_reason) {
    summaryEntries.push(['Finish reason', formatMetadataValue(metadata.finish_reason)]);
  }
  if (summaryEntries.length) {
    appendMetadataSection('Completion Summary', summaryEntries);
  }

  let hasUsageSections = false;
  if (isPlainObject(metadata.usage)) {
    const usage = metadata.usage;

    const usageEntries = [];
    if (typeof usage.prompt_tokens === 'number') {
      usageEntries.push(['Prompt tokens', formatMetadataValue(usage.prompt_tokens)]);
    }
    if (typeof usage.completion_tokens === 'number') {
      usageEntries.push(['Completion tokens', formatMetadataValue(usage.completion_tokens)]);
    }
    if (typeof usage.total_tokens === 'number') {
      usageEntries.push(['Total tokens', formatMetadataValue(usage.total_tokens)]);
    }
    if (typeof usage.cost === 'number') {
      const formattedCost = formatUsageCost(usage.cost);
      if (formattedCost != null) {
        usageEntries.push(['Cost (credits)', formattedCost]);
      }
    }
    if (usageEntries.length) {
      appendMetadataSection('Usage', usageEntries);
      hasUsageSections = true;
    }

    const breakdownEntries = [];
    const promptDetails = isPlainObject(usage.prompt_tokens_details)
      ? usage.prompt_tokens_details
      : null;
    if (promptDetails) {
      for (const [key, value] of Object.entries(promptDetails)) {
        if (typeof value === 'number') {
          breakdownEntries.push([
            `Prompt ${formatMetadataLabel(key)}`,
            formatMetadataValue(value),
          ]);
        }
      }
    }

    const completionDetails = isPlainObject(usage.completion_tokens_details)
      ? usage.completion_tokens_details
      : null;
    if (completionDetails) {
      for (const [key, value] of Object.entries(completionDetails)) {
        if (typeof value === 'number') {
          breakdownEntries.push([
            `Completion ${formatMetadataLabel(key)}`,
            formatMetadataValue(value),
          ]);
        }
      }
    }

    if (breakdownEntries.length) {
      appendMetadataSection('Usage Breakdown', breakdownEntries);
      hasUsageSections = true;
    }

    const costDetails = isPlainObject(usage.cost_details) ? usage.cost_details : null;
    if (costDetails) {
      const costEntries = [];
      for (const [key, value] of Object.entries(costDetails)) {
        if (typeof value === 'number') {
          const formatted = formatUsageCost(value);
          if (formatted != null) {
            costEntries.push([formatMetadataLabel(key), formatted]);
            continue;
          }
        }
        costEntries.push([formatMetadataLabel(key), formatMetadataValue(value)]);
      }
      if (costEntries.length) {
        appendMetadataSection('Cost Details', costEntries);
        hasUsageSections = true;
      }
    }
  }

  if (!hasUsageSections) {
    appendUsageUnavailableMessage();
  }

  if (isPlainObject(metadata.routing)) {
    const routingEntries = [];
    for (const [key, value] of Object.entries(metadata.routing)) {
      routingEntries.push([formatMetadataLabel(key), formatMetadataValue(value)]);
    }
    if (routingEntries.length) {
      appendMetadataSection('Routing', routingEntries);
    }
  }

  if (isPlainObject(metadata.meta)) {
    const metaEntries = flattenMetadataObject(metadata.meta);
    if (metaEntries.length) {
      appendMetadataSection('Meta', metaEntries);
    }
  }

  renderMoreInfoSection(metadata);
}

function appendMetadataSection(title, entries, target = metadataContent) {
  const root = target;
  if (!root || !entries.length) {
    return;
  }

  const heading = document.createElement('h3');
  heading.className = 'metadata-section-title';
  heading.textContent = title;
  root.appendChild(heading);

  for (const [label, value] of entries) {
    const row = document.createElement('div');
    row.className = 'metadata-row';

    const labelEl = document.createElement('span');
    labelEl.className = 'metadata-row__label';
    labelEl.textContent = label;

    const valueEl = document.createElement('span');
    valueEl.className = 'metadata-row__value';
    valueEl.textContent = value;

    row.append(labelEl, valueEl);
    root.appendChild(row);
  }
}

function renderMoreInfoSection(metadata) {
  if (!metadataContent) {
    return;
  }

  const container = document.createElement('div');
  container.className = 'metadata-more-info';
  metadataContent.appendChild(container);

  const generationId = metadataMoreInfoState.generationId;
  if (!generationId) {
    const note = document.createElement('p');
    note.className = 'metadata-empty';
    note.textContent = 'Additional generation details are unavailable.';
    container.appendChild(note);
    return;
  }

  const actions = document.createElement('div');
  actions.className = 'metadata-more-info__actions';

  const toggleButton = document.createElement('button');
  toggleButton.type = 'button';
  toggleButton.className = 'metadata-more-info__button';
  toggleButton.textContent = metadataMoreInfoState.expanded ? 'Hide more info' : 'More info';
  toggleButton.addEventListener('click', handleMetadataMoreInfoToggle);
  actions.appendChild(toggleButton);

  container.appendChild(actions);

  if (!metadataMoreInfoState.expanded) {
    return;
  }

  if (metadataMoreInfoState.loading) {
    const status = document.createElement('p');
    status.className = 'metadata-more-info__status';
    status.textContent = 'Loading more details…';
    container.appendChild(status);
    return;
  }

  if (metadataMoreInfoState.error) {
    const error = document.createElement('p');
    error.className = 'metadata-more-info__error';
    error.textContent = metadataMoreInfoState.error;
    container.appendChild(error);
    return;
  }

  const detailEntries = buildGenerationDetailEntries(metadataMoreInfoState.data);
  if (detailEntries.length) {
    appendMetadataSection('Generation Details', detailEntries, container);
  } else {
    const empty = document.createElement('p');
    empty.className = 'metadata-empty';
    empty.textContent = 'No additional generation data available.';
    container.appendChild(empty);
  }
}

function appendUsageUnavailableMessage(target = metadataContent) {
  if (!target) {
    return;
  }
  const empty = document.createElement('p');
  empty.className = 'metadata-empty';
  empty.textContent = 'Usage details are not available for this reply.';
  target.appendChild(empty);
}

async function handleMetadataMoreInfoToggle(event) {
  if (event) {
    event.preventDefault();
  }

  const generationId = metadataMoreInfoState.generationId;
  if (!generationId) {
    return;
  }

  const shouldExpand = !metadataMoreInfoState.expanded;
  metadataMoreInfoState.expanded = shouldExpand;
  metadataMoreInfoState.error = null;

  if (!shouldExpand) {
    renderMetadataModalContent(activeMetadataRecord);
    return;
  }

  const cached = generationDetailsCache.get(generationId);
  if (cached) {
    metadataMoreInfoState.data = cached;
    metadataMoreInfoState.loading = false;
    renderMetadataModalContent(activeMetadataRecord);
    return;
  }

  metadataMoreInfoState.loading = true;
  metadataMoreInfoState.data = null;
  renderMetadataModalContent(activeMetadataRecord);

  try {
    const payload = await fetchGenerationDetails(generationId);
    metadataMoreInfoState.data = payload;
    generationDetailsCache.set(generationId, payload);
  } catch (error) {
    metadataMoreInfoState.error =
      error instanceof Error ? error.message : 'Failed to load generation details.';
  } finally {
    metadataMoreInfoState.loading = false;
    renderMetadataModalContent(activeMetadataRecord);
  }
}

function createMoreInfoState(metadata) {
  const generationId =
    metadata && typeof metadata.generation_id === 'string'
      ? metadata.generation_id.trim()
      : '';
  const normalizedId = generationId || null;
  const cached = normalizedId ? generationDetailsCache.get(normalizedId) ?? null : null;

  return {
    generationId: normalizedId,
    expanded: false,
    loading: false,
    data: cached,
    error: null,
  };
}

async function fetchGenerationDetails(generationId) {
  const response = await fetch(`/api/chat/generation/${encodeURIComponent(generationId)}`, {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    let message = `Failed to load generation details (${response.status})`;
    try {
      const body = await response.json();
      if (body) {
        if (typeof body.detail === 'string') {
          message = body.detail;
        } else if (typeof body.error === 'string') {
          message = body.error;
        }
      }
    } catch (_) {
      // ignore parsing errors, fall back to default message
    }
    throw new Error(message);
  }

  try {
    return await response.json();
  } catch (error) {
    throw new Error('Received an invalid response when loading generation details.');
  }
}

function buildGenerationDetailEntries(payload) {
  const data = normalizeGenerationData(payload);
  if (!isPlainObject(data)) {
    return [];
  }

  const orderedKeys = [
    'id',
    'model',
    'provider_name',
    'origin',
    'created_at',
    'finish_reason',
    'native_finish_reason',
    'streamed',
    'cancelled',
    'latency',
    'moderation_latency',
    'generation_time',
    'total_cost',
    'upstream_inference_cost',
    'cache_discount',
    'usage',
    'tokens_prompt',
    'tokens_completion',
    'native_tokens_prompt',
    'native_tokens_completion',
    'native_tokens_reasoning',
    'num_media_prompt',
    'num_media_completion',
    'num_search_results',
    'app_id',
    'upstream_id',
    'is_byok',
  ];

  const costKeys = new Set(['total_cost', 'cache_discount', 'upstream_inference_cost']);

  const entries = [];
  for (const key of orderedKeys) {
    if (!(key in data)) {
      continue;
    }
    const value = data[key];
    if (value == null || value === '') {
      continue;
    }

    let formatted;
    if (typeof value === 'number' && costKeys.has(key)) {
      formatted = formatUsageCost(value) ?? formatMetadataValue(value);
    } else {
      formatted = formatMetadataValue(value);
    }

    entries.push([formatMetadataLabel(key), formatted]);
  }

  return entries;
}

function normalizeGenerationData(payload) {
  if (isPlainObject(payload?.data)) {
    return payload.data;
  }
  if (isPlainObject(payload)) {
    return payload;
  }
  return null;
}

async function requestStream(latestUserMessage) {
  isStreaming = true;
  stopRequested = false;
  messageInput.disabled = true;
  modelSelect.disabled = true;
  if (voiceButton) {
    voiceButton.hidden = true;
    voiceButton.setAttribute('aria-hidden', 'true');
  }

  if (stopButton) {
    stopButton.hidden = false;
    stopButton.disabled = false;
    stopButton.textContent = 'Stop';
  }

  const controller = new AbortController();
  currentStreamAbortController = controller;

  let assistantText = '';
  let pendingMetadata = null;
  let assistantSaved = false;
  const reasoningSegments = [];
  const reasoningSeen = new Set();
  let reasoningUpdated = false;
  let reasoningCombinedText = '';
  const assistantMessage = addMessage('assistant', '');

  const applyStreamingReasoning = (value) => {
    if (!assistantMessage || typeof assistantMessage.setReasoning !== 'function') {
      return;
    }
    const normalized = normalizeReasoningSegments(value);
    let changed = false;

    for (const segment of normalized) {
      if (!segment || typeof segment.text !== 'string') {
        continue;
      }
      const text = segment.text.trim();
      if (!text) {
        continue;
      }
      const type = typeof segment.type === 'string' ? segment.type.trim() : '';
      const key = `${type}::${text}`;
      if (reasoningSeen.has(key)) {
        continue;
      }
      reasoningSeen.add(key);
      reasoningSegments.push(type ? { text, type } : { text });
      changed = true;
    }

    if (!changed) {
      return;
    }

    reasoningUpdated = true;
    const snapshot = reasoningSegments.map((segment) => ({ ...segment }));
    const combined = assistantMessage.setReasoning(snapshot);
    if (combined) {
      reasoningCombinedText = combined;
      if (pendingMetadata && isPlainObject(pendingMetadata)) {
        pendingMetadata.reasoning = combined;
      }
    }
  };

  try {
    const model = resolveModelForRequest(modelSelect.value || 'openrouter/auto');
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

    if (webSearchEnabled) {
      payload.plugins = [buildWebSearchPluginPayload()];
    }

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
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

        if (event.event === 'metadata') {
          try {
            const metadataPayload = JSON.parse(event.data);
            const sanitized = typeof assistantMessage?.setMetadata === 'function'
              ? assistantMessage.setMetadata(metadataPayload)
              : sanitizeMetadata(metadataPayload);
            pendingMetadata = sanitized;
          } catch (error) {
            console.warn('Failed to parse metadata payload', error);
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
            if (Object.prototype.hasOwnProperty.call(delta, 'reasoning')) {
              applyStreamingReasoning(delta.reasoning);
            }
            if (typeof delta.content === 'string') {
              assistantText += delta.content;
              assistantMessage.setContent(assistantText);
            }
          }

          if (Object.prototype.hasOwnProperty.call(parsed, 'reasoning')) {
            applyStreamingReasoning(parsed.reasoning);
          }

          const messageReasoning = parsed.message && parsed.message.reasoning;
          if (typeof messageReasoning !== 'undefined') {
            applyStreamingReasoning(messageReasoning);
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
                  if (Object.prototype.hasOwnProperty.call(delta, 'reasoning')) {
                    applyStreamingReasoning(delta.reasoning);
                  }
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
      const entry = { role: 'assistant', content: assistantText };
      if (pendingMetadata) {
        entry.metadata = pendingMetadata;
      } else if (reasoningUpdated && reasoningCombinedText) {
        entry.metadata = {
          reasoning: reasoningCombinedText,
        };
      }
      conversation.push(entry);
      persistConversationState();
      assistantSaved = true;
    }
  } catch (error) {
    if (stopRequested || (error && error.name === 'AbortError')) {
      if (!assistantText.trim()) {
        assistantMessage.setContent('Generation stopped.');
      } else {
        assistantMessage.setContent(assistantText);
      }

      if (assistantText.trim() && !assistantSaved) {
        const entry = { role: 'assistant', content: assistantText };
        if (pendingMetadata) {
          entry.metadata = pendingMetadata;
        }
        conversation.push(entry);
        persistConversationState();
        assistantSaved = true;
      }
      return;
    }

    const message = error instanceof Error ? error.message : 'Unknown error';
    assistantMessage.setContent(`Error: ${message}`);
    assistantMessage.element.classList.add('error');
    throw error;
  } finally {
    messageInput.disabled = false;
    modelSelect.disabled = false;
    if (stopButton) {
      stopButton.hidden = true;
      stopButton.disabled = false;
      stopButton.textContent = 'Stop';
    }
    if (voiceButton) {
      voiceButton.hidden = false;
      voiceButton.setAttribute('aria-hidden', 'false');
    }
    currentStreamAbortController = null;
    stopRequested = false;
    isStreaming = false;

    // Handle conversation mode auto-restart
    const shouldRestartConversation = conversationModeActive && !stopRequested;
    if (shouldRestartConversation) {
      console.log('🎤 Conversation mode: AI response complete, restarting voice input...');
      // Small delay to ensure UI updates and focus, then restart listening
      setTimeout(() => {
        if (!isRecording && !isStreaming) {
          startVoiceInput().catch((err) => {
            console.error('🎤 Conversation mode auto-restart failed:', err);
            conversationModeActive = false; // Reset on failure
          });
        }
      }, 500);
    } else {
      conversationModeActive = false; // Reset conversation mode if not restarting
    }

    messageInput.focus();
  }
}

function handleVoiceClick(event) {
  if (event) {
    event.preventDefault();
  }
  console.log('🎤 handleVoiceClick called', {
    isStreaming,
    isRecording,
    source: event ? 'manual' : 'wakeword'
  });
  if (isStreaming) {
    console.log('🎤 Skipping voice input - already streaming');
    return; // Don't start STT while model is responding
  }
  if (isRecording) {
    // When manually stopping recording, always submit (ignore auto_submit setting)
    // because the user explicitly wants to stop and send the message
    console.log('🎤 Manually stopping current recording with submit=true');
    stopVoiceInput(true).catch((err) => console.warn('Voice stop failed', err));
  } else {
    console.log('🎤 Starting new voice input');
    startVoiceInput().catch((err) => {
      console.error('Voice start failed', err);
      updateVoiceUi(false);
    });
  }
}

async function startVoiceInput() {
  if (isRecording) return;

  lastFinalTranscript = '';
  voiceInputPreviousValue = messageInput ? messageInput.value : '';

  // Check if conversation mode is enabled for auto-restart after response
  const speechSettings = getSpeechSettings();
  const conversationEnabled = speechSettings?.conversation?.enabled === true;

  // Set initial UI state - countdown will be updated later if conversation mode is enabled
  updateVoiceUi(true);

  if (conversationEnabled) {
    conversationModeActive = true;
    console.log('🎤 Conversation mode active - will auto-restart after AI response');
  }

  let token;
  try {
    const resp = await fetch('/api/stt/deepgram/token', { method: 'POST', headers: { 'Accept': 'application/json' } });
    if (!resp.ok) {
      let reason = `${resp.status}`;
      try { const b = await resp.json(); reason = b?.detail || reason; } catch (_) { }
      throw new Error(`Token request failed: ${reason}`);
    }
    const data = await resp.json();
    token = data.access_token;
    if (!token) throw new Error('Missing Deepgram token');
  } catch (err) {
    updateVoiceUi(false);
    // Clear timeout and countdown if setup fails
    if (listeningTimeoutId) {
      clearTimeout(listeningTimeoutId);
      listeningTimeoutId = null;
    }
    if (countdownIntervalId) {
      clearInterval(countdownIntervalId);
      countdownIntervalId = null;
    }
    countdownSecondsRemaining = 0;
    countdownTimeoutMs = 0;
    throw err;
  }

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  } catch (err) {
    updateVoiceUi(false);
    // Clear timeout and countdown if microphone setup fails
    if (listeningTimeoutId) {
      clearTimeout(listeningTimeoutId);
      listeningTimeoutId = null;
    }
    if (countdownIntervalId) {
      clearInterval(countdownIntervalId);
      countdownIntervalId = null;
    }
    countdownSecondsRemaining = 0;
    countdownTimeoutMs = 0;
    throw new Error('Microphone permission denied or unavailable');
  }

  // Pick a recorder mime first so we can set matching Deepgram encoding
  const recorderMimeCandidates = [
    'audio/ogg;codecs=opus',
    'audio/webm;codecs=opus',
    'audio/webm',
  ];
  const selectedMime = recorderMimeCandidates.find((t) => {
    try { return MediaRecorder.isTypeSupported(t); } catch { return false; }
  });

  // Deepgram expects the audio codec; keep encoding=opus regardless of container
  const encoding = 'opus';

  const sttSettings = getSpeechSettings()?.stt || {};
  const dgModel = typeof sttSettings.model === 'string' && sttSettings.model ? sttSettings.model : 'nova-3';
  const interim = sttSettings.interim_results !== false;
  const vad = sttSettings.vad_events !== false;
  const utteranceMs = Number.isFinite(Number(sttSettings.utterance_end_ms)) ? Number(sttSettings.utterance_end_ms) : 1000;
  const endpointMs = Number.isFinite(Number(sttSettings.endpointing)) ? Number(sttSettings.endpointing) : 1000;

  const params = new URLSearchParams({
    model: dgModel,
    interim_results: String(interim),
    smart_format: 'true',
    vad_events: String(vad),
    utterance_end_ms: String(utteranceMs),
    endpointing: String(endpointMs),
    encoding,
  });

  const url = `wss://api.deepgram.com/v1/listen?${params.toString()}`;
  const isJwt = typeof token === 'string' && token.split('.').length >= 3;
  const protocols = isJwt ? ['Bearer', token] : ['token', token];
  dgSocket = new WebSocket(url, protocols);

  dgSocket.addEventListener('open', () => {
    const mimeType = selectedMime;
    try {
      mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);
    } catch (err) {
      console.warn('MediaRecorder init failed, stopping voice input', err);
      stopVoiceInput(false);
      return;
    }

    mediaRecorder.addEventListener('dataavailable', async (ev) => {
      if (!ev.data || ev.data.size === 0) return;
      try {
        const buf = await ev.data.arrayBuffer();
        if (dgSocket && dgSocket.readyState === WebSocket.OPEN) {
          dgSocket.send(buf);
        }
      } catch (err) {
        console.warn('Chunk send failed', err);
      }
    });

    mediaRecorder.addEventListener('stop', () => {
      // Signal end of stream
      try { dgSocket?.send(new Uint8Array()); } catch (_) { }
    });

    mediaRecorder.start(250);

    // Start listening timeout only if conversation mode is enabled
    const conversationEnabled = speechSettings?.conversation?.enabled === true;
    if (conversationEnabled) {
      const sttSettings = getSpeechSettings()?.stt || {};
      const timeoutMs = Number.isFinite(Number(sttSettings.timeout_ms)) ? Number(sttSettings.timeout_ms) : 5000;
      console.log(`🎤 Conversation mode enabled - countdown will start when no speech detected: ${timeoutMs}ms`);

      // Store timeout value for resetting
      countdownTimeoutMs = timeoutMs;

      // Initialize countdown but don't start interval yet (wait for silence)
      countdownSecondsRemaining = Math.ceil(timeoutMs / 1000);
      updateVoiceUi(true, countdownSecondsRemaining);

      // Start initial timeout - this will be reset when speech is detected
      listeningTimeoutId = setTimeout(() => {
        console.log('🎤 Listening timeout reached');

        // Clear countdown
        if (countdownIntervalId) {
          clearInterval(countdownIntervalId);
          countdownIntervalId = null;
        }
        countdownSecondsRemaining = 0;

        // Check if we have any transcript when timeout occurs
        const currentText = (messageInput?.value || '').trim() || lastFinalTranscript;
        const autoSubmitEnabled = sttSettings.auto_submit !== false;

        if (currentText && autoSubmitEnabled) {
          console.log('🎤 Timeout with transcript - auto-submitting');
          stopVoiceInput(true).catch((err) => console.warn('Timeout auto-submit failed', err));
        } else {
          console.log('🎤 Timeout without valid transcript or auto-submit disabled');
          stopVoiceInput(false).catch((err) => console.warn('Timeout stop failed', err));
        }
      }, timeoutMs);

      // Start countdown interval
      countdownIntervalId = setInterval(() => {
        countdownSecondsRemaining--;
        if (countdownSecondsRemaining > 0) {
          updateVoiceUi(true, countdownSecondsRemaining);
        }
      }, 1000);
    } else {
      console.log('🎤 Conversation mode disabled - no listening timeout set');
      countdownTimeoutMs = 0;
    }
  });

  dgSocket.addEventListener('message', (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === 'SpeechStarted') {
        // Reset countdown when speech is detected
        resetCountdown();
        return;
      }
      const alt = msg?.channel?.alternatives?.[0];
      const transcript = alt?.transcript || '';
      const isFinal = Boolean(msg?.is_final);
      const speechFinal = Boolean(msg?.speech_final);

      if (transcript) {
        // Reset countdown when we receive any transcript (interim or final)
        resetCountdown();

        if (messageInput) {
          messageInput.value = transcript;
        }
        if (isFinal) {
          lastFinalTranscript = transcript;
        }
      }

      if (speechFinal) {
        // End of utterance detected
        const sttSettings = getSpeechSettings()?.stt || {};
        const autoSubmit = sttSettings.auto_submit !== false; // Default to true
        console.log('🎤 speechFinal detected', { autoSubmit });
        stopVoiceInput(autoSubmit).catch((err) => console.warn('Auto stop failed', err));
      }
    } catch (err) {
      // Ignore non-JSON pings/keepalives
    }
  });

  dgSocket.addEventListener('error', (err) => {
    console.warn('Deepgram socket error', err);
    stopVoiceInput(false).catch(() => { });
  });

  dgSocket.addEventListener('close', (ev) => {
    // Code 1005: "No Status Received" - this is normal and indicates a clean close
    // Other common codes: 1000 (normal), 1001 (going away), 1006 (abnormal)
    const isNormalClose = ev.code === 1005 || ev.code === 1000 || ev.code === 1001;
    if (isNormalClose) {
      console.log('Deepgram socket closed normally', { code: ev.code, reason: ev.reason });
    } else {
      console.warn('Deepgram socket closed', { code: ev.code, reason: ev.reason });
    }
    updateVoiceUi(false);
  });
  dgSocket.addEventListener('close', () => {
    updateVoiceUi(false);
  });
}

async function stopVoiceInput(submit) {
  if (!isRecording) return;
  isRecording = false;

  // Clear listening timeout and countdown
  if (listeningTimeoutId) {
    clearTimeout(listeningTimeoutId);
    listeningTimeoutId = null;
    console.log('🎤 Cleared listening timeout');
  }
  if (countdownIntervalId) {
    clearInterval(countdownIntervalId);
    countdownIntervalId = null;
    console.log('🎤 Cleared countdown interval');
  }
  countdownSecondsRemaining = 0;
  countdownTimeoutMs = 0;

  const sttSettings = getSpeechSettings()?.stt || {};
  const autoSubmitEnabled = sttSettings.auto_submit !== false;
  console.log('🎤 stopVoiceInput called', {
    submit,
    autoSubmitEnabled,
    messageInputValue: messageInput?.value,
    lastFinalTranscript
  });

  try { mediaRecorder?.stop(); } catch (_) { }
  try { mediaStream?.getTracks().forEach((t) => t.stop()); } catch (_) { }
  mediaRecorder = null;
  mediaStream = null;

  try { dgSocket?.close(); } catch (_) { }
  dgSocket = null;

  updateVoiceUi(false);

  if (submit) {
    const text = (messageInput?.value || '').trim() || lastFinalTranscript;
    console.log('🎤 Processing submit', { text, isStreaming, autoSubmitEnabled });
    if (text) {
      messageInput.value = text;
      if (!isStreaming) {
        console.log('🎤 Submitting form with text:', text);
        // Keep conversationModeActive true since we're submitting and expecting a response
        if (typeof form.requestSubmit === 'function') {
          form.requestSubmit();
        } else {
          form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
        }
      } else {
        console.log('🎤 Skipping submit - already streaming');
        conversationModeActive = false; // Reset if we can't submit
      }
    } else {
      console.log('🎤 No text to submit, restoring previous value');
      conversationModeActive = false; // Reset if no text to submit
      // Restore previous typed value if no transcript
      if (messageInput) messageInput.value = voiceInputPreviousValue;
    }
  } else {
    console.log('🎤 Voice input stopped without submit (auto-submit disabled or manual stop)');
    // When not submitting, check if we should reset conversation mode
    // Only keep it active if auto-submit is disabled but we have text that might be submitted later
    const text = (messageInput?.value || '').trim() || lastFinalTranscript;
    if (text && messageInput) {
      messageInput.value = text;
      console.log('🎤 Transcript preserved in input field for manual submission:', text);
      // Keep conversation mode active since user might still submit manually
    } else {
      conversationModeActive = false; // Reset if no text or manual stop without intent to submit
    }
  }
}

function updateVoiceUi(recording, countdownSeconds = null) {
  isRecording = recording;
  if (!voiceButton) return;
  voiceButton.classList.toggle('is-active', recording);
  voiceButton.setAttribute('aria-pressed', recording ? 'true' : 'false');

  if (recording && countdownSeconds !== null && countdownSeconds > 0) {
    // Show countdown instead of mic icon
    voiceButton.innerHTML = `<span style="font-weight: bold; font-size: 16px;">${countdownSeconds}</span>`;
    voiceButton.setAttribute('aria-label', `Stop voice input (${countdownSeconds}s remaining)`);
  } else if (recording) {
    // Show mic icon when recording without countdown
    voiceButton.innerHTML = '<img src="/static/icons/mic_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg" alt="" width="24" height="24" />';
    voiceButton.setAttribute('aria-label', 'Stop voice input');
  } else {
    // Show mic icon when not recording
    voiceButton.innerHTML = '<img src="/static/icons/mic_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg" alt="" width="24" height="24" />';
    voiceButton.setAttribute('aria-label', 'Start voice input');
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
  const friendlyMessage =
    typeof details.message === 'string' && details.message.trim()
      ? details.message.trim()
      : null;

  let text;
  if (friendlyMessage) {
    text = friendlyMessage;
  } else {
    text = `[tool] ${details.name} ${status}`;
  }
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

  // Debug: show what rich data we now have available
  if (availableModels.length > 0) {
    const sampleModel = availableModels[0];
    console.debug('[models] FULL model data preserved:', {
      // Basic fields
      id: sampleModel.id,
      name: sampleModel.name,
      created: sampleModel.created,
      description: sampleModel.description?.slice(0, 100) + '...',
      canonical_slug: sampleModel.canonical_slug,
      hugging_face_id: sampleModel.hugging_face_id,

      // Capabilities
      context_length: sampleModel.context_length,
      architecture: sampleModel.architecture,
      top_provider: sampleModel.top_provider,
      per_request_limits: sampleModel.per_request_limits,

      // Pricing
      pricing: sampleModel.pricing,
      prompt_price: sampleModel.prompt_price,
      prompt_price_per_million: sampleModel.prompt_price_per_million,

      // Parameters & Support
      supported_parameters: sampleModel.supported_parameters,
      supported_parameters_normalized: sampleModel.supported_parameters_normalized,
      supports_tools: sampleModel.supports_tools,

      // Backend enrichments
      input_modalities: sampleModel.input_modalities,
      output_modalities: sampleModel.output_modalities,
      series: sampleModel.series,
      provider_prefix: sampleModel.provider_prefix,

      // UI field
      label: sampleModel.label
    });

    console.debug('[models] Total fields preserved:', Object.keys(sampleModel).length);
    console.debug('[models] All field names:', Object.keys(sampleModel).sort());
  }

  // Make models available for inspection in browser console
  window.debugModels = availableModels;  // Populate the selector with the latest normalized set
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
    option.dataset.supportsTools = String(model.supports_tools);
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
      const candidate = data.filters;
      const rawSupportedParameters = Array.isArray(candidate.supported_parameters_normalized)
        ? candidate.supported_parameters_normalized
        : typeof candidate.supported_parameters_normalized === 'string'
          ? [candidate.supported_parameters_normalized]
          : null;
      if (rawSupportedParameters) {
        const normalizedParams = rawSupportedParameters
          .map(normalizeSupportedParameterValue)
          .filter(Boolean);
        if (normalizedParams.length) {
          filters = {
            ...candidate,
            supported_parameters_normalized: normalizedParams,
          };
        } else {
          const { supported_parameters_normalized: _, ...rest } = candidate;
          filters = { ...rest };
        }
      } else {
        filters = candidate;
      }
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
    const normalizedParams = data.supportedParameters
      .map(normalizeSupportedParameterValue)
      .filter(Boolean);
    if (normalizedParams.length) {
      filters.supported_parameters_normalized = normalizedParams;
    }
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

function handleWebSearchToggle(event) {
  if (event) {
    event.preventDefault();
  }
  webSearchEnabled = !webSearchEnabled;
  persistWebSearchPreference(webSearchEnabled);
  updateWebSearchButton();
}

function updateWebSearchButton() {
  if (!webSearchButton) {
    return;
  }
  const enabled = Boolean(webSearchEnabled);
  const label = enabled ? 'Web search on' : 'Web search off';
  webSearchButton.textContent = label;
  webSearchButton.setAttribute('aria-pressed', enabled ? 'true' : 'false');
  webSearchButton.classList.toggle('is-active', enabled);
  webSearchButton.title = enabled
    ? 'Web search enabled. Responses may include live citations.'
    : 'Web search disabled. Responses use cached knowledge only.';
}

function buildWebSearchPluginPayload() {
  const maxResults = Number.isFinite(DEFAULT_WEB_SEARCH_RESULTS)
    ? DEFAULT_WEB_SEARCH_RESULTS
    : 3;

  return {
    id: 'web',
    max_results: maxResults,
  };
}

function handleModelSelectChange() {
  persistSelectedModel(modelSelect.value);
  modelSettingsController.syncActiveModelDisplay();
}

function resolveModelForRequest(selectedModel) {
  const fallback = 'openrouter/auto';
  const baseModel = typeof selectedModel === 'string' && selectedModel.trim()
    ? selectedModel.trim()
    : fallback;

  if (!webSearchEnabled) {
    return baseModel;
  }

  if (baseModel.endsWith(':online')) {
    return baseModel;
  }

  const directCandidate = `${baseModel}:online`;
  if (availableModels.some((model) => model.id === directCandidate)) {
    return directCandidate;
  }

  const [prefix] = baseModel.split(':');
  if (prefix && prefix !== baseModel) {
    const fallbackCandidate = `${prefix}:online`;
    if (availableModels.some((model) => model.id === fallbackCandidate)) {
      return fallbackCandidate;
    }
  }

  return baseModel;
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

function persistWebSearchPreference(enabled) {
  if (!supportsLocalStorage()) {
    return;
  }
  try {
    const value = enabled ? '1' : '0';
    window.localStorage.setItem(WEB_SEARCH_PREF_KEY, value);
  } catch (error) {
    console.warn('Failed to persist web search preference', error);
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

function readStoredWebSearchPreference() {
  if (!supportsLocalStorage()) {
    return false;
  }
  try {
    const raw = window.localStorage.getItem(WEB_SEARCH_PREF_KEY);
    if (raw === '1') {
      return true;
    }
    if (raw === '0') {
      return false;
    }
    if (raw == null) {
      return false;
    }
    const normalized = typeof raw === 'string' ? raw.trim().toLowerCase() : '';
    return normalized === 'true';
  } catch (error) {
    console.warn('Failed to read web search preference', error);
    return false;
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
    if (entry.metadata) options.metadata = entry.metadata;
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
      const metadata = sanitizeMetadata(entry.metadata);
      if (metadata) {
        record.metadata = metadata;
      }
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
        if (entry.metadata && typeof entry.metadata === 'object') {
          record.metadata = entry.metadata;
        }
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

  // Preserve the entire model object and just add computed fields
  const enriched = { ...model };

  // Ensure we have a consistent label field for the UI
  enriched.label = model.name || model.id || model.slug || id;

  // Ensure we have the tool support detection (which uses complex logic)
  if (enriched.supports_tools === undefined) {
    enriched.supports_tools = detectToolSupport(model);
  }

  // Ensure supported_parameters is always an array
  if (!Array.isArray(enriched.supported_parameters)) {
    enriched.supported_parameters = [];
  }

  return enriched;
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

function updateBodyModalClass() {
  if (typeof document === 'undefined') {
    return;
  }
  const visibleModals = document.querySelectorAll('.modal.is-visible');
  if (visibleModals.length) {
    document.body.classList.add('modal-open');
  } else {
    document.body.classList.remove('modal-open');
  }
}

function isPlainObject(value) {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function sanitizeMetadata(value) {
  if (!isPlainObject(value)) {
    return null;
  }

  try {
    if (typeof structuredClone === 'function') {
      return structuredClone(value);
    }
  } catch (_) {
    // structuredClone not supported; fall back to JSON clone
  }

  try {
    return JSON.parse(JSON.stringify(value));
  } catch (_) {
    return null;
  }
}

function formatMetadataLabel(raw) {
  if (typeof raw !== 'string') {
    return 'Value';
  }
  return raw
    .replace(/[_\-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/(^|\s)\w/g, (match) => match.toUpperCase());
}

function formatMetadataValue(value) {
  if (value == null) {
    return '—';
  }
  if (typeof value === 'number') {
    return metadataNumberFormatter.format(value);
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (typeof value === 'object') {
    if (Array.isArray(value)) {
      return value.map((item) => formatMetadataValue(item)).join(', ');
    }
    try {
      return JSON.stringify(value);
    } catch (_) {
      return String(value);
    }
  }
  return String(value);
}

function formatUsageCost(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return null;
  }
  return `$${metadataCreditFormatter.format(value)}`;
}

function flattenMetadataObject(value, prefix = '') {
  if (!isPlainObject(value)) {
    return [];
  }

  const entries = [];
  for (const [key, raw] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (isPlainObject(raw)) {
      entries.push(...flattenMetadataObject(raw, path));
    } else if (Array.isArray(raw)) {
      if (raw.every((item) => !isPlainObject(item))) {
        entries.push([formatMetadataLabel(path), formatMetadataValue(raw)]);
      } else {
        raw.forEach((item, index) => {
          const arrayPath = `${path}[${index}]`;
          if (isPlainObject(item)) {
            entries.push(...flattenMetadataObject(item, arrayPath));
          } else {
            entries.push([formatMetadataLabel(arrayPath), formatMetadataValue(item)]);
          }
        });
      }
    } else {
      entries.push([formatMetadataLabel(path), formatMetadataValue(raw)]);
    }
  }
  return entries;
}
