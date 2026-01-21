"""Text segmentation utility for TTS processing pipeline."""

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def compile_delimiter_pattern(delimiters: list[str]) -> Optional[re.Pattern]:
    """
    Compile a regex pattern from a list of delimiters.

    Delimiters are sorted by length (longest first) to ensure proper matching.
    """
    if not delimiters:
        return None
    sorted_delims = sorted(delimiters, key=len, reverse=True)
    escaped = map(re.escape, sorted_delims)
    pattern = "|".join(escaped)
    return re.compile(pattern)


async def process_text_chunks(
    chunk_queue: asyncio.Queue,
    phrase_queue: asyncio.Queue,
    delimiters: list[str],
    use_segmentation: bool,
    first_phrase_min_chars: int,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Process text chunks and segment them into phrases for TTS.

    Accumulates text chunks from chunk_queue and emits the first phrase
    once a delimiter or whitespace occurs and the minimum character threshold
    is met. If no boundary appears shortly after the minimum, it emits what is
    available to minimize latency. The remaining text is sent as a single
    final chunk to keep the pipeline at most two phrases.

    Args:
        chunk_queue: Queue receiving text chunks from LLM
        phrase_queue: Queue to send segmented phrases to TTS
        delimiters: List of delimiter strings to split at
        use_segmentation: Whether to enable segmentation
        first_phrase_min_chars: Minimum characters before emitting the first segmented phrase
        stop_event: Optional event to signal early stop
    """
    working_string = ""
    chars_processed = 0
    segmentation_active = use_segmentation
    first_phrase_emitted = not use_segmentation
    min_ready_at: Optional[float] = None

    delimiter_pattern = compile_delimiter_pattern(delimiters) if use_segmentation else None
    whitespace_pattern = re.compile(r"\s+")
    loop = asyncio.get_running_loop()
    max_wait_seconds = 0.25

    async def maybe_emit_first_phrase() -> None:
        nonlocal working_string, segmentation_active, first_phrase_emitted, chars_processed, min_ready_at

        if not segmentation_active or first_phrase_emitted:
            return
        if not working_string:
            return
        if len(working_string) < first_phrase_min_chars:
            return

        if min_ready_at is None:
            min_ready_at = loop.time()

        delimiter_match = (
            delimiter_pattern.search(working_string, first_phrase_min_chars)
            if delimiter_pattern
            else None
        )
        whitespace_match = whitespace_pattern.search(
            working_string, first_phrase_min_chars
        )

        split_candidates = []
        if delimiter_match:
            split_candidates.append(delimiter_match.end())
        if whitespace_match:
            split_candidates.append(whitespace_match.end())

        split_idx = min(split_candidates) if split_candidates else None
        if split_idx is None and min_ready_at is not None:
            if loop.time() - min_ready_at >= max_wait_seconds:
                split_idx = len(working_string)

        if split_idx is None:
            return

        raw_phrase = working_string[:split_idx]
        phrase = raw_phrase.strip()
        if not phrase:
            working_string = working_string[split_idx:]
            min_ready_at = None
            return

        if len(raw_phrase) < first_phrase_min_chars:
            return

        await phrase_queue.put(phrase)
        chars_processed += len(phrase)
        logger.info(f"Segment ({chars_processed} chars): '{phrase[:80]}...'")
        working_string = working_string[split_idx:]
        segmentation_active = False
        first_phrase_emitted = True
        min_ready_at = None

    try:
        while True:
            # Check stop event
            if stop_event and stop_event.is_set():
                logger.debug("Text segmenter: stop event triggered")
                break

            # Get next chunk (with timeout to check stop event)
            try:
                chunk = await asyncio.wait_for(chunk_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                await maybe_emit_first_phrase()
                continue

            # None signals end of text
            if chunk is None:
                if working_string.strip():
                    phrase = working_string.strip()
                    await phrase_queue.put(phrase)
                    logger.info(f"Final segment: '{phrase[:80]}...'")
                await phrase_queue.put(None)
                break

            # Accumulate the chunk
            working_string += chunk

            # Segment only until the first phrase is emitted
            if segmentation_active and not first_phrase_emitted:
                await maybe_emit_first_phrase()

    except Exception as e:
        logger.error(f"Text segmenter error: {e}")
        await phrase_queue.put(None)
        raise
