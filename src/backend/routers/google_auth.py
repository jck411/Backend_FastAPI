"""Router for Google OAuth operations."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from backend.config import get_settings
from backend.services.google_auth.auth import (
    authorize_user,
    get_credentials,
    process_auth_callback,
)

router = APIRouter()


class AuthorizationRequest(BaseModel):
    """Request to start Google authorization."""

    user_email: str
    redirect_uri: Optional[str] = (
        None  # If not provided, will use the default from settings
    )


class AuthorizationResponse(BaseModel):
    """Response with authorization URL."""

    auth_url: str


class TokenResponse(BaseModel):
    """Response after successful token acquisition."""

    success: bool
    message: str


@router.post("/authorize", response_model=AuthorizationResponse)
async def start_authorization(request: AuthorizationRequest):
    """
    Start the Google OAuth authorization flow.

    Returns a URL that the user should visit to authorize access.
    """
    settings = get_settings()

    # Use provided redirect URI or fallback to default
    redirect_uri = request.redirect_uri or settings.google_oauth_redirect_uri

    try:
        auth_url = authorize_user(request.user_email, redirect_uri)
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create authorization URL: {str(e)}"
        )


@router.get("/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),  # state contains user_email
    error: str = Query(None),
):
    """
    Handle the OAuth callback from Google.

    This endpoint should match the redirect_uri used in the authorize endpoint.
    """
    settings = get_settings()

    if error:
        return RedirectResponse(f"{settings.frontend_url}?auth_error={error}")

    try:
        # Use the state parameter as the user_email (in a real app, verify this is secure)
        user_email = state

        # Process the authorization code to get credentials
        # Store credentials and validate they work
        process_auth_callback(code, user_email, settings.google_oauth_redirect_uri)

        # Redirect back to the frontend with success message
        return RedirectResponse(
            f"{settings.frontend_url}?auth_success=true&email={user_email}"
        )

    except Exception as e:
        # Redirect with error information
        return RedirectResponse(f"{settings.frontend_url}?auth_error={str(e)}")


@router.get("/status/{user_email}")
async def check_auth_status(user_email: str):
    """
    Check if a user has valid credentials stored.

    Returns the authorization status for the given email.
    """
    try:
        credentials = get_credentials(user_email)

        if credentials:
            return {
                "authorized": True,
                "expires_at": credentials.expiry.isoformat()
                if credentials.expiry
                else None,
            }
        else:
            return {"authorized": False}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to check authorization status: {str(e)}"
        )
