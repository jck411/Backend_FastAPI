# Voice PWA Tuning Options

This is a quick reference for speed and responsiveness knobs that do not
require a rewrite. It focuses on settings you can adjust safely, plus a few
low-risk code tweaks to consider later.

## Safe adjustments (no code)

These values live under `src/backend/data/clients/voice/` and can be edited
directly or updated via the `/api/clients/voice/*` endpoints.

### STT end-of-turn timing
File: `src/backend/data/clients/voice/stt.json`

- `eot_timeout_ms` (default 5000). Lower values return faster after you stop
  speaking. Typical range: 1500-3000.
- `eot_threshold` (default 0.7). Lower values end turns sooner. Typical range:
  0.6-0.75. Too low can clip words.
- `keyterms` (default empty). Add domain-specific words to improve accuracy.

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
