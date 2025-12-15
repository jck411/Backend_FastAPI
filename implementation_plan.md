# Smart Home Voice Assistant - Implementation Status

## Project Overview

Building an Alexa-like smart home voice assistant with:
- **Raspberry Pi 5** - Edge device running audio agent + kiosk UI
- **Backend Server** (FastAPI) - Intelligence, STT, TTS, MCP tools
- **Real-time Communication** - WebSocket bidirectional

---

## Current Architecture

```
Backend (FastAPI) - http://192.168.1.223:8000
├── WebSocket Server       ✅ COMPLETE (voice_assistant.py)
├── STT Service            ✅ COMPLETE (stt_service.py)
├── TTS Service            ✅ COMPLETE (tts_service.py)
├── Voice Session Manager  ✅ COMPLETE (voice_session.py)
├── Intent Parser          ⏳ TODO (intent_parser.py)
└── Existing Infrastructure (reuse)
    ├── OpenRouter Client  ✅ EXISTS
    ├── MCP Client         ✅ EXISTS
    ├── MCP Registry       ✅ EXISTS
    └── Chat Orchestrator  ✅ EXISTS

Frontends:
├── Svelte Chat UI         ✅ COMPLETE - http://192.168.1.223:5173
│   └── frontend/
└── Kiosk UI (React)       ✅ COMPLETE - http://192.168.1.223:5174
    └── frontend-kiosk/
```

---

## ✅ COMPLETED - Raspberry Pi Audio Agent

Complete Python audio agent deployed to Pi at `/home/jck411/.gemini/antigravity/scratch/raspi-smarthome/`

**Components Implemented:**
- ✅ Audio capture module (PyAudio + ReSpeaker 4 Mic Array)
- ✅ Wake word detection (openwakeword - "hey Jarvis")
- ✅ WebSocket client with auto-reconnect
- ✅ State machine orchestrator (IDLE/LISTENING/PROCESSING/SPEAKING)
- ✅ Barge-in support (wake word during TTS)
- ✅ Systemd service with auto-restart

**WebSocket Protocol (Pi → Backend):**
- ✅ `connection_ready` - Initial connection
- ✅ `wakeword_detected` - Wake word from IDLE
- ✅ `wakeword_barge_in` - Wake word during SPEAKING
- ✅ `audio_chunk` - Audio streaming (base64 PCM)
- ✅ `stream_end` - Stop streaming
- ✅ `heartbeat` - Keep-alive

**WebSocket Protocol (Backend → Pi):**
- ✅ `set_state` - State changes
- ✅ `interrupt_tts` - Stop TTS playback
- ✅ `tts_audio` - Play audio response
- ✅ `session_reset` - Reset to IDLE

---

## ✅ COMPLETED - Backend Voice Services

### 1. WebSocket Router ✅ COMPLETE

**File:** `src/backend/routers/voice_assistant.py` (145 lines)

**Implemented:**
- ✅ WebSocket endpoint `/api/voice/connect`
- ✅ Client connection handling with `client_id` query param
- ✅ Event handlers for all Pi events (wakeword, audio_chunk, stream_end, etc.)
- ✅ Integration with STT and TTS services
- ✅ State management via VoiceConnectionManager
- ✅ Registered in app.py

---

### 2. STT Service ✅ COMPLETE

**File:** `src/backend/services/stt_service.py` (184 lines)

**Implemented:**
- ✅ `STTService` class with Deepgram SDK
- ✅ `create_session(session_id, on_transcript, on_error)` - Start live connection
- ✅ `stream_audio(session_id, audio_bytes)` - Send audio to Deepgram
- ✅ `close_session(session_id)` - Terminate connection
- ✅ Async background task for connection management
- ✅ Transcript callbacks (interim + final)

**Deepgram Configuration:**
```python
{
    "model": "nova-2",
    "language": "en-US",
    "smart_format": "true",
    "interim_results": "true",
    "vad_events": "true",
    "endpointing": "1000"
}
```

---

### 3. TTS Service ✅ COMPLETE

**File:** `src/backend/services/tts_service.py` (50 lines)

**Implemented:**
- ✅ `TTSService` class with Deepgram Aura
- ✅ `synthesize(text: str) -> bytes` - Generate audio

**Deepgram Configuration:**
```python
{
    "model": "aura-asteria-en",
    "encoding": "linear16",
    "sample_rate": 16000,
    "container": "none"
}
```

---

### 4. Voice Session Manager ✅ COMPLETE

**File:** `src/backend/services/voice_session.py` (74 lines)

**Implemented:**
- ✅ `VoiceSession` dataclass with all fields
- ✅ `VoiceConnectionManager` class
- ✅ `connect(websocket, client_id)` - Accept connection
- ✅ `disconnect(client_id)` - Remove session
- ✅ `get_session(client_id)` - Retrieve session
- ✅ `send_message(client_id, message)` - Send to client
- ✅ `update_state(client_id, new_state)` - State transition + broadcast
- ✅ `broadcast(message)` - Send to all clients

---

## ✅ COMPLETED - Kiosk Frontend

**Directory:** `frontend-kiosk/`

**Technology:** React + Vite + Framer Motion + Tailwind CSS

**Components:**
- ✅ `App.jsx` - Main app with 3 swipeable screens
- ✅ `components/Clock.jsx` - Time and date display
- ✅ `components/PhotoFrame.jsx` - Auto-rotating photo slideshow
- ✅ `components/TranscriptionScreen.jsx` - Live transcript + voice state

**Features:**
- ✅ WebSocket connection to `/api/voice/connect`
- ✅ Swipe gestures between screens
- ✅ Auto-jump to transcription screen on LISTENING/THINKING state
- ✅ Auto-return to clock after IDLE
- ✅ Connection status indicator
- ✅ Page indicator dots

**Running:** `http://192.168.1.223:5174`

---

## ⏳ TODO - Upgrade Voice Capabilities (KioskChatService)

**File:** `src/backend/services/kiosk_chat_service.py` (Upgrade)

### Purpose
Enable the Voice Assistant to use MCP tools (e.g., "turn on lights", "check weather") by upgrading the lightweight `KioskChatService` to use a **dedicated** instance of `ChatOrchestrator`.

### Design Decision: Independent Instance
To keep the Kiosk/Voice assistant distinct from the main Svelte frontend:
- **Separate Settings:** It will use its own system prompt and model preferences.
- **Separate Orchestrator:** It will instantiate its own `ChatOrchestrator` rather than sharing the global singleton used by the main web UI.
- **Why?** This prevents "pollution" of the main chat history and allows specific tuning (e.g., faster/smaller models) for voice interactions.

### Implementation Checklist
- [ ] Update `KioskChatService` class:
  - [ ] Initialize a private `ChatOrchestrator` instance
  - [ ] Configure it with Kiosk-specific settings (if available) or defaults
  - [ ] Update `stream_response` to use `orchestrator.process_message` instead of raw `OpenRouterClient`
- [ ] Connect MCP Tools:
  - [ ] Ensure the Kiosk Orchestrator has access to the MCP Registry
  - [ ] Verify tool execution works via voice commands
- [ ] System Prompt:
  - [ ] Ensure rigid "voice mode" system prompt (concise, no markdown) is preserved

---

## Integration & Configuration ✅ COMPLETE

### `src/backend/app.py` Updates ✅
- ✅ Imports voice_assistant router
- ✅ `app.state.voice_manager = VoiceConnectionManager()`
- ✅ `app.state.stt_service = STTService()`
- ✅ `app.state.tts_service = TTSService()`
- ✅ `app.include_router(voice_assistant.router)`
- ✅ Serves kiosk static files from `src/backend/static/`

### Dependencies ✅
- ✅ `deepgram-sdk` installed

---

## Running the System

### Start All Services
```bash
./start_server.sh
```

This starts:
1. **Backend API** - `http://192.168.1.223:8000`
2. **Svelte Chat UI** - `http://192.168.1.223:5173`
3. **Kiosk UI** - `http://192.168.1.223:5174`

### Firewall Ports (already configured)
```bash
sudo firewall-cmd --list-ports
# 5173/tcp 5174/tcp 8000/tcp
```

---

## Success Criteria

- [x] Pi connects to backend via WebSocket
- [x] Kiosk frontend connects and shows state
- [x] Wake word detection triggers backend STT session
- [x] Audio streams from Pi to Deepgram
- [x] Transcripts received in real-time
- [x] TTS responses generated and sent back
- [ ] Voice commands execute MCP tools (needs IntentParser)
- [x] System survives network drops and reconnects

---

## Next Steps

### Phase 2: Intelligent Responses
1. Create `intent_parser.py` to integrate with ChatOrchestrator
2. Replace echo logic in `voice_assistant.py` with IntentParser
3. Test with existing MCP tools

### Phase 3: Smart Home Integration
1. Create home-appliances MCP server
2. Add device control tools
3. Configure in `data/mcp_servers.json`

---

## File Status Summary

| File | Status | Lines |
|------|--------|-------|
| `src/backend/routers/voice_assistant.py` | ✅ Complete | 145 |
| `src/backend/services/stt_service.py` | ✅ Complete | 184 |
| `src/backend/services/tts_service.py` | ✅ Complete | 50 |
| `src/backend/services/voice_session.py` | ✅ Complete | 74 |
| `src/backend/services/intent_parser.py` | ⏳ TODO | - |
| `frontend-kiosk/` | ✅ Complete | ~400 |

**Total Backend Voice Code:** ~450 lines (complete)
