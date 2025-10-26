from backend.mcp_servers.notion_server import _format_search_results


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
