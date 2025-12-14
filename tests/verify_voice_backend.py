import asyncio
import base64
import json
import logging
import sys

import websockets

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestClient")

BACKEND_URL = "ws://localhost:8000/api/voice/connect?client_id=test_script"

async def test_voice_loop():
    logger.info(f"Connecting to {BACKEND_URL}...")
    try:
        async with websockets.connect(BACKEND_URL) as websocket:
            logger.info("Connected!")

            # 1. Send connection_ready
            await websocket.send(json.dumps({
                "type": "connection_ready"
            }))
            logger.info("Sent connection_ready")

            # 2. Send wakeword_detected
            # This triggers the backend to start an STT session
            await websocket.send(json.dumps({
                "type": "wakeword_detected"
            }))
            logger.info("Sent wakeword_detected")

            # 3. Simulate streaming audio
            # We don't have real audio bytes easily, but Deepgram might error on silence/garbage
            # or just return empty transcripts.
            # Ideally we'd send a wav file if we had one.
            # Let's try sending a few chunks of silence (0x00)
            # 16kHz 16-bit mono = 32000 bytes/sec
            # Send 100ms chunks = 3200 bytes

            silence_chunk = bytes(3200)
            b64_data = base64.b64encode(silence_chunk).decode('utf-8')

            for _ in range(5):
                await websocket.send(json.dumps({
                    "type": "audio_chunk",
                    "data": b64_data
                }))
                await asyncio.sleep(0.1)

            logger.info("Sent 0.5s of silence")

            # 4. End Stream
            await websocket.send(json.dumps({
                "type": "stream_end"
            }))
            logger.info("Sent stream_end")

            # 5. Listen for responses
            # Since we sent silence, we probably won't get a transcript -> TTS response
            # But we can check if we get disconnected or errors.

            # To *really* test TTS, we might need to mock the STT service to return a fake transcript
            # OR we rely on Deepgram potentially returning *something* or at least "connection established" logs in backend.

            wait_time = 5
            logger.info(f"Listening for {wait_time} seconds...")

            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=wait_time)
                data = json.loads(msg)
                logger.info(f"Received message: {data.get('type')}")
                if data.get('type') == 'tts_audio':
                    logger.info("✅ SUCCESS: Received TTS Audio!")
                return
            except asyncio.TimeoutError:
                logger.info("No response received (expected if sending silence)")

    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_voice_loop())
