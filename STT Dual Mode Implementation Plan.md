# STT Dual Mode Implementation Plan

**Project**: Add Conversation vs Command modes to voice frontend STT
**Date**: February 11, 2026
**Branch**: separation

## Overview

Add a mode toggle to the voice frontend that switches between:
- **Conversation Mode** — Flux (v2 API), fast turn detection, auto-listen after response
- **Command Mode** — Nova-3 (v1 API), higher accuracy, click-to-talk, no auto-listen

Each mode has dedicated settings. TTS works independently in both modes.

### Current State (after Parts 1 & 2)
- Deepgram SDK: **5.3.2** ✓
- STT modes: Flux v2 (conversation) and Nova-3 v1 (command) ✓
- Settings: `src/backend/data/clients/voice/stt.json` (all fields present)
- Schema: `src/backend/schemas/client_settings.py` → `SttSettings` & `SttSettingsUpdate`
- Service: `src/backend/services/stt_service.py` → `DeepgramSession` (dual mode)
- Voice backend: `src/backend/routers/voice_assistant.py` (uses `stt_settings.mode`)
- Voice frontend: `frontend-voice/src/App.jsx`

### Key Files for Part 3
```
frontend-voice/src/App.jsx     ← Main changes (state + UI)
frontend-voice/src/App.css     ← Add mode toggle styles
```

---

## Part 1: Backend Schema & STT Service ✅ COMPLETE

All items implemented:
- [x] `pyproject.toml` updated to `deepgram-sdk>=5.3.2`
- [x] `SttSettings` has `mode` + all command fields
- [x] `SttSettingsUpdate` has optional versions
- [x] `stt.json` has all defaults (eot_timeout_ms=1000, mode=conversation)
- [x] `DeepgramSession.__init__()` accepts mode + command params
- [x] `DeepgramSession.connect()` uses v1 for command, v2 for conversation
- [x] `_handle_message()` handles both `StartOfTurn` (v2) and `SpeechStarted` (v1)
- [x] Uses `speech_final` for v1 end detection (per Deepgram docs)

---

## Part 2: Voice Backend State Machine ✅ COMPLETE

**Goal**: Update voice assistant to use `stt_settings.mode` for post-response behavior.

### Changes Made
1. **`voice_assistant.py`** — Two locations changed from `llm_settings.conversation_mode` to `stt_settings.mode`:
   - After non-TTS response (~line 261): Uses `stt_settings.mode == "conversation"`
   - `tts_playback_end` handler (~line 453): Uses `stt_settings.mode == "conversation"`

2. **Optimization**: Factored out `resume_session()` call - always called before mode check

### Verification (Part 2) ✅
- [x] Conversation mode: auto-listen after response
- [x] Command mode: returns to IDLE after response
- [x] Orb tap stops everything in both modes
- [x] Mode is read from settings on each TTS end (no stale state)

---

## Part 3: Voice Frontend UI

**Goal**: Add mode selector and mode-specific settings panels.

### Current State of App.jsx

The frontend already has:
- `sttDraft` state with conversation settings only: `{ eot_timeout_ms, eot_threshold, listen_timeout_seconds }`
- Settings panel with STT sliders for conversation mode
- TTS toggle and text stream speed slider
- Fetch from `/api/clients/voice/stt` and PUT to save

### Changes Needed

#### 1. Expand `sttDraft` State

**Current:**
```javascript
const [sttDraft, setSttDraft] = useState({
  eot_timeout_ms: 5000,
  eot_threshold: 0.7,
  listen_timeout_seconds: 15,
});
```

**New:**
```javascript
const [sttDraft, setSttDraft] = useState({
  mode: 'conversation',
  // Conversation mode (Flux)
  eot_timeout_ms: 1000,
  eot_threshold: 0.7,
  listen_timeout_seconds: 15,
  // Command mode (Nova-3)
  command_utterance_end_ms: 1500,
  command_endpointing: 1200,
  command_smart_format: true,
  command_punctuate: true,
  command_numerals: true,
  command_filler_words: false,
  command_profanity_filter: false,
});
```

#### 2. Update Load Settings (useEffect)

**In `loadSettings()` function, update the normalized object:**
```javascript
const normalized = {
  mode: data.mode || 'conversation',
  // Conversation
  eot_timeout_ms: Number(data.eot_timeout_ms ?? 1000),
  eot_threshold: Number(data.eot_threshold ?? 0.7),
  listen_timeout_seconds: Number(data.listen_timeout_seconds ?? 15),
  // Command
  command_utterance_end_ms: Number(data.command_utterance_end_ms ?? 1500),
  command_endpointing: Number(data.command_endpointing ?? 1200),
  command_smart_format: Boolean(data.command_smart_format ?? true),
  command_punctuate: Boolean(data.command_punctuate ?? true),
  command_numerals: Boolean(data.command_numerals ?? true),
  command_filler_words: Boolean(data.command_filler_words ?? false),
  command_profanity_filter: Boolean(data.command_profanity_filter ?? false),
};
```

#### 3. Update Save Settings (handleSaveSettings)

**Send all STT fields:**
```javascript
const payload = {
  mode: sttDraft.mode,
  // Conversation
  eot_timeout_ms: Number(sttDraft.eot_timeout_ms),
  eot_threshold: Number(sttDraft.eot_threshold),
  listen_timeout_seconds: Number(sttDraft.listen_timeout_seconds),
  // Command
  command_utterance_end_ms: Number(sttDraft.command_utterance_end_ms),
  command_endpointing: Number(sttDraft.command_endpointing),
  command_smart_format: Boolean(sttDraft.command_smart_format),
  command_punctuate: Boolean(sttDraft.command_punctuate),
  command_numerals: Boolean(sttDraft.command_numerals),
  command_filler_words: Boolean(sttDraft.command_filler_words),
  command_profanity_filter: Boolean(sttDraft.command_profanity_filter),
};
```

#### 4. Update Default Settings

```javascript
const defaultSettings = {
  mode: 'conversation',
  eot_timeout_ms: 1000,
  eot_threshold: 0.7,
  listen_timeout_seconds: 15,
  command_utterance_end_ms: 1500,
  command_endpointing: 1200,
  command_smart_format: true,
  command_punctuate: true,
  command_numerals: true,
  command_filler_words: false,
  command_profanity_filter: false,
};
```

#### 5. Settings Panel UI Structure

```
┌─────────────────────────────────────┐
│ Voice Settings              Save Close│
├─────────────────────────────────────┤
│ Mode                                 │
│ [Conversation] [Command]  ← toggle   │
├─────────────────────────────────────┤
│ Text to Speech                       │
│ ├─ Enable TTS: [On/Off]              │
│ └─ Text stream speed: [slider/Sync]  │
├─────────────────────────────────────┤
│ IF mode == "conversation":           │
│   Speech Recognition (Flux)          │
│   ├─ End of turn timeout: [slider]   │
│   ├─ End of turn threshold: [slider] │
│   └─ Listen timeout: [slider]        │
├─────────────────────────────────────┤
│ IF mode == "command":                │
│   Speech Recognition (Nova-3)        │
│   ├─ Utterance end: [slider] ms      │
│   ├─ Endpointing: [slider] ms        │
│   ├─ Smart format: [On/Off]          │
│   ├─ Punctuate: [On/Off]             │
│   ├─ Numerals: [On/Off]              │
│   ├─ Filler words: [On/Off]          │
│   └─ Profanity filter: [On/Off]      │
├─────────────────────────────────────┤
│ [Default]                            │
└─────────────────────────────────────┘
```

#### 6. Mode Toggle Component (JSX)

Add after settings-section-title for Mode:
```jsx
<div className="settings-section">
  <div className="settings-section-title">Mode</div>
  <div className="settings-row">
    <div className="mode-toggle">
      <button
        className={`mode-btn ${sttDraft.mode === 'conversation' ? 'active' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          setSttDraft(prev => ({ ...prev, mode: 'conversation' }));
        }}
        disabled={settingsSaving}
      >
        Conversation
      </button>
      <button
        className={`mode-btn ${sttDraft.mode === 'command' ? 'active' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          setSttDraft(prev => ({ ...prev, mode: 'command' }));
        }}
        disabled={settingsSaving}
      >
        Command
      </button>
    </div>
  </div>
</div>
```

#### 7. Conditional Settings Sections (JSX)

Replace current "Speech Recognition" section with:
```jsx
{sttDraft.mode === 'conversation' ? (
  <div className="settings-section">
    <div className="settings-section-title">Speech Recognition (Flux)</div>
    {/* existing eot_timeout_ms, eot_threshold, listen_timeout_seconds sliders */}
  </div>
) : (
  <div className="settings-section">
    <div className="settings-section-title">Speech Recognition (Nova-3)</div>

    <div className="settings-row">
      <div className="settings-label">Utterance end</div>
      <div className="settings-value">{sttDraft.command_utterance_end_ms} ms</div>
      <input
        className="settings-slider"
        type="range"
        min="500"
        max="3000"
        step="100"
        value={sttDraft.command_utterance_end_ms}
        onChange={(e) => setSttDraft(prev => ({
          ...prev,
          command_utterance_end_ms: Number(e.target.value),
        }))}
      />
    </div>

    <div className="settings-row">
      <div className="settings-label">Endpointing</div>
      <div className="settings-value">{sttDraft.command_endpointing} ms</div>
      <input
        className="settings-slider"
        type="range"
        min="300"
        max="2000"
        step="100"
        value={sttDraft.command_endpointing}
        onChange={(e) => setSttDraft(prev => ({
          ...prev,
          command_endpointing: Number(e.target.value),
        }))}
      />
    </div>

    <div className="settings-row">
      <div className="settings-label">Smart format</div>
      <button
        className={`settings-toggle ${sttDraft.command_smart_format ? 'on' : ''}`}
        onClick={(e) => {
          e.stopPropagation();
          setSttDraft(prev => ({ ...prev, command_smart_format: !prev.command_smart_format }));
        }}
        disabled={settingsSaving}
      >
        {sttDraft.command_smart_format ? 'On' : 'Off'}
      </button>
    </div>

    {/* Similar for punctuate, numerals, filler_words, profanity_filter */}
  </div>
)}
```

#### 8. CSS Additions (App.css)

```css
/* Mode toggle - segmented control style */
.mode-toggle {
  display: flex;
  gap: 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.2);
}

.mode-btn {
  flex: 1;
  padding: 10px 16px;
  border: none;
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.6);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}

.mode-btn:first-child {
  border-right: 1px solid rgba(255,255,255,0.1);
}

.mode-btn.active {
  background: rgba(255,255,255,0.15);
  color: #fff;
}

.mode-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

### Verification Checklist (Part 3)
- [ ] Mode toggle switches between Conversation/Command
- [ ] Correct settings section shows for each mode
- [ ] TTS section always visible (independent of mode)
- [ ] Save persists mode and all settings to backend
- [ ] Load fetches and populates all settings
- [ ] Default button resets to conversation mode defaults
- [ ] UI aesthetic matches existing design
- [ ] Switching mode and saving updates which STT model backend uses on next session

---

## API Reference

### GET /api/clients/voice/stt
Returns all settings from `stt.json`:
```json
{
  "mode": "conversation",
  "eot_threshold": 0.7,
  "eot_timeout_ms": 1000,
  "keyterms": [],
  "pause_timeout_seconds": 30,
  "listen_timeout_seconds": 15,
  "command_model": "nova-3",
  "command_utterance_end_ms": 1500,
  "command_endpointing": 1200,
  "command_interim_results": true,
  "command_smart_format": true,
  "command_punctuate": true,
  "command_numerals": true,
  "command_filler_words": false,
  "command_profanity_filter": false
}
```

### PUT /api/clients/voice/stt
Partial update - send only fields you want to change:
```json
{
  "mode": "command",
  "command_utterance_end_ms": 1800
}
```

---

## Deepgram API Reference

### Flux (v2) - Conversation Mode
```python
client.listen.v2.connect(
    model="flux-general-en",
    encoding="linear16",
    sample_rate="16000",
    eot_threshold="0.7",
    eot_timeout_ms="1000"
)
```
Events: `StartOfTurn`, `EndOfTurn`, transcript at top level

### Nova (v1) - Command Mode
```python
client.listen.v1.connect(
    model="nova-3",
    encoding="linear16",
    sample_rate="16000",
    interim_results="true",
    utterance_end_ms="1500",
    endpointing="1200",
    smart_format="true",
    punctuate="true",
    numerals="true",
    filler_words="false",
    profanity_filter="false",
    vad_events="true"
)
```
Events: `SpeechStarted`, `Results` with `speech_final` for end detection

---

## Behavior Summary

| Aspect | Conversation | Command |
|--------|--------------|---------|
| Model | flux-general-en | nova-3 |
| API | v2 | v1 |
| Turn detection | ML-based (eot_threshold) | Timer-based (utterance_end_ms) |
| After response | Auto-listen | Return to IDLE |
| Tap orb (SPEAKING) | Stop TTS → IDLE | Stop TTS → IDLE |
| Tap orb (LISTENING) | Stop STT → IDLE | Stop STT → IDLE |
| Tap orb (IDLE) | Start STT → LISTENING | Start STT → LISTENING |
| TTS | Independent setting | Independent setting |

---

## Implementation Order

1. **Part 1** ✅ COMPLETE: Backend schema, settings file, STT service
2. **Part 2** ✅ COMPLETE: Voice backend state machine - uses stt_settings.mode
3. **Part 3** (this session): Frontend UI - mode toggle + conditional settings
