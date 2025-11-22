"""Custom MCP server for Spotify integration.

Provides tools for searching tracks, controlling playback, and managing Spotify content.

OAuth Note: Spotify OAuth callback uses port 8888 (http://127.0.0.1:8888/callback).
Ensure this port is available when authorizing through Settings.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from mcp.server.fastmcp import FastMCP

from backend.services.spotify_auth.auth import (
    DEFAULT_USER_EMAIL,
    get_spotify_client,
    retry_on_rate_limit,
)

mcp = FastMCP("spotify")


def _format_track_info(track: dict) -> str:
    """Format track information for display.

    Args:
        track: Track object from Spotify API

    Returns:
        Formatted string with track details
    """
    name = track.get("name", "Unknown")
    artists = ", ".join(
        artist.get("name", "Unknown") for artist in track.get("artists", [])
    )
    album = track.get("album", {}).get("name", "Unknown")
    url = track.get("external_urls", {}).get("spotify", "")
    uri = track.get("uri", "")
    duration_ms = track.get("duration_ms", 0)
    duration_min = duration_ms // 60000
    duration_sec = (duration_ms % 60000) // 1000

    return (
        f"Track: {name}\n"
        f"Artist: {artists}\n"
        f"Album: {album}\n"
        f"Duration: {duration_min}:{duration_sec:02d}\n"
        f"URI: {uri}\n"
        f"Link: {url}"
    )


@mcp.tool("spotify_search_tracks")
@retry_on_rate_limit(max_retries=3)
async def search_tracks(
    query: str,
    user_email: str = DEFAULT_USER_EMAIL,
    limit: int = 10,
) -> str:
    """Search Spotify for tracks by query string.

    Searches track names, artist names, and album names. Returns track details
    including name, artist, album, duration, and Spotify URL.

    Args:
        query: Search terms (e.g., "bohemian rhapsody queen", "jazz piano")
        user_email: User's email for authentication (default: jck411@gmail.com)
        limit: Maximum number of results to return (default: 10, max: 50)

    Returns:
        Formatted list of tracks with metadata and Spotify links
    """
    try:
        sp = get_spotify_client(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Click 'Connect Spotify' in Settings to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Spotify client: {exc}"

    try:
        results = await asyncio.to_thread(
            sp.search, q=query, type="track", limit=min(limit, 50)
        )
    except Exception as exc:
        return f"Error searching Spotify: {exc}"

    if not results or not isinstance(results, dict):
        return "Invalid response from Spotify API"

    tracks_data = results.get("tracks", {})
    if not isinstance(tracks_data, dict):
        return "Invalid tracks data from Spotify API"

    tracks = tracks_data.get("items", [])

    if not tracks:
        return f"No tracks found for query '{query}'"

    lines = [
        f"Found {len(tracks)} track(s) for '{query}':",
        "",
    ]

    for idx, track in enumerate(tracks, start=1):
        lines.append(f"{idx}.")
        lines.append(_format_track_info(track))
        lines.append("")

    return "\n".join(lines)


@mcp.tool("spotify_get_current_playback")
@retry_on_rate_limit(max_retries=3)
async def get_current_playback(
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Get information about the user's current Spotify playback.

    Returns details about what's currently playing, including track info,
    playback state (playing/paused), device, shuffle/repeat status, and progress.

    Args:
        user_email: User's email for authentication (default: jck411@gmail.com)

    Returns:
        Formatted playback information or message if nothing is playing
    """
    try:
        sp = get_spotify_client(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Click 'Connect Spotify' in Settings to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Spotify client: {exc}"

    try:
        playback = await asyncio.to_thread(sp.current_playback)
    except Exception as exc:
        return f"Error getting current playback: {exc}"

    if not playback or not playback.get("item"):
        return "No track currently playing"

    track = playback["item"]
    is_playing = playback.get("is_playing", False)
    device = playback.get("device", {})
    shuffle = playback.get("shuffle_state", False)
    repeat = playback.get("repeat_state", "off")
    progress_ms = playback.get("progress_ms", 0)
    progress_min = progress_ms // 60000
    progress_sec = (progress_ms % 60000) // 1000

    lines = [
        "Current Playback:",
        "",
        _format_track_info(track),
        "",
        f"Status: {'Playing' if is_playing else 'Paused'}",
        f"Device: {device.get('name', 'Unknown')} ({device.get('type', 'Unknown')})",
        f"Volume: {device.get('volume_percent', 'N/A')}%",
        f"Shuffle: {'On' if shuffle else 'Off'}",
        f"Repeat: {repeat}",
        f"Progress: {progress_min}:{progress_sec:02d}",
    ]

    return "\n".join(lines)


@mcp.tool("spotify_play_track")
@retry_on_rate_limit(max_retries=3)
async def play_track(
    track_uri: str,
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Start playing a specific track on Spotify.

    Args:
        track_uri: Spotify track URI (e.g., "spotify:track:6rqhFgbbKwnb9MLmUQDhG6")
                   or Spotify track URL (e.g., "https://open.spotify.com/track/...")
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID to play on (default: active device)

    Returns:
        Confirmation message or error
    """
    try:
        sp = get_spotify_client(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Click 'Connect Spotify' in Settings to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Spotify client: {exc}"

    # Convert URL to URI if needed
    if track_uri.startswith("https://open.spotify.com/track/"):
        track_id = track_uri.split("/")[-1].split("?")[0]
        track_uri = f"spotify:track:{track_id}"

    try:
        await asyncio.to_thread(
            sp.start_playback, uris=[track_uri], device_id=device_id
        )
    except Exception as exc:
        return f"Error playing track: {exc}. Make sure Spotify is open on a device."

    # Get track info to confirm
    try:
        track_id = track_uri.split(":")[-1]
        track = await asyncio.to_thread(sp.track, track_id)
        if track and isinstance(track, dict):
            track_name = track.get("name", "Unknown")
            artists = ", ".join(
                artist.get("name", "Unknown") for artist in track.get("artists", [])
            )
            return f"Now playing: {track_name} by {artists}"
        return f"Started playback of {track_uri}"
    except Exception:
        return f"Started playback of {track_uri}"


@mcp.tool("spotify_pause")
@retry_on_rate_limit(max_retries=3)
async def pause_playback(
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Pause Spotify playback.

    Args:
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID to pause (default: active device)

    Returns:
        Confirmation message or error
    """
    try:
        sp = get_spotify_client(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Click 'Connect Spotify' in Settings to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Spotify client: {exc}"

    try:
        await asyncio.to_thread(sp.pause_playback, device_id=device_id)
    except Exception as exc:
        return f"Error pausing playback: {exc}. Make sure Spotify is open and playing."

    return "Playback paused"


def run() -> None:  # pragma: no cover - integration entrypoint
    """Run the Spotify MCP server."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "run",
    "search_tracks",
    "get_current_playback",
    "play_track",
    "pause_playback",
]
