"""Spotify authentication service.

OAuth 2.0 authentication flow for Spotify Web API using spotipy.
Mirrors the Google Workspace auth pattern for consistency.

Note: Spotify OAuth callback uses port 8888 (http://127.0.0.1:8888/callback).
Ensure this port is available and matches the redirect URI in credentials/spotify_credentials.json.
"""

from __future__ import annotations

import json
import os
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Default configuration
DEFAULT_USER_EMAIL = "jck411@gmail.com"

# Path settings
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "credentials"
TOKEN_PATH = PROJECT_ROOT / "data" / "tokens"

# Create token directory if it doesn't exist
os.makedirs(TOKEN_PATH, exist_ok=True)

# Spotify scopes for minimal playback control
# Documentation: https://developer.spotify.com/documentation/web-api/concepts/scopes
SCOPES = [
    "user-read-playback-state",  # Read current playback state
    "user-modify-playback-state",  # Control playback (play, pause, skip)
    "user-read-currently-playing",  # Read currently playing track
]

T = TypeVar("T")


def retry_on_rate_limit(
    max_retries: int = 3,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to retry Spotify API calls on rate limit (429) errors.

    Implements exponential backoff: 1s, 2s, 4s between retries.
    Works with both sync and async functions.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Check if the function is async
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except spotipy.exceptions.SpotifyException as e:
                        # Check for rate limit (429 Too Many Requests)
                        if e.http_status == 429 and attempt < max_retries - 1:
                            wait_time = 2**attempt  # 1s, 2s, 4s
                            await asyncio.sleep(wait_time)
                            continue
                        raise
                return await func(*args, **kwargs)  # Final attempt

            return async_wrapper  # type: ignore
        else:

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except spotipy.exceptions.SpotifyException as e:
                        # Check for rate limit (429 Too Many Requests)
                        if e.http_status == 429 and attempt < max_retries - 1:
                            wait_time = 2**attempt  # 1s, 2s, 4s
                            time.sleep(wait_time)
                            continue
                        raise
                return func(*args, **kwargs)  # Final attempt

            return sync_wrapper  # type: ignore

    return decorator


def get_spotify_config() -> dict[str, Any]:
    """Load Spotify OAuth configuration from credentials file.

    Returns:
        Dict containing client_id, client_secret, and redirect_uri

    Raises:
        FileNotFoundError: If spotify_credentials.json doesn't exist
    """
    config_path = CREDENTIALS_PATH / "spotify_credentials.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Spotify credentials not found at {config_path}. "
            "Please create this file with client_id, client_secret, and redirect_uri. "
            "See docs for setup instructions."
        )

    with open(config_path) as f:
        return json.load(f)


def get_token_path(user_email: str) -> Path:
    """Get the path where user's Spotify token should be stored.

    Args:
        user_email: User's email address, used to identify their token file

    Returns:
        Path to the user's token file
    """
    # Create sanitized filename from email (e.g., jck411_at_gmail_com_spotify.json)
    filename = user_email.replace("@", "_at_").replace(".", "_") + "_spotify.json"
    return TOKEN_PATH / filename


def get_credentials(user_email: str) -> Optional[dict[str, Any]]:
    """Get stored Spotify credentials for a user, refreshing if necessary.

    Spotipy handles token refresh automatically, but we check if the token
    file exists and is valid.

    Args:
        user_email: User's email address

    Returns:
        Token data dict if valid credentials exist, None otherwise
    """
    token_path = get_token_path(user_email)

    if not token_path.exists():
        return None

    try:
        with open(token_path) as token_file:
            token_data = json.load(token_file)

        # Basic validation - spotipy will handle refresh if expired
        if "access_token" not in token_data:
            return None

        return token_data
    except (json.JSONDecodeError, OSError):
        return None


def store_credentials(user_email: str, token_info: dict[str, Any]) -> None:
    """Store Spotify token data to file.

    Args:
        user_email: User's email address
        token_info: Token info dict from spotipy (contains access_token, refresh_token, etc.)
    """
    token_path = get_token_path(user_email)

    with open(token_path, "w") as token_file:
        json.dump(token_info, token_file, indent=2)


def get_spotify_client(user_email: str) -> spotipy.Spotify:
    """Get authenticated Spotify client for a user.

    Creates a Spotify client with OAuth authentication. The client will
    automatically refresh tokens when they expire.

    Args:
        user_email: User's email address

    Returns:
        Authenticated Spotify client

    Raises:
        ValueError: If no valid credentials are found for the user
    """
    credentials = get_credentials(user_email)

    if not credentials:
        raise ValueError(
            f"No valid Spotify credentials found for {user_email}. "
            "Click 'Connect Spotify' in Settings to authorize access."
        )

    try:
        config = get_spotify_config()

        auth_manager = SpotifyOAuth(
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            redirect_uri=config["redirect_uri"],
            scope=" ".join(SCOPES),
            cache_path=str(get_token_path(user_email)),
            open_browser=False,  # Don't auto-open browser for server context
        )

        # Spotipy handles token refresh automatically
        return spotipy.Spotify(auth_manager=auth_manager)

    except Exception as e:
        raise ValueError(f"Failed to create Spotify client for {user_email}: {e}")


def get_auth_url(user_email: str) -> str:
    """Generate Spotify OAuth authorization URL for a user.

    Args:
        user_email: User's email address (stored in state for callback verification)

    Returns:
        Authorization URL to redirect user to
    """
    config = get_spotify_config()

    auth_manager = SpotifyOAuth(
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        redirect_uri=config["redirect_uri"],
        scope=" ".join(SCOPES),
        cache_path=str(get_token_path(user_email)),
        open_browser=False,
        state=user_email,  # Pass user_email in state for verification
    )

    return auth_manager.get_authorize_url()


def process_auth_callback(code: str, user_email: str) -> dict[str, Any]:
    """Process OAuth callback and exchange code for tokens.

    Args:
        code: Authorization code from Spotify callback
        user_email: User's email address

    Returns:
        Token info dict containing access_token, refresh_token, etc.

    Raises:
        Exception: If token exchange fails
    """
    config = get_spotify_config()

    auth_manager = SpotifyOAuth(
        client_id=config["client_id"],
        client_secret=config["client_secret"],
        redirect_uri=config["redirect_uri"],
        scope=" ".join(SCOPES),
        cache_path=str(get_token_path(user_email)),
        open_browser=False,
    )

    # Exchange code for token
    token_info = auth_manager.get_access_token(code, as_dict=True)

    if not token_info:
        raise ValueError("Failed to exchange authorization code for tokens")

    # Store credentials
    store_credentials(user_email, token_info)

    return token_info
