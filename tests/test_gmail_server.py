"""Tests for the Gmail MCP server."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import backend.mcp_servers.gmail_server as gmail_module
from backend.mcp_servers.gmail_server import (
    generate_auth_url,
    search_gmail_messages,
)


@pytest.mark.asyncio
@patch("backend.mcp_servers.gmail_server.get_credentials")
async def test_auth_status_authorized(mock_get_credentials):
    mock_credentials = MagicMock()
    mock_credentials.expiry = None
    mock_get_credentials.return_value = mock_credentials

    result = await gmail_module.auth_status("user@example.com")

    assert "already authorized" in result
    mock_get_credentials.assert_called_once_with("user@example.com")


@patch("backend.mcp_servers.gmail_server.get_credentials")
@pytest.mark.asyncio
async def test_auth_status_missing(mock_get_credentials):
    mock_get_credentials.return_value = None

    result = await gmail_module.auth_status("user@example.com")

    assert "No stored Gmail credentials" in result
    mock_get_credentials.assert_called_once_with("user@example.com")


@patch("backend.mcp_servers.gmail_server.authorize_user")
@patch("backend.mcp_servers.gmail_server.get_credentials")
@pytest.mark.asyncio
async def test_generate_auth_url_existing_credentials(
    mock_get_credentials, mock_authorize_user
):
    mock_credentials = MagicMock()
    mock_credentials.expiry = None
    mock_get_credentials.return_value = mock_credentials

    result = await generate_auth_url("user@example.com")

    assert "already has stored credentials" in result
    mock_authorize_user.assert_not_called()


@patch("backend.mcp_servers.gmail_server.authorize_user")
@patch("backend.mcp_servers.gmail_server.get_credentials")
@pytest.mark.asyncio
async def test_generate_auth_url_force_flow(mock_get_credentials, mock_authorize_user):
    mock_credentials = MagicMock()
    mock_credentials.expiry = None
    mock_get_credentials.return_value = mock_credentials
    mock_authorize_user.return_value = "https://auth.example.com"

    result = await generate_auth_url(
        "user@example.com", redirect_uri="https://app.example.com/callback", force=True
    )

    assert "https://auth.example.com" in result
    mock_authorize_user.assert_called_once()


@patch("backend.mcp_servers.gmail_server.get_gmail_service")
@pytest.mark.asyncio
async def test_search_gmail_messages_auth_error(mock_get_gmail_service):
    mock_get_gmail_service.side_effect = ValueError("Missing credentials")

    result = await search_gmail_messages("from:someone@example.com")

    assert "Authentication error" in result
    assert "Missing credentials" in result
