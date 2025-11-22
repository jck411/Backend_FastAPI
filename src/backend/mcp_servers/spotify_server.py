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


@mcp.tool("spotify_resume")
@retry_on_rate_limit(max_retries=3)
async def resume_playback(
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Resume paused Spotify playback.

    Args:
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID to resume on (default: active device)

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
        await asyncio.to_thread(sp.start_playback, device_id=device_id)
    except Exception as exc:
        return f"Error resuming playback: {exc}. Make sure Spotify is open on a device."

    return "Playback resumed"


@mcp.tool("spotify_next_track")
@retry_on_rate_limit(max_retries=3)
async def next_track(
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Skip to the next track in Spotify playback.

    Args:
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID (default: active device)

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
        await asyncio.to_thread(sp.next_track, device_id=device_id)
    except Exception as exc:
        return f"Error skipping to next track: {exc}. Make sure Spotify is open and playing."

    return "Skipped to next track"


@mcp.tool("spotify_previous_track")
@retry_on_rate_limit(max_retries=3)
async def previous_track(
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Go back to the previous track in Spotify playback.

    Args:
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID (default: active device)

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
        await asyncio.to_thread(sp.previous_track, device_id=device_id)
    except Exception as exc:
        return f"Error going to previous track: {exc}. Make sure Spotify is open and playing."

    return "Went back to previous track"


@mcp.tool("spotify_shuffle")
@retry_on_rate_limit(max_retries=3)
async def set_shuffle(
    state: bool,
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Toggle shuffle mode for Spotify playback.

    Args:
        state: True to enable shuffle, False to disable
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID (default: active device)

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
        await asyncio.to_thread(sp.shuffle, state, device_id=device_id)
    except Exception as exc:
        return f"Error setting shuffle: {exc}. Make sure Spotify is open and playing."

    return f"Shuffle {'enabled' if state else 'disabled'}"


@mcp.tool("spotify_repeat")
@retry_on_rate_limit(max_retries=3)
async def set_repeat(
    state: str,
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Set repeat mode for Spotify playback.

    Args:
        state: Repeat mode - "track" (repeat current track), "context" (repeat playlist/album), or "off"
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID (default: active device)

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

    # Validate state
    valid_states = ["track", "context", "off"]
    if state not in valid_states:
        return (
            f"Invalid repeat state '{state}'. Must be one of: {', '.join(valid_states)}"
        )

    try:
        await asyncio.to_thread(sp.repeat, state, device_id=device_id)
    except Exception as exc:
        return (
            f"Error setting repeat mode: {exc}. Make sure Spotify is open and playing."
        )

    return f"Repeat mode set to '{state}'"


@mcp.tool("spotify_seek_position")
@retry_on_rate_limit(max_retries=3)
async def seek_position(
    position_ms: int,
    user_email: str = DEFAULT_USER_EMAIL,
    device_id: Optional[str] = None,
) -> str:
    """Seek to a specific position in the currently playing track.

    Args:
        position_ms: Position in milliseconds (e.g., 30000 for 30 seconds)
        user_email: User's email for authentication (default: jck411@gmail.com)
        device_id: Optional device ID (default: active device)

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

    # Ensure non-negative position
    position_ms = max(0, position_ms)
    position_min = position_ms // 60000
    position_sec = (position_ms % 60000) // 1000

    try:
        await asyncio.to_thread(sp.seek_track, position_ms, device_id=device_id)
    except Exception as exc:
        return (
            f"Error seeking to position: {exc}. Make sure Spotify is open and playing."
        )

    return f"Seeked to {position_min}:{position_sec:02d}"


@mcp.tool("spotify_get_user_playlists")
@retry_on_rate_limit(max_retries=3)
async def get_user_playlists(
    user_email: str = DEFAULT_USER_EMAIL,
    limit: int = 50,
) -> str:
    """Get a list of the user's Spotify playlists.

    Args:
        user_email: User's email for authentication (default: jck411@gmail.com)
        limit: Maximum number of playlists to return (default: 50, max: 50)

    Returns:
        Formatted list of playlists with names, track counts, and URLs
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
            sp.current_user_playlists, limit=min(limit, 50)
        )
    except Exception as exc:
        return f"Error fetching playlists: {exc}"

    if not results or not isinstance(results, dict):
        return "Invalid response from Spotify API"

    playlists = results.get("items", [])

    if not playlists:
        return "No playlists found"

    lines = [f"Found {len(playlists)} playlist(s):", ""]

    for idx, playlist in enumerate(playlists, start=1):
        name = playlist.get("name", "Unknown")
        track_count = playlist.get("tracks", {}).get("total", 0)
        playlist_id = playlist.get("id", "")
        uri = playlist.get("uri", "")
        url = playlist.get("external_urls", {}).get("spotify", "")
        owner = playlist.get("owner", {}).get("display_name", "Unknown")
        public = playlist.get("public", False)

        lines.append(f"{idx}. {name}")
        lines.append(f"   Owner: {owner}")
        lines.append(f"   Tracks: {track_count}")
        lines.append(f"   Public: {'Yes' if public else 'No'}")
        lines.append(f"   ID: {playlist_id}")
        lines.append(f"   URI: {uri}")
        lines.append(f"   Link: {url}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool("spotify_get_playlist_tracks")
@retry_on_rate_limit(max_retries=3)
async def get_playlist_tracks(
    playlist_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
    limit: int = 50,
) -> str:
    """Get tracks from a Spotify playlist.

    Args:
        playlist_id: Spotify playlist ID or URI (e.g., "37i9dQZF1DXcBWIGoYBM5M" or "spotify:playlist:...")
        user_email: User's email for authentication (default: jck411@gmail.com)
        limit: Maximum number of tracks to return (default: 50, max: 100)

    Returns:
        Formatted list of tracks with details
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

    # Extract playlist ID from URI if needed
    if playlist_id.startswith("spotify:playlist:"):
        playlist_id = playlist_id.split(":")[-1]
    elif "open.spotify.com/playlist/" in playlist_id:
        playlist_id = playlist_id.split("/")[-1].split("?")[0]

    try:
        # Get playlist details
        playlist_info = await asyncio.to_thread(
            sp.playlist, playlist_id, fields="name,tracks.total"
        )
        if not isinstance(playlist_info, dict):
            return "Error: Invalid playlist info response"

        playlist_name = playlist_info.get("name", "Unknown Playlist")
        total_tracks = playlist_info.get("tracks", {}).get("total", 0)

        # Get tracks
        results = await asyncio.to_thread(
            sp.playlist_tracks, playlist_id, limit=min(limit, 100)
        )
    except Exception as exc:
        return f"Error fetching playlist tracks: {exc}"

    if not results or not isinstance(results, dict):
        return "Invalid response from Spotify API"

    items = results.get("items", [])

    if not items:
        return f"No tracks found in playlist '{playlist_name}'"

    lines = [
        f"Playlist: {playlist_name}",
        f"Total tracks: {total_tracks} (showing {len(items)})",
        "",
    ]

    for idx, item in enumerate(items, start=1):
        track = item.get("track")
        if not track:
            continue

        added_by = item.get("added_by", {}).get("id", "Unknown")

        lines.append(f"{idx}.")
        lines.append(_format_track_info(track))
        lines.append(f"Added by: {added_by}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool("spotify_create_playlist")
@retry_on_rate_limit(max_retries=3)
async def create_playlist(
    name: str,
    description: str = "",
    public: bool = False,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Create a new Spotify playlist for the user.

    Args:
        name: Name of the new playlist
        description: Optional description for the playlist
        public: Whether the playlist should be public (default: False/private)
        user_email: User's email for authentication (default: jck411@gmail.com)

    Returns:
        Confirmation message with playlist details and URL
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
        # Get current user ID
        user_info = await asyncio.to_thread(sp.current_user)
        if not isinstance(user_info, dict):
            return "Error: Invalid user info response"

        user_id = user_info.get("id")

        if not user_id:
            return "Error: Could not get user ID"

        # Create playlist
        playlist = await asyncio.to_thread(
            sp.user_playlist_create,
            user_id,
            name,
            public=public,
            description=description,
        )
    except Exception as exc:
        return f"Error creating playlist: {exc}"

    if not playlist or not isinstance(playlist, dict):
        return "Error creating playlist: Invalid response"

    playlist_name = playlist.get("name", name)
    playlist_id = playlist.get("id", "")
    playlist_url = playlist.get("external_urls", {}).get("spotify", "")
    playlist_uri = playlist.get("uri", "")

    return (
        f"Created playlist: {playlist_name}\n"
        f"ID: {playlist_id}\n"
        f"URI: {playlist_uri}\n"
        f"Public: {'Yes' if public else 'No'}\n"
        f"Link: {playlist_url}"
    )


@mcp.tool("spotify_add_tracks_to_playlist")
@retry_on_rate_limit(max_retries=3)
async def add_tracks_to_playlist(
    playlist_id: str,
    track_uris: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Add tracks to a Spotify playlist.

    Args:
        playlist_id: Spotify playlist ID or URI (e.g., "37i9dQZF1DXcBWIGoYBM5M" or "spotify:playlist:...")
        track_uris: Comma-separated list of track URIs or URLs (e.g., "spotify:track:abc123,spotify:track:def456")
        user_email: User's email for authentication (default: jck411@gmail.com)

    Returns:
        Confirmation message with number of tracks added
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

    # Extract playlist ID from URI if needed
    if playlist_id.startswith("spotify:playlist:"):
        playlist_id = playlist_id.split(":")[-1]
    elif "open.spotify.com/playlist/" in playlist_id:
        playlist_id = playlist_id.split("/")[-1].split("?")[0]

    # Parse track URIs
    track_list = [uri.strip() for uri in track_uris.split(",") if uri.strip()]

    if not track_list:
        return "Error: No track URIs provided"

    # Convert URLs to URIs if needed
    normalized_uris = []
    for uri in track_list:
        if uri.startswith("https://open.spotify.com/track/"):
            track_id = uri.split("/")[-1].split("?")[0]
            normalized_uris.append(f"spotify:track:{track_id}")
        elif uri.startswith("spotify:track:"):
            normalized_uris.append(uri)
        else:
            # Assume it's just a track ID
            normalized_uris.append(f"spotify:track:{uri}")

    try:
        await asyncio.to_thread(sp.playlist_add_items, playlist_id, normalized_uris)
    except Exception as exc:
        return f"Error adding tracks to playlist: {exc}"

    return f"Successfully added {len(normalized_uris)} track(s) to playlist"


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
    "resume_playback",
    "next_track",
    "previous_track",
    "set_shuffle",
    "set_repeat",
    "seek_position",
    "get_user_playlists",
    "get_playlist_tracks",
    "create_playlist",
    "add_tracks_to_playlist",
]
