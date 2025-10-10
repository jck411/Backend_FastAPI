# Speech-to-Text Auto-Submit Implementation

This document explains the robust speech detection and auto-submit logic implemented for conversational AI interactions with household noise resilience.

## Overview

The auto-submit feature automatically submits voice input when the user finishes speaking, enabling natural conversation flow with the LLM without requiring manual button clicks. The implementation uses Deepgram's STT service with dual detection methods for maximum reliability.

## Core Problem

Detecting when someone has truly finished speaking is inherently difficult because:
- Humans can resume talking at any time
- Background noise can interfere with detection
- Different speaking patterns require different timeout values
- Household environments have varying noise levels (TV, music, phones, etc.)

## Solution: Dual Detection Method

Based on Deepgram's documentation, we implement a robust approach using **both** detection methods:

### 1. Primary Detection: `speech_final=true`
- **Most reliable** when available
- Deepgram is confident the speaker has finished
- Takes precedence over other methods
- Triggers auto-submit (after configurable delay)

### 2. Backup Detection: `UtteranceEnd` Events
- **Noise-resistant** fallback method
- Based on word timing patterns, not audio levels
- Ignores background noise (music, TV, phones)
- Only triggers if no `speech_final=true` was received (delay still applies)

## Implementation Details

### State Management

```javascript
// Speech detection state for robust end-of-speech detection
let speechFinalReceived = false; // Track if we've seen speech_final=true
let utteranceEndTimer = null; // Timer for UtteranceEnd handling
```

### Logic Flow

```
1. User starts speaking
   ↓
2. Deepgram sends interim transcripts
   ↓
3. User stops speaking
   ↓
4. Two possible detection paths:

Path A (Preferred):
   speech_final=true received
   → Set speechFinalReceived = true
   → Clear any pending UtteranceEnd timer
   → Schedule auto-submit after configured delay

Path B (Backup):
   UtteranceEnd received + speechFinalReceived = false
   → Check: no speech_final was received for this utterance
   → Schedule auto-submit after configured delay
   → Set timer to reset speechFinalReceived flag

Both paths:
   → Check auto_submit setting
   → Submit form if enabled
```

> The auto-submit delay is configurable in the speech settings panel. A value of `0` retains the previous immediate submission behavior.

### Key Code Sections

#### 1. UtteranceEnd Handling
```javascript
if (msg.type === 'UtteranceEnd') {
  // Only trigger if no speech_final=true was received
  if (!speechFinalReceived) {
    console.log('🎤 UtteranceEnd without speech_final - triggering auto-submit');
    // Trigger auto-submit logic
  }

  // Reset flag after delay for next utterance
  utteranceEndTimer = setTimeout(() => {
    speechFinalReceived = false;
  }, 1000);
}
```

#### 2. Speech Final Handling
```javascript
if (speechFinal) {
  // Mark that definitive detection occurred
  speechFinalReceived = true;

  // Clear backup timer since we have definitive detection
  if (utteranceEndTimer) {
    clearTimeout(utteranceEndTimer);
  }

// Schedule auto-submit after the configured delay
  if (autoSubmit) {
    stopVoiceInput(autoSubmit);
  }
}
```

## Configuration

### Speech Settings
The auto-submit behavior is controlled by the Speech Settings panel:

- **Auto-submit on speech end**: Enable/Disable
- **Auto-submit delay**: Milliseconds to wait before submitting when auto-submit is enabled
- **Provider**: Deepgram (configured for optimal detection)
- **Model**: nova-3 (recommended for accuracy)
- **Interim results**: Enabled (for real-time feedback)
- **VAD events**: Enabled (for SpeechStarted detection)
- **Utterance end**: 1000ms (timing for UtteranceEnd)
- **Endpointing**: 1000ms (timing for speech_final)

#### Other Deepgram Parameters
- **Language & tier** (`language`, `tier`): default to Deepgram’s auto values. Expose these if you need non-English transcripts or premium tiers.
- **Diarization** (`diarize`), **paragraphs**, **topics**, **summaries**, **sentiment**, **redaction**: Advanced analytics features not used in the chat UI today.
- **Search & replace** (`search`, `replace`), **keywords**, **detect_language**: Useful for vertical-specific use cases; currently omitted to keep the interface focused on dictation.
- **Channel options** (`multichannel`, `channel_count`): Hard-coded to the single-channel microphone flow.

**Recommended next candidates to surface in the UI**
- `keywords`: highlight domain-specific terms in interim output; low overhead when the vocabulary is tight.
- `summaries` / `topics`: can auto-generate high-level recaps for meeting-style dictation; good to expose as a post-processing toggle paired with higher-tier models.
- `redaction`: helpful when transcripts may contain PII; worth exposing if compliance is a concern.
- `diarize`: separates speakers when using multi-mic inputs or uploaded recordings; less relevant for single-speaker dictation but valuable if we later support call transcripts.

These options require verifying the Deepgram project’s plan supports them and, in some cases, coordinating backend changes to persist extra metadata.

Additions should be coordinated with the backend token request so the selected options are allowed in Deepgram projects and pricing plans.

### Deepgram Parameters
```javascript
const params = new URLSearchParams({
  model: 'nova-3',
  interim_results: 'true',
  smart_format: 'true',
  vad_events: 'true',
  utterance_end_ms: '1000',
  endpointing: '1000',
  encoding: 'opus'
});
```

## Event Types from Deepgram

### Endpointing vs Utterance vs Auto-Submit

- **Endpointing window (`endpointing`)** – Deepgram waits this many milliseconds of silence before it finalizes the *current* stream and emits a `speech_final` result. Shorter values produce faster final transcripts but can misfire in noisy rooms.
- **Utterance gap (`utterance_end_ms`)** – Controls how Deepgram chunks interim transcripts. When silence exceeds this gap it starts a new interim "utterance" while continuing to listen.
- **Auto-submit delay** – Our client-side buffer that waits after Deepgram finalizes before sending the message. This gives the user time to cancel or append text after endpointing has triggered.

### 1. SpeechStarted
- Indicates user began speaking
- No auto-submit action

### 2. Results (Interim)
- `is_final: false, speech_final: false`
- Provides real-time transcription
- Updates UI but no auto-submit

### 3. Results (Final)
- `is_final: true, speech_final: false`
- Confirmed transcript for that segment
- Updates `lastFinalTranscript` but no auto-submit

### 4. Results (Speech Final)
- `is_final: true, speech_final: true`
- **Definitive end-of-speech detection**
- **Triggers auto-submit** (primary method, respects configurable delay)

### 5. UtteranceEnd
- Separate event type (not in Results)
- **Backup end-of-speech detection**
- **Triggers auto-submit** only if no speech_final was received (after configurable delay)

## Noise Resilience Features

### Background Noise Handling
- **UtteranceEnd** ignores continuous background sounds
- **speech_final** uses advanced ML models for detection
- Both methods focus on speech patterns, not audio levels

### False Positive Prevention
- Dual detection prevents duplicate submissions
- State tracking ensures only one auto-submit per utterance
- Timeout resets prevent cross-utterance interference

### Household Environment Optimization
- Tuned for conversational AI use case
- Balanced timing (1000ms) for natural speech patterns
- Robust against common household noises

## Debugging and Logs

### Console Output
The implementation provides detailed logging for troubleshooting:

```
🎤 Deepgram message received: {type, is_final, speech_final, transcript}
🎤 speech_final=true detected - END OF UTTERANCE (definitive)
🎤 UtteranceEnd without speech_final - triggering auto-submit
🎤 Processing submit: {text, autoSubmitEnabled, willSubmit}
```

### Key Log Messages
- `SpeechStarted event` - User began speaking
- `Transcript received` - Real-time transcription updates
- `Final transcript updated` - Confirmed transcript segment
- `speech_final=true detected` - Primary detection triggered
- `UtteranceEnd without speech_final` - Backup detection triggered
- `Processing submit` - Form submission attempt

## Use Cases

### Optimal Scenarios
- **Conversational AI**: Natural dialog flow
- **Voice journaling**: Hands-free note taking
- **Voice commands**: Quick interactions
- **Accessibility**: Users who prefer voice input

### Environment Compatibility
- ✅ **Quiet rooms**: Both methods work excellently
- ✅ **TV/music background**: UtteranceEnd provides reliability
- ✅ **Phone calls nearby**: Word-timing based detection
- ✅ **Multiple speakers**: Focuses on primary microphone input
- ✅ **Varying speech patterns**: Adaptive timing

## Configuration Recommendations

### For Conversation Mode
```javascript
conversation: { enabled: true }
stt: {
  auto_submit: true,
  timeout_ms: 5000  // 5-second listening timeout
}
```

### For Quick Commands
```javascript
conversation: { enabled: false }
stt: {
  auto_submit: true,
  utterance_end_ms: 800,   // Faster detection
  endpointing: 800
}
```

### For Noisy Environments
```javascript
stt: {
  model: 'nova-3',         // Most accurate model
  vad_events: true,        // Better noise handling
  utterance_end_ms: 1200,  // Slightly longer for clarity
  endpointing: 1200
}
```

## Troubleshooting

### Auto-submit Not Working
1. Check Speech Settings: Ensure "Auto-submit on speech end" is enabled
2. Verify localStorage: Settings must be saved properly
3. Check console logs: Look for detection events
4. Test environment: Try in quieter space first

### Double Submissions
- Should not occur with current implementation
- State tracking prevents duplicate triggers
- Check for multiple event listeners

### Delayed Submissions
- Normal behavior: Deepgram needs time to detect speech end
- Adjust `utterance_end_ms` and `endpointing` for faster/slower detection
- Balance between accuracy and speed

### No Detection in Noisy Environment
- UtteranceEnd should handle this case
- Check VAD events are enabled
- Consider adjusting model settings

## Future Enhancements

### Potential Improvements
- **Adaptive timing**: Adjust detection based on user patterns
- **Context awareness**: Different settings for different conversation types
- **Learning system**: Improve detection based on user feedback
- **Multi-language support**: Optimize for different languages

### Advanced Features
- **Emotion detection**: Adjust timing based on speech emotion
- **Speaker identification**: Handle multi-user scenarios
- **Intent detection**: Different timing for questions vs statements
- **Background noise classification**: Adaptive algorithms for specific noise types

## Technical Architecture

### Dependencies
- **Deepgram API**: Real-time STT service
- **WebSocket**: Real-time communication
- **MediaRecorder API**: Audio capture
- **LocalStorage**: Settings persistence

### Browser Compatibility
- Modern browsers with WebRTC support
- Microphone permissions required
- WebSocket support required

### Performance Considerations
- Minimal latency impact
- Efficient state management
- Optimized event handling
- Memory cleanup on session end

---

## Summary

This implementation provides a robust, noise-resistant auto-submit feature that enables natural conversation flow with AI systems. By combining Deepgram's dual detection methods with intelligent state management, it delivers reliable speech-end detection across various household environments while preventing false positives and ensuring a smooth user experience.
