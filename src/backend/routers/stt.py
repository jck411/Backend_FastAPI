from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..config import get_settings

router = APIRouter(prefix="/api/stt", tags=["stt"])


class DeepgramToken(BaseModel):
    access_token: str
    expires_in: int | None = None


@router.post("/deepgram/token", response_model=DeepgramToken)
async def get_deepgram_token() -> DeepgramToken:
    settings = get_settings()
    if (
        not settings.deepgram_api_key
        or not settings.deepgram_api_key.get_secret_value()
    ):
        raise HTTPException(
            status_code=501, detail="Deepgram is not configured on server"
        )

    headers = {
        "Authorization": f"Token {settings.deepgram_api_key.get_secret_value()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    json = {"ttl_seconds": settings.deepgram_token_ttl_seconds}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/auth/grant", headers=headers, json=json
            )
            if resp.status_code != 200:
                # Try to surface Deepgram error if present
                dg_error = resp.headers.get("dg-error")
                detail = None
                body = None
                try:
                    body = resp.json()
                    detail = body.get("error") or body.get("detail")
                except Exception:
                    pass

                # Optional dev fallback: return API key directly as a token so the browser can use Sec-WebSocket-Protocol auth
                if (
                    settings.deepgram_allow_apikey_fallback
                    and settings.deepgram_api_key
                ):
                    return DeepgramToken(
                        access_token=settings.deepgram_api_key.get_secret_value(),
                        expires_in=None,
                    )

                msg = (
                    detail
                    or dg_error
                    or f"Deepgram token request failed ({resp.status_code})"
                )
                raise HTTPException(status_code=502, detail=msg)
            data = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to contact Deepgram: {exc}"
        )

    token = data.get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="Deepgram did not return a token")
    expires_in = data.get("expires_in")
    return DeepgramToken(
        access_token=token,
        expires_in=expires_in if isinstance(expires_in, int) else None,
    )


class WakewordDetected(BaseModel):
    phrase: str | None = None
    source: str | None = None


# In-memory subscriber queues for wakeword SSE
_wakeword_queues: set[asyncio.Queue[str]] = set()


async def _broadcast_wakeword(payload: dict) -> None:
    """Broadcast a wakeword event to all connected SSE clients."""
    data = json.dumps(payload)
    for q in list(_wakeword_queues):
        try:
            q.put_nowait(data)
        except Exception:
            # Ignore slow/overflowed clients
            pass


@router.get("/wakeword/stream")
async def wakeword_stream() -> EventSourceResponse:
    """
    Server-Sent Events stream for wakeword detections.
    Frontend connects when wakeword is enabled; on event, it mimics mic button press.
    """
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=16)
    _wakeword_queues.add(queue)

    async def event_generator():
        try:
            while True:
                data = await queue.get()
                yield {"event": "wakeword", "data": data}
        except asyncio.CancelledError:
            # client disconnected
            pass
        finally:
            _wakeword_queues.discard(queue)

    # Send periodic pings to keep connections alive
    return EventSourceResponse(event_generator(), ping=15)


@router.post("/wakeword/detected")
async def wakeword_detected(event: WakewordDetected) -> dict[str, str]:
    """
    Hook for the local wakeword listener process to notify the backend.
    Broadcasts to any connected SSE clients.
    """
    payload = {
        "type": "wakeword",
        "phrase": (event.phrase or "computer"),
        "source": (event.source or "listener"),
        "ts": time.time(),
    }
    await _broadcast_wakeword(payload)
    return {"status": "ok"}


# ---------------- Wakeword listener process management (server-managed) ----------------

# Project/Test_Frontend paths
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_DIR = _PROJECT_ROOT / "Test_Frontend"

# Singleton process + lock
_wakeword_proc: subprocess.Popen | None = None
_wakeword_lock: asyncio.Lock = asyncio.Lock()


def _proc_running() -> bool:
    try:
        return _wakeword_proc is not None and _wakeword_proc.poll() is None
    except Exception:
        return False


@router.get("/wakeword/listener/status")
async def wakeword_listener_status() -> dict[str, bool]:
    """Return whether the wakeword listener process is running."""
    return {"running": _proc_running()}


@router.post("/wakeword/listener/start")
async def wakeword_listener_start() -> dict[str, str | bool]:
    """Start the Node wakeword listener as a background process."""
    global _wakeword_proc
    async with _wakeword_lock:
        if _proc_running():
            return {"status": "already_running", "running": True}

        script_rel = Path("STT/Wakeword/wakeword_listiner_no_key.cjs")
        script_path = _FRONTEND_DIR / script_rel
        if not script_path.exists():
            raise HTTPException(
                status_code=500, detail=f"Wakeword script missing: {script_path}"
            )

        env = os.environ.copy()
        env.setdefault("BACKEND_URL", "http://localhost:8000/api/stt/wakeword/detected")

        try:
            # Detach stdio so it doesn't block the server; start in Test_Frontend dir
            _wakeword_proc = subprocess.Popen(
                ["node", str(script_rel)],
                cwd=str(_FRONTEND_DIR),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail="Node.js not found. Install node to use wakeword.",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to start wakeword listener: {exc}"
            )

        return {"status": "started", "running": _proc_running()}


@router.post("/wakeword/listener/stop")
async def wakeword_listener_stop() -> dict[str, str | bool]:
    """Stop the Node wakeword listener process if running."""
    global _wakeword_proc
    async with _wakeword_lock:
        # Snapshot the proc and validate it's actually running
        proc = _wakeword_proc
        if proc is None or proc.poll() is not None:
            _wakeword_proc = None
            return {"status": "not_running", "running": False}

        try:
            # Terminate the whole process group
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=3.0)
            except Exception:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            # Best-effort stop; proceed to clear handle
            pass
        finally:
            _wakeword_proc = None

        return {"status": "stopped", "running": False}
