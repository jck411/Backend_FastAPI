
import asyncio
import re
from backend.services.text_segmenter import process_text_chunks

async def run_test():
    chunk_queue = asyncio.Queue()
    phrase_queue = asyncio.Queue()
    delimiters = ["\n", ". ", "? ", "! ", "* "]

    # Defaults from KioskTtsSettings
    character_max = 50
    use_segmentation = True

    print(f"Starting test with character_max={character_max}")

    # Create task
    task = asyncio.create_task(process_text_chunks(
        chunk_queue, phrase_queue, delimiters, use_segmentation, character_max
    ))

    # Simulate streaming text
    text_parts = [
        "Hello. ", # 7 chars. Should be segmented.
        "This is a test of the emergency broadcast system. ", # 49 chars. Total > 50.
        "This is the part that gets buffered forever until the end ",
        "because segmentation gets disabled. ",
        "It effectively kills streaming for long responses."
    ]

    for part in text_parts:
        print(f"Functions: sending chunk '{part}'")
        await chunk_queue.put(part)
        await asyncio.sleep(0.1)

        # Check output
        while not phrase_queue.empty():
            phrase = await phrase_queue.get()
            print(f"OUTPUT PHRASE: '{phrase}'")

    print("Sending None (End of stream)")
    await chunk_queue.put(None)

    # Wait for final
    while not task.done():
        try:
            phrase = await asyncio.wait_for(phrase_queue.get(), timeout=1.0)
            if phrase is None:
                break
            print(f"OUTPUT PHRASE: '{phrase}'")
        except asyncio.TimeoutError:
            break

    await task

if __name__ == "__main__":
    asyncio.run(run_test())
