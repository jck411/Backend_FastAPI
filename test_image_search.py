#!/usr/bin/env python3
"""Test script to verify image search returns actual images."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.mcp_servers.gdrive_server import search_drive_files, _detect_file_type_query


async def test_detect_file_type():
    """Test the file type detection function."""
    print("Testing file type detection...")
    
    test_cases = [
        ("image", "mimeType contains 'image/'"),
        ("latest image", "mimeType contains 'image/'"),
        ("photo", "mimeType contains 'image/'"),
        ("pdf", "mimeType = 'application/pdf'"),
        ("latest pdf", "mimeType = 'application/pdf'"),
        ("spreadsheet", "mimeType = 'application/vnd.google-apps.spreadsheet'"),
        ("video", "mimeType contains 'video/'"),
        ("folder", "mimeType = 'application/vnd.google-apps.folder'"),
    ]
    
    for query, expected in test_cases:
        result = _detect_file_type_query(query)
        status = "✓" if result == expected else "✗"
        print(f"  {status} Query: '{query}' -> {result}")
        if result != expected:
            print(f"    Expected: {expected}")


@patch("backend.mcp_servers.gdrive_server.get_drive_service")
@patch("backend.mcp_servers.gdrive_server.asyncio.to_thread")
async def test_image_search(mock_to_thread, mock_get_service):
    """Test that searching for 'image' returns actual images, not documents."""
    print("\nTesting image search...")
    
    # Setup mocks
    mock_service = MagicMock()
    mock_get_service.return_value = mock_service
    
    files_api = mock_service.files.return_value
    files_api.list.return_value.execute.return_value = {
        "files": [
            {
                "id": "img123",
                "name": "vacation.jpg",
                "mimeType": "image/jpeg",
                "size": "2048000",
                "modifiedTime": "2025-11-13T12:00:00.000Z",
                "webViewLink": "https://drive.google.com/file/d/img123/view",
            },
            {
                "id": "img456",
                "name": "screenshot.png",
                "mimeType": "image/png",
                "size": "1024000",
                "modifiedTime": "2025-11-12T12:00:00.000Z",
                "webViewLink": "https://drive.google.com/file/d/img456/view",
            },
        ]
    }
    
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)
    
    mock_to_thread.side_effect = fake_to_thread
    
    # Run the search
    result = await search_drive_files(query="image", user_email="test@example.com", page_size=10)
    
    print(f"Result: {result}")
    
    # Verify the query was built correctly
    call_args = files_api.list.call_args
    if call_args:
        query_param = call_args.kwargs.get("q")
        print(f"\nGenerated Drive query: {query_param}")
        
        # Check that it's filtering by image MIME type
        if "mimeType contains 'image/'" in query_param:
            print("✓ Query correctly filters by image MIME type")
        else:
            print("✗ Query does NOT filter by image MIME type")
            print(f"  Expected: mimeType contains 'image/'")
            print(f"  Got: {query_param}")
    
    # Verify results contain only images
    if "vacation.jpg" in result and "image/jpeg" in result:
        print("✓ Results contain image files")
    else:
        print("✗ Results do not contain expected image files")
    
    return result


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Google Drive Image Search Fix")
    print("=" * 60)
    
    await test_detect_file_type()
    await test_image_search()
    
    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
