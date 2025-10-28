from typing import cast

import pytest

from backend.mcp_servers import notion_server
from backend.mcp_servers.notion_server import (
    NotionAppendChildrenInput,
    NotionUpdateBlockInput,
    _build_children_payload,
    _build_paragraph_block,
    _format_search_results,
    _generate_search_variations,
    _merge_properties,
    _perform_enhanced_search,
    notion_append_block_children,
    notion_update_block,
)


def _build_title_property(title: str) -> dict:
    return {"type": "title", "title": [{"plain_text": title}]}


def test_format_search_results_includes_details() -> None:
    results = [
        {
            "object": "page",
            "id": "abc123",
            "properties": {"Name": _build_title_property("Mission Statement")},
        }
    ]
    details = ["Title: Mission Statement\nBlock content:\n- Paragraph: Text"]

    output = _format_search_results(results, details, next_cursor=None)

    assert "1. Page • Mission Statement • ID: abc123" in output
    assert "\n   Title: Mission Statement" in output
    assert "- Paragraph: Text" in output


def test_format_search_results_without_details() -> None:
    results = [
        {
            "object": "database",
            "id": "db123",
            "properties": {"Name": _build_title_property("Tasks DB")},
        }
    ]

    output = _format_search_results(results, [None], next_cursor="cursor-2")

    assert "1. Database • Tasks DB • ID: db123" in output
    assert "More results available. Use start_cursor='cursor-2' to continue." in output


def test_merge_properties_ignores_custom_title_for_page_parent() -> None:
    properties = _merge_properties(
        explicit_properties=None,
        title="My Page",
        title_property="Names",
        parent_type="page",
    )

    assert "title" in properties
    assert "Names" not in properties
    assert properties["title"]["title"][0]["plain_text"] == "My Page"


def test_build_paragraph_block_generates_rich_text() -> None:
    block = _build_paragraph_block("Hello world")

    assert block["type"] == "paragraph"
    assert block["paragraph"]["rich_text"][0]["plain_text"] == "Hello world"


def test_build_children_payload_combines_inputs() -> None:
    payload = _build_children_payload(
        cast(
            NotionAppendChildrenInput,
            {"paragraphs": ["Alpha"], "children": [{"type": "divider", "divider": {}}]},
        )
    )

    assert len(payload["children"]) == 2
    assert payload["children"][0]["type"] == "paragraph"
    assert payload["children"][1]["type"] == "divider"


@pytest.mark.asyncio
async def test_notion_append_block_children_uses_patch(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    async def fake_request(method: str, path: str, *, params=None, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = json
        return {"results": [{"id": "child"}]}

    monkeypatch.setattr(notion_server, "_request", fake_request)

    message = await notion_append_block_children(
        cast(
            NotionAppendChildrenInput,
            {"block_id": "page-123", "paragraphs": ["Updated text"]},
        )
    )

    assert captured["method"] == "PATCH"
    assert captured["path"] == "/blocks/page-123/children"
    assert captured["json"]["children"][0]["type"] == "paragraph"
    assert "Appended 1 block(s)" in message


@pytest.mark.asyncio
async def test_notion_update_block_accepts_paragraph(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    async def fake_request(method: str, path: str, *, params=None, json=None):
        captured["method"] = method
        captured["path"] = path
        captured["json"] = json
        return {"type": "paragraph"}

    monkeypatch.setattr(notion_server, "_request", fake_request)

    message = await notion_update_block(
        cast(NotionUpdateBlockInput, {"block_id": "block-42", "paragraph": "Rewrite content"})
    )

    assert captured["method"] == "PATCH"
    assert captured["path"] == "/blocks/block-42"
    assert captured["json"]["paragraph"]["rich_text"][0]["plain_text"] == "Rewrite content"
    assert "Updated Notion block block-42" in message


def test_generate_search_variations_with_multiword_query() -> None:
    """Test that multi-word queries generate useful variations."""
    variations = _generate_search_variations("names to remember")
    
    assert "names to remember" in variations  # Original query
    assert "names" in variations  # First significant word
    assert "remember" in variations  # Second significant word
    assert "names remember" in variations  # Adjacent pair


def test_generate_search_variations_filters_short_words() -> None:
    """Test that short words are filtered out from individual terms."""
    variations = _generate_search_variations("old lady at the park")
    
    assert "old lady at the park" in variations  # Original query
    assert "old" in variations  # Significant word
    assert "lady" in variations  # Significant word
    assert "park" in variations  # Significant word
    # "at" and "the" should not be individual variations (too short)
    short_words_count = sum(1 for v in variations if v in ["at", "the"])
    assert short_words_count == 0


def test_generate_search_variations_single_word() -> None:
    """Test that single-word queries return just the word."""
    variations = _generate_search_variations("reminders")
    
    assert variations == ["reminders"]


def test_generate_search_variations_empty_query() -> None:
    """Test that empty queries return empty list."""
    assert _generate_search_variations(None) == []
    assert _generate_search_variations("") == []
    assert _generate_search_variations("   ") == []


@pytest.mark.asyncio
async def test_perform_enhanced_search_with_good_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that enhanced search returns immediately when initial query has good results."""
    call_count = 0
    
    async def fake_request(method: str, path: str, *, params=None, json=None):
        nonlocal call_count
        call_count += 1
        # Return 3+ results on first call
        return {
            "results": [
                {"id": "1", "object": "page"},
                {"id": "2", "object": "page"},
                {"id": "3", "object": "page"},
            ],
            "next_cursor": None,
        }
    
    monkeypatch.setattr(notion_server, "_request", fake_request)
    
    results, next_cursor = await _perform_enhanced_search("names to remember")
    
    # Should only make one API call since we got good results
    assert call_count == 1
    assert len(results) == 3


@pytest.mark.asyncio
async def test_perform_enhanced_search_tries_variations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that enhanced search tries variations when initial query yields few results."""
    call_count = 0
    queries_tried = []
    
    async def fake_request(method: str, path: str, *, params=None, json=None):
        nonlocal call_count
        call_count += 1
        query = json.get("query", "") if json else ""
        queries_tried.append(query)
        
        # First call returns only 1 result
        if call_count == 1:
            return {"results": [{"id": "1", "object": "page"}], "next_cursor": None}
        # Variation calls return different results
        elif call_count == 2:
            return {"results": [{"id": "2", "object": "page"}], "next_cursor": None}
        else:
            return {"results": [{"id": "3", "object": "page"}], "next_cursor": None}
    
    monkeypatch.setattr(notion_server, "_request", fake_request)
    
    results, next_cursor = await _perform_enhanced_search("names to remember")
    
    # Should make multiple API calls to try variations
    assert call_count > 1
    # Should have tried the original query
    assert "names to remember" in queries_tried
    # Should deduplicate results by ID
    result_ids = [r["id"] for r in results]
    assert len(result_ids) == len(set(result_ids))  # No duplicates


@pytest.mark.asyncio
async def test_perform_enhanced_search_handles_api_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that enhanced search continues with other variations if one fails."""
    call_count = 0
    
    async def fake_request(method: str, path: str, *, params=None, json=None):
        nonlocal call_count
        call_count += 1
        
        # First call returns 1 result
        if call_count == 1:
            return {"results": [{"id": "1", "object": "page"}], "next_cursor": None}
        # Second call raises error
        elif call_count == 2:
            from backend.mcp_servers.notion_server import NotionAPIError
            raise NotionAPIError("Test error")
        # Third call succeeds
        else:
            return {"results": [{"id": "2", "object": "page"}], "next_cursor": None}
    
    monkeypatch.setattr(notion_server, "_request", fake_request)
    
    results, next_cursor = await _perform_enhanced_search("names to remember")
    
    # Should still return results from successful calls
    assert len(results) >= 1
    assert call_count >= 2  # Should have tried multiple variations
