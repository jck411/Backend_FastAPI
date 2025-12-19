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
    character_max: int,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """
    Process text chunks and segment them into phrases for TTS.

    Accumulates text chunks from chunk_queue and splits into phrases
    at delimiter boundaries. After character_max is reached, segmentation
    is disabled and remaining text is sent as a single chunk.

    Args:
        chunk_queue: Queue receiving text chunks from LLM
        phrase_queue: Queue to send segmented phrases to TTS
        delimiters: List of delimiter strings to split at
        use_segmentation: Whether to enable segmentation
        character_max: Max chars before disabling segmentation
        stop_event: Optional event to signal early stop
    """
    working_string = ""
    chars_processed = 0
    segmentation_active = use_segmentation

    delimiter_pattern = compile_delimiter_pattern(delimiters) if use_segmentation else None

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

            # Segment if enabled and pattern available
            if segmentation_active and delimiter_pattern:
                while True:
                    match = delimiter_pattern.search(working_string)
                    if match:
                        end_idx = match.end()
                        phrase = working_string[:end_idx].strip()
                        if phrase:
                            await phrase_queue.put(phrase)
                            chars_processed += len(phrase)
                            logger.info(f"Segment ({chars_processed} chars): '{phrase[:80]}...'")
                        working_string = working_string[end_idx:]

                        # Disable segmentation after character_max
                        # if chars_processed >= character_max:
                        #     segmentation_active = False
                        #     logger.debug(f"Segmentation disabled after {chars_processed} chars")
                        #     break
                    else:
                        break

    except Exception as e:
        logger.error(f"Text segmenter error: {e}")
        await phrase_queue.put(None)
        raise
