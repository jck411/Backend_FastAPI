from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stt", tags=["stt"])


class DeepgramToken(BaseModel):
    access_token: str
    expires_in: int | None = None


@router.post("/deepgram/token", response_model=DeepgramToken)
async def get_deepgram_token() -> DeepgramToken:
    logger.info("Deepgram token request received")
    settings = get_settings()
    if (
        not settings.deepgram_api_key
        or not settings.deepgram_api_key.get_secret_value()
    ):
        logger.error("Deepgram API key not configured")
        raise HTTPException(
            status_code=503, detail="Deepgram is not configured on server"
        )

    headers = {
        "Authorization": f"Token {settings.deepgram_api_key.get_secret_value()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"ttl_seconds": settings.deepgram_token_ttl_seconds}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.debug("Requesting Deepgram temporary token")
            resp = await client.post(
                "https://api.deepgram.com/v1/auth/grant", headers=headers, json=payload
            )
            logger.debug(f"Deepgram response status: {resp.status_code}")

            # Log request ID for debugging
            request_id = resp.headers.get("dg-request-id")
            if request_id:
                logger.debug(f"Deepgram request ID: {request_id}")

            if resp.status_code != 200:
                # Try to surface Deepgram error if present
                dg_error = resp.headers.get("dg-error")
                err_code = None
                err_msg = None
                body = None
                try:
                    body = resp.json()
                    # Deepgram uses err_code and err_msg in responses
                    err_code = body.get("err_code")
                    err_msg = body.get("err_msg") or body.get("error") or body.get("detail")
                    logger.error(
                        f"Deepgram error response: {body}"
                        + (f" (request_id: {request_id})" if request_id else "")
                    )
                except Exception:
                    pass

                # Optional dev fallback: return API key directly as a token so the browser can use Sec-WebSocket-Protocol auth
                if (
                    settings.deepgram_allow_apikey_fallback
                    and settings.deepgram_api_key
                ):
                    logger.warning("Using API key fallback for Deepgram token")
                    return DeepgramToken(
                        access_token=settings.deepgram_api_key.get_secret_value(),
                        expires_in=None,
                    )

                # Provide specific error messages based on status code
                if resp.status_code == 401:
                    if err_code == "FORBIDDEN" or "permission" in (err_msg or "").lower():
                        msg = "Deepgram API key lacks sufficient permissions (needs at least 'Member' role)"
                    else:
                        msg = "Deepgram API key is invalid or unauthorized"
                elif resp.status_code == 402:
                    msg = "Deepgram project has insufficient funds"
                elif resp.status_code == 403:
                    msg = "Deepgram API key lacks sufficient permissions for token generation"
                else:
                    msg = (
                        err_msg
                        or dg_error
                        or f"Deepgram token request failed ({resp.status_code})"
                    )

                logger.error(
                    f"Deepgram token request failed: {msg}"
                    + (f" [err_code: {err_code}]" if err_code else "")
                    + (f" (request_id: {request_id})" if request_id else "")
                )
                raise HTTPException(status_code=502, detail=msg)
            data = resp.json()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        logger.error(f"Deepgram request timed out: {exc}")
        raise HTTPException(
            status_code=504, detail="Deepgram request timed out"
        )
    except httpx.RequestError as exc:
        logger.error(f"Network error contacting Deepgram: {exc}")
        raise HTTPException(
            status_code=502, detail=f"Network error contacting Deepgram: {exc}"
        )
    except Exception as exc:
        logger.exception("Unexpected error in Deepgram token request")
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
