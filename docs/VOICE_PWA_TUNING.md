# Voice PWA Tuning Options

This is a quick reference for speed and responsiveness knobs that do not
require a rewrite. It focuses on settings you can adjust safely, plus a few
low-risk code tweaks to consider later.

## STT Mode Selection

The voice frontend supports two speech recognition modes, selectable via the
settings panel or `stt.json`:

| Mode | Model | API | Turn Detection | After Response |
|------|-------|-----|----------------|----------------|
| **Conversation** | flux-general-en | v2 | ML-based (`eot_threshold`) | Auto-listen |
| **Command** | nova-3 | v1 | Timer-based (`utterance_end_ms`) | Return to IDLE |

- **Conversation mode** — Optimized for back-and-forth dialogue. Uses Deepgram
  Flux with ML end-of-turn detection. Automatically resumes listening after TTS.
- **Command mode** — Optimized for single commands. Uses Nova-3 with higher
  accuracy. Click orb to speak each time.

## Safe adjustments (no code)

These values live under `src/backend/data/clients/voice/` and can be edited
directly or updated via the `/api/clients/voice/*` endpoints.

### STT settings
File: `src/backend/data/clients/voice/stt.json`

**Mode selection:**
- `mode` — `"conversation"` or `"command"`

**Conversation mode (Flux):**
- `eot_timeout_ms` (default 1000) — Max silence before forcing turn end.
- `eot_threshold` (default 0.7) — ML confidence for end-of-turn. Lower = faster
  but may clip words. Range: 0.6-0.75.
- `keyterms` — Domain-specific words to improve accuracy.

**Command mode (Nova-3):**
- `command_utterance_end_ms` (default 1000) — Silence duration to detect
  complete utterance. Community-recommended value.
- `command_endpointing` (default 300) — Shorter silence to finalize segments.
  Community-recommended value.
- `command_smart_format`, `command_numerals` — Formatting options for
  transcripts (`smart_format` already includes punctuation behavior).

### LLM response length
File: `src/backend/data/clients/voice/llm.json`

- `max_tokens` (default 500). Lower values reduce response latency and TTS time.

### TTS speed / quality
File: `src/backend/data/clients/voice/tts.json`

- `model` (default `tts-1`). `tts-1` is faster than `tts-1-hd`.
- `speed` (default 1.0). Slightly higher (1.1-1.2) sounds faster without
  changing the text length.

### UI idle timing
File: `src/backend/data/clients/voice/ui.json`

- `idle_return_delay_ms` controls how quickly the UI returns to idle when no
  speech is detected. This does not change STT speed but impacts perceived
  responsiveness.

## Low-risk code tweaks (only if needed later)

These are small changes with clear tradeoffs.

- Audio buffer size: `frontend-voice/src/hooks/useAudioCapture.js` uses
  `createScriptProcessor(4096, 1, 1)`. Dropping to 2048 or 1024 can reduce input
  latency but may increase CPU usage.

## How to apply changes

Option A: Edit the JSON files and restart the backend.

Option B: Use the settings endpoints (example):

```bash
curl -X PUT https://localhost:8000/api/clients/voice/stt \
  -H "Content-Type: application/json" \
  -d '{"eot_timeout_ms": 2000, "eot_threshold": 0.65}'
```

Notes:
- Values are validated (for example, `eot_timeout_ms` must be between 100 and
  30000).
- If you update via API, the JSON files in `src/backend/data/clients/voice/`
  are updated automatically.
