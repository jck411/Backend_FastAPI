"""
TTS (Text-to-Speech) Services Package.

This package contains modules for streaming TTS processing:

- text_segmenter: Splits streaming LLM text into phrases for TTS
- tts_processor: Queue-based TTS processing pipeline

Architecture Overview:

    ┌─────────────┐     ┌───────────────┐     ┌─────────────┐     ┌───────────┐
    │ LLM Stream  │────▶│ TextSegmenter │────▶│ phrase_queue│────▶│TTSProcessor│
    └─────────────┘     └───────────────┘     └─────────────┘     └─────────────┘
                                                                         │
                                                                         ▼
                                                                  ┌─────────────┐
                                                                  │ audio_queue │
                                                                  └─────────────┘
                                                                         │
                                                                         ▼
                                                                  ┌─────────────┐
                                                                  │  WebSocket  │
                                                                  │  Broadcast  │
                                                                  └─────────────┘

The pipeline is designed for minimal time-to-first-audio:
1. TextSegmenter emits phrases as soon as a delimiter is found (min 25 chars)
2. TTSProcessor immediately starts synthesis for each phrase
3. Audio chunks are broadcast via WebSocket as they arrive from TTS provider
4. Frontend plays audio chunks immediately using Web Audio API
"""

from .text_segmenter import TextSegmenter
from .tts_processor import TTSProcessor

__all__ = ["TextSegmenter", "TTSProcessor"]
