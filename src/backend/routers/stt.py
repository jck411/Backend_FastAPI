from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
