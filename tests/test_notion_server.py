from typing import cast

import pytest

from backend.mcp_servers import notion_server
from backend.mcp_servers.notion_server import (
    NotionAppendChildrenInput,
    NotionUpdateBlockInput,
    _build_children_payload,
    _build_paragraph_block,
    _format_search_results,
    _merge_properties,
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
