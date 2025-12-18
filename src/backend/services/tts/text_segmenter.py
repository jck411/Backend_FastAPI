"""
Text Segmenter for Streaming TTS Pipeline.

This module provides real-time text segmentation for streaming TTS applications.
It splits incoming text chunks into phrases at delimiter boundaries, ensuring
a minimum character threshold before emitting phrases.

Architecture:
    LLM Chunks → TextSegmenter.consume() → phrase_queue

The segmenter is designed to minimize time-to-first-audio by emitting phrases
as soon as possible while maintaining natural speech boundaries.

Usage:
    segmenter = TextSegmenter(min_chars=25, delimiters=['. ', '? ', '! ', '\\n'])

    # During LLM streaming:
    for chunk in llm_response:
        for phrase in segmenter.consume(chunk):
            await phrase_queue.put(phrase)

    # After streaming completes:
    final = segmenter.flush()
    if final:
        await phrase_queue.put(final)
    await phrase_queue.put(None)  # Signal end
"""

import re
from typing import Iterator, List, Optional


class TextSegmenter:
    """
    Stateful text segmenter that splits streaming text into phrases.

    Emits phrases at delimiter boundaries (., ?, !, newline) but only after
    accumulating a minimum number of characters. This balances latency
    (emitting phrases quickly) with natural speech patterns (complete sentences).

    Attributes:
        min_chars: Minimum characters before a split is allowed (default: 25)
        delimiters: List of delimiter strings that trigger splits
    """

    # Default delimiters for sentence boundaries
    DEFAULT_DELIMITERS = ['. ', '? ', '! ', '.\n', '?\n', '!\n', '\n']

    def __init__(
        self,
        min_chars: int = 25,
        delimiters: Optional[List[str]] = None
    ):
        """
        Initialize the segmenter.

        Args:
            min_chars: Minimum characters required before emitting a phrase.
                       The segmenter will NOT split until at least this many
                       characters have been accumulated.
            delimiters: List of delimiter strings. Defaults to sentence-ending
                       punctuation followed by space or newline.
        """
        self.min_chars = min_chars
        self.delimiters = delimiters or self.DEFAULT_DELIMITERS
        self._buffer = ""
        self._delimiter_pattern = self._compile_pattern(self.delimiters)
        self._total_emitted = 0

    @staticmethod
    def _compile_pattern(delimiters: List[str]) -> re.Pattern:
        """Compile regex pattern for delimiter matching."""
        # Sort by length (longest first) to match longer delimiters first
        sorted_delims = sorted(delimiters, key=len, reverse=True)
        escaped = [re.escape(d) for d in sorted_delims]
        return re.compile('|'.join(escaped))

    def consume(self, chunk: str) -> Iterator[str]:
        """
        Consume a text chunk and yield any complete phrases.

        This method should be called for each chunk received from the LLM.
        It buffers text until a delimiter is found after the minimum character
        threshold, then yields the phrase.

        Args:
            chunk: Text chunk from LLM streaming response

        Yields:
            Complete phrases ready for TTS synthesis
        """
        if not chunk:
            return

        self._buffer += chunk

        # Keep extracting phrases while we find delimiters past min_chars
        while True:
            # Only search for delimiters after min_chars position
            if len(self._buffer) < self.min_chars:
                break

            # Search for delimiter starting from min_chars position
            match = self._delimiter_pattern.search(self._buffer, pos=self.min_chars)
            if not match:
                break

            # Extract phrase up to and including the delimiter
            end_pos = match.end()
            phrase = self._buffer[:end_pos].strip()
            self._buffer = self._buffer[end_pos:]

            if phrase:
                self._total_emitted += len(phrase)
                yield phrase

    def flush(self) -> Optional[str]:
        """
        Flush any remaining buffered text.

        Call this after LLM streaming completes to get the final phrase
        that may not have ended with a delimiter.

        Returns:
            Remaining text if any, None otherwise
        """
        if self._buffer.strip():
            phrase = self._buffer.strip()
            self._buffer = ""
            self._total_emitted += len(phrase)
            return phrase
        return None

    def reset(self) -> None:
        """Reset segmenter state for reuse."""
        self._buffer = ""
        self._total_emitted = 0

    @property
    def total_emitted_chars(self) -> int:
        """Total characters emitted across all phrases."""
        return self._total_emitted

    @property
    def buffer_size(self) -> int:
        """Current buffer size in characters."""
        return len(self._buffer)
