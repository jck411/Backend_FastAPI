export const SPEECH_SETTINGS_LS_KEY = 'speech.settings.v1';

function nowIso() {
    try {
        return new Date().toISOString();
    } catch (_) {
        return null;
    }
}

export function getDefaultSpeechSettings() {
    return {
        stt: {
            provider: 'deepgram',
            model: 'nova-3',
            interim_results: true,
            vad_events: true,
            utterance_end_ms: 1000,
            endpointing: 1000,
            auto_submit: true,
            timeout_ms: 30000, // 30 seconds default
        },
        tts: {
            provider: '',
            voice: '',
        },
        wakeword: {
            enabled: false,
            phrase: '',
        },
        conversation: {
            enabled: false,
        },
        updated_at: null,
    };
}

export function getSpeechSettings() {
    const defaults = getDefaultSpeechSettings();
    try {
        if (typeof window === 'undefined' || !window.localStorage) {
            return defaults;
        }
        const raw = window.localStorage.getItem(SPEECH_SETTINGS_LS_KEY);
        if (!raw) {
            return defaults;
        }
        const data = JSON.parse(raw);

        // Sanitize and merge with defaults
        const settings = { ...defaults };

        if (data && typeof data === 'object') {
            if (data.stt && typeof data.stt === 'object') {
                settings.stt = {
                    provider: typeof data.stt.provider === 'string' ? data.stt.provider : defaults.stt.provider,
                    model: typeof data.stt.model === 'string' ? data.stt.model : defaults.stt.model,
                    interim_results:
                        typeof data.stt.interim_results === 'boolean'
                            ? data.stt.interim_results
                            : defaults.stt.interim_results,
                    vad_events:
                        typeof data.stt.vad_events === 'boolean' ? data.stt.vad_events : defaults.stt.vad_events,
                    utterance_end_ms: Number.isFinite(Number(data.stt.utterance_end_ms))
                        ? Number(data.stt.utterance_end_ms)
                        : defaults.stt.utterance_end_ms,
                    endpointing: Number.isFinite(Number(data.stt.endpointing))
                        ? Number(data.stt.endpointing)
                        : defaults.stt.endpointing,
                    auto_submit:
                        typeof data.stt.auto_submit === 'boolean'
                            ? data.stt.auto_submit
                            : defaults.stt.auto_submit,
                    timeout_ms: Number.isFinite(Number(data.stt.timeout_ms))
                        ? Number(data.stt.timeout_ms)
                        : defaults.stt.timeout_ms,
                };
            }

            if (data.tts && typeof data.tts === 'object') {
                settings.tts = {
                    provider: typeof data.tts.provider === 'string' ? data.tts.provider : defaults.tts.provider,
                    voice: typeof data.tts.voice === 'string' ? data.tts.voice : defaults.tts.voice,
                };
            }

            if (data.wakeword && typeof data.wakeword === 'object') {
                settings.wakeword = {
                    enabled:
                        typeof data.wakeword.enabled === 'boolean'
                            ? data.wakeword.enabled
                            : defaults.wakeword.enabled,
                    phrase: typeof data.wakeword.phrase === 'string' ? data.wakeword.phrase : defaults.wakeword.phrase,
                };
            }

            if (data.conversation && typeof data.conversation === 'object') {
                settings.conversation = {
                    enabled:
                        typeof data.conversation.enabled === 'boolean'
                            ? data.conversation.enabled
                            : defaults.conversation.enabled,
                };
            }

            if (typeof data.updated_at === 'string' && data.updated_at) {
                settings.updated_at = data.updated_at;
            }
        }

        return settings;
    } catch (_) {
        return defaults;
    }
}

export function saveSpeechSettings(settings) {
    const sanitized = getSpeechSettings();
    if (settings && typeof settings === 'object') {
        if (settings.stt && typeof settings.stt === 'object') {
            sanitized.stt = {
                ...sanitized.stt,
                ...settings.stt,
            };
        }
        if (settings.tts && typeof settings.tts === 'object') {
            sanitized.tts = {
                ...sanitized.tts,
                ...settings.tts,
            };
        }
        if (settings.wakeword && typeof settings.wakeword === 'object') {
            sanitized.wakeword = {
                ...sanitized.wakeword,
                ...settings.wakeword,
            };
        }
        if (settings.conversation && typeof settings.conversation === 'object') {
            sanitized.conversation = {
                ...sanitized.conversation,
                ...settings.conversation,
            };
        }
    }
    sanitized.updated_at = nowIso();

    try {
        if (typeof window !== 'undefined' && window.localStorage) {
            window.localStorage.setItem(SPEECH_SETTINGS_LS_KEY, JSON.stringify(sanitized));
        }
    } catch (_) {
        // ignore storage failures
    }
    return sanitized;
}

export function createSpeechSettingsController({
    openButton,
    modal,
    backdrop,
    closeButton,
}) {
    const controls = {
        form: null,
        status: null,
        updatedAt: null,
        submitButton: null,

        sttProvider: null,
        sttModel: null,
        sttInterim: null,
        sttVad: null,
        sttUtteranceEndMs: null,
        sttEndpointing: null,
        sttAutoSubmit: null,
        sttTimeoutMs: null,

        ttsProvider: null,
        ttsVoice: null,

        wakeEnabled: null,
        wakePhrase: null,

        conversationEnabled: null,
    };

    const state = {
        initialized: false,
        visible: false,
        saving: false,
    };

    function bindControls() {
        controls.form = document.querySelector('#speech-settings-form');
        controls.status = document.querySelector('#speech-settings-status');
        controls.updatedAt = document.querySelector('#speech-settings-updated-at');
        controls.submitButton = document.querySelector('#speech-settings-submit');

        controls.sttProvider = document.querySelector('#stt-provider');
        controls.sttModel = document.querySelector('#stt-model');
        controls.sttInterim = document.querySelector('#stt-interim');
        controls.sttVad = document.querySelector('#stt-vad-events');
        controls.sttUtteranceEndMs = document.querySelector('#stt-utterance-end-ms');
        controls.sttEndpointing = document.querySelector('#stt-endpointing');
        controls.sttAutoSubmit = document.querySelector('#stt-auto-submit');
        controls.sttTimeoutMs = document.querySelector('#stt-timeout-ms');

        controls.ttsProvider = document.querySelector('#tts-provider');
        controls.ttsVoice = document.querySelector('#tts-voice');

        controls.wakeEnabled = document.querySelector('#wakeword-enabled');
        controls.wakePhrase = document.querySelector('#wakeword-phrase');

        controls.conversationEnabled = document.querySelector('#conversation-enabled');
    }

    function setModalSavingState(isSaving) {
        state.saving = !!isSaving;
        if (controls.submitButton) {
            controls.submitButton.disabled = !!isSaving;
        }
    }

    function setModalStatus(message, variant) {
        const node = controls.status;
        if (!node) return;
        node.textContent = message || '';
        if (variant) {
            node.dataset.variant = variant;
        } else {
            delete node.dataset.variant;
        }
    }

    function updateModalUpdatedAt(value) {
        const node = controls.updatedAt;
        if (!node) return;
        const text = formatTimestamp(value);
        node.textContent = text;
        node.hidden = !text;
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

    function populateForm(settings) {
        const s = settings || getSpeechSettings();

        // STT
        if (controls.sttProvider) controls.sttProvider.value = s.stt.provider || 'deepgram';
        if (controls.sttModel) controls.sttModel.value = s.stt.model || 'nova-3';
        if (controls.sttInterim) controls.sttInterim.value = s.stt.interim_results ? 'true' : 'false';
        if (controls.sttVad) controls.sttVad.value = s.stt.vad_events ? 'true' : 'false';
        if (controls.sttUtteranceEndMs)
            controls.sttUtteranceEndMs.value = String(
                Number.isFinite(Number(s.stt.utterance_end_ms)) ? Number(s.stt.utterance_end_ms) : 1000
            );
        if (controls.sttEndpointing)
            controls.sttEndpointing.value = String(
                Number.isFinite(Number(s.stt.endpointing)) ? Number(s.stt.endpointing) : 1000
            );
        if (controls.sttAutoSubmit) controls.sttAutoSubmit.value = s.stt.auto_submit ? 'true' : 'false';
        if (controls.sttTimeoutMs)
            controls.sttTimeoutMs.value = String(
                Number.isFinite(Number(s.stt.timeout_ms)) ? Number(s.stt.timeout_ms) : 30000
            );

        // TTS
        if (controls.ttsProvider) controls.ttsProvider.value = s.tts.provider || '';
        if (controls.ttsVoice) controls.ttsVoice.value = s.tts.voice || '';

        // Wakeword
        if (controls.wakeEnabled) controls.wakeEnabled.value = s.wakeword.enabled ? 'true' : 'false';
        if (controls.wakePhrase) controls.wakePhrase.value = s.wakeword.phrase || '';

        // Conversation
        if (controls.conversationEnabled) controls.conversationEnabled.value = s.conversation.enabled ? 'true' : 'false';

        updateModalUpdatedAt(s.updated_at);
    }

    function readFromForm() {
        const sttProvider = controls.sttProvider?.value || 'deepgram';
        const sttModel = controls.sttModel?.value || 'nova-3';
        const sttInterim = controls.sttInterim?.value === 'true';
        const sttVad = controls.sttVad?.value === 'true';
        const sttAutoSubmit = controls.sttAutoSubmit?.value === 'true';

        const utteranceRaw = controls.sttUtteranceEndMs?.value;
        const endpointingRaw = controls.sttEndpointing?.value;
        const timeoutRaw = controls.sttTimeoutMs?.value;
        const utterance = Number(utteranceRaw);
        const endpointing = Number(endpointingRaw);
        const timeout = Number(timeoutRaw);

        const ttsProvider = controls.ttsProvider?.value || '';
        const ttsVoice = controls.ttsVoice?.value || '';

        const wakeEnabled = controls.wakeEnabled?.value === 'true';
        const wakePhrase = controls.wakePhrase?.value || '';

        const conversationEnabled = controls.conversationEnabled?.value === 'true';

        return {
            stt: {
                provider: sttProvider,
                model: sttModel,
                interim_results: sttInterim,
                vad_events: sttVad,
                utterance_end_ms: Number.isFinite(utterance) ? utterance : 1000,
                endpointing: Number.isFinite(endpointing) ? endpointing : 1000,
                auto_submit: sttAutoSubmit,
                timeout_ms: Number.isFinite(timeout) ? timeout : 30000,
            },
            tts: {
                provider: ttsProvider,
                voice: ttsVoice,
            },
            wakeword: {
                enabled: wakeEnabled,
                phrase: wakePhrase,
            },
            conversation: {
                enabled: conversationEnabled,
            },
        };
    }

    async function openModal() {
        if (!modal || state.visible) return;

        state.visible = true;
        modal.classList.add('is-visible');
        modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('modal-open');
        document.addEventListener('keydown', handleModalKeydown);

        setModalStatus('', null);
        setModalSavingState(false);
        populateForm(getSpeechSettings());

        // Focus first useful control
        const focusTarget =
            controls.sttProvider ||
            controls.sttModel ||
            controls.ttsProvider ||
            controls.wakePhrase ||
            controls.submitButton;
        if (focusTarget) {
            window.setTimeout(() => {
                focusTarget.focus();
            }, 0);
        }
    }

    function closeModal() {
        if (!modal || !state.visible) return;

        state.visible = false;
        modal.classList.remove('is-visible');
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('modal-open');
        document.removeEventListener('keydown', handleModalKeydown);
    }

    function handleModalKeydown(event) {
        if (event.key === 'Escape') {
            closeModal();
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
            const payload = readFromForm();
            const saved = saveSpeechSettings(payload);
            populateForm(saved);
            try {
                // Notify listeners in the same tab that speech settings changed
                window.dispatchEvent(new CustomEvent('speechsettings:updated', { detail: saved }));
            } catch (_) {
                // no-op
            }
            setModalStatus('Saved', 'success');
        } catch (error) {
            console.error('Failed to save speech settings', error);
            setModalStatus('Save failed', 'error');
        } finally {
            setModalSavingState(false);
        }
    }

    function initialize() {
        if (state.initialized) return;
        state.initialized = true;

        bindControls();

        if (openButton) {
            openButton.addEventListener('click', (e) => {
                if (e) e.preventDefault();
                openModal().catch((err) => console.error('Failed to open speech settings', err));
            });
        }

        if (closeButton) {
            closeButton.addEventListener('click', () => {
                closeModal();
            });
        }

        if (backdrop) {
            backdrop.addEventListener('click', () => {
                closeModal();
            });
        }

        if (controls.form) {
            controls.form.addEventListener('submit', handleSubmit);
        }
    }

    return {
        initialize,
    };
}
