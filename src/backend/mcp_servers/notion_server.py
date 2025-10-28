"""Custom MCP server exposing a focused subset of the Notion API for reminders and memory.

This lightweight adapter mirrors the public `notion-mcp-server` reference
implementation while remaining fully async and dependency-light. It's optimized
for storing and retrieving reminders, notes, and information you want to remember.

Tools provided
--------------
* ``notion_search`` – search for reminders, notes, and stored information (e.g.,
  "names to remember", "project ideas"). Wraps the `/v1/search` endpoint.
* ``notion_retrieve_page`` – retrieve detailed content from a reminder or note page,
  fetching metadata and block content via `/v1/pages/{page_id}` and
  `/v1/blocks/{page_id}/children`.
* ``notion_create_page`` – create new reminder notes or memory storage pages (e.g.,
  "Names to Remember", "Books to Read") using `/v1/pages`.
* ``notion_append_block_children`` – add new content to existing reminders or notes
  (e.g., add a new name to your "names to remember" page) via
  `/v1/blocks/{block_id}/children`.
* ``notion_update_block`` – update or modify content in existing reminder blocks
  via `/v1/blocks/{block_id}`.

Common use cases
----------------
* Remember names: Create a "Names to Remember" page, search it when needed, and
  add new names as you meet people.
* Store information: Create topic-specific notes (e.g., "Project Ideas",
  "Books to Read") that you can search and update later.
* Manage reminders: Build lists and notes that help you remember important
  information, tasks, or ideas.

Required environment variables
------------------------------
* ``NOTION_TOKEN`` or ``NOTION_API_KEY`` – the integration token created from
  https://www.notion.so/profile/integrations. ``NOTION_TOKEN`` mirrors the
  upstream project defaults, while ``NOTION_API_KEY`` matches the official
  developer documentation naming.
* ``NOTION_VERSION`` (optional) – defaults to the latest stable version used by
  the reference repository (``2022-06-28``).
* ``NOTION_PAGE_ID`` (optional) – default parent page for ``notion_create_page``
  when a parent is not explicitly supplied.
* ``NOTION_DATABASE_ID`` (optional) – default parent database for
  ``notion_create_page``. Takes precedence over ``NOTION_PAGE_ID`` when both are
  defined because Notion requires database items to specify a database parent.

Payload schemas
---------------
``notion_search`` accepts Notion's search body members: ``query`` (string),
``filter`` and ``sort`` objects, ``start_cursor`` (string) and ``page_size``
(int). The helper ``_build_search_payload`` ensures optional keys are removed
when empty so the payload matches the upstream JSON schema. Additional optional
parameters ``include_content`` (bool, defaults to ``True``) and
``content_block_limit`` (int, defaults to ``20``) control whether matching page
contents are embedded in the response and how many blocks are fetched per page.

``notion_retrieve_page`` requires a ``page_id`` string. Optional parameters are
``filter_properties`` (list of property IDs to include), ``include_children``
(boolean), ``start_cursor`` and ``page_size`` for pagination when fetching block
content. The helper ``_parse_filter_properties`` converts the list into the
comma-delimited query parameter Notion expects.

``notion_create_page`` accepts either a ``title`` string or a raw Notion
``properties`` mapping. Parent selection can be controlled with ``parent_id``
and ``parent_type`` (``"page"`` or ``"database"``). For convenience the
``title_property`` parameter defaults to ``"Name"`` when using database parents
and ``"title"`` for page parents. The ``_build_page_payload`` helper assembles a
valid Notion page create body and ensures title rich text blocks are generated
when only ``title`` is provided.
"""

from __future__ import annotations

import asyncio
import os
import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Literal, Optional, Sequence, TypedDict

import httpx

if TYPE_CHECKING:  # pragma: no cover - only needed for static analysis

    class FastMCP:  # pragma: no cover - type checking shim
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        def tool(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...

        def run(self) -> None: ...

else:  # Runtime import
    from mcp.server.fastmcp import FastMCP

NOTION_BASE_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = "2022-06-28"
DEFAULT_SEARCH_BLOCK_LIMIT = 100


@dataclass(slots=True)
class NotionConfig:
    """Runtime configuration resolved from environment variables."""

    token: str
    version: str
    default_page_id: Optional[str] = None
    default_database_id: Optional[str] = None


class NotionSearchPayload(TypedDict, total=False):
    query: str
    filter: Dict[str, Any]
    sort: Dict[str, Any]
    start_cursor: str
    page_size: int


class NotionCreatePageInput(TypedDict, total=False):
    title: str
    parent_id: str
    parent_type: Literal["page", "database"]
    title_property: str
    properties: Dict[str, Any]
    children: List[Dict[str, Any]]
    icon: Dict[str, Any]
    cover: Dict[str, Any]


class NotionAppendChildrenInput(TypedDict, total=False):
    block_id: str
    children: List[Dict[str, Any]]
    paragraphs: Iterable[str]


class NotionUpdateBlockInput(TypedDict, total=False):
    block_id: str
    block: Dict[str, Any]
    paragraph: str
    archived: bool


class NotionAPIError(RuntimeError):
    """Raised when the Notion API returns an error response."""


_config: Optional[NotionConfig] = None
_config_lock = asyncio.Lock()
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock = asyncio.Lock()


async def _get_config() -> NotionConfig:
    """Load configuration from the environment, caching the result."""

    global _config
    if _config is not None:
        return _config

    async with _config_lock:
        if _config is not None:
            return _config

        token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
        if not token:
            raise NotionAPIError(
                "Notion credentials missing. Set NOTION_TOKEN (preferred) or NOTION_API_KEY "
                "with a valid integration token."
            )

        config = NotionConfig(
            token=token,
            version=os.getenv("NOTION_VERSION", DEFAULT_NOTION_VERSION),
            default_page_id=os.getenv("NOTION_PAGE_ID"),
            default_database_id=os.getenv("NOTION_DATABASE_ID"),
        )
        _config = config
        return config


async def _get_http_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient with sane defaults."""

    global _http_client
    if _http_client is not None:
        return _http_client

    async with _http_client_lock:
        if _http_client is not None:
            return _http_client

        timeout = httpx.Timeout(30.0, connect=10.0)
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        _http_client = httpx.AsyncClient(base_url=NOTION_BASE_URL, timeout=timeout, limits=limits)
        return _http_client


def _build_headers(config: NotionConfig) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {config.token}",
        "Notion-Version": config.version,
        "Content-Type": "application/json",
    }


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Perform an HTTP request against the Notion API."""

    config = await _get_config()
    client = await _get_http_client()
    headers = _build_headers(config)

    response = await client.request(method, path, params=params, json=json, headers=headers)

    try:
        payload = response.json()
    except ValueError:
        payload = {"message": response.text}

    if response.status_code >= 400:
        detail = payload.get("message") or payload.get("error") or payload
        raise NotionAPIError(f"Notion API error {response.status_code}: {detail}")

    return payload  # type: ignore[return-value]


def _build_search_payload(
    query: Optional[str],
    *,
    filter: Optional[Dict[str, Any]] = None,
    sort: Optional[Dict[str, Any]] = None,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
) -> NotionSearchPayload:
    payload: NotionSearchPayload = {}
    if query:
        payload["query"] = query
    if filter:
        payload["filter"] = filter
    if sort:
        payload["sort"] = sort
    if start_cursor:
        payload["start_cursor"] = start_cursor
    if page_size:
        payload["page_size"] = page_size
    return payload


def _build_rich_text(title: str) -> List[Dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": {"content": title},
            "plain_text": title,
            "annotations": {
                "bold": False,
                "italic": False,
                "strikethrough": False,
                "underline": False,
                "code": False,
                "color": "default",
            },
        }
    ]


def _build_parent(
    *,
    parent_id: Optional[str],
    parent_type: Optional[Literal["page", "database"]],
    config: NotionConfig,
) -> tuple[Dict[str, str], Literal["page", "database"]]:
    resolved_type: Literal["page", "database"]
    resolved_id: Optional[str] = parent_id

    if not resolved_id:
        if parent_type == "page":
            resolved_id = config.default_page_id
        elif parent_type == "database":
            resolved_id = config.default_database_id
        else:
            resolved_id = config.default_database_id or config.default_page_id
            parent_type = "database" if config.default_database_id else "page"

    if not parent_type:
        parent_type = "database" if resolved_id and resolved_id == config.default_database_id else "page"

    if not resolved_id:
        raise NotionAPIError(
            "A Notion parent could not be determined. Provide parent_id explicitly or configure NOTION_DATABASE_ID/NOTION_PAGE_ID."
        )

    resolved_type = parent_type
    if resolved_type == "database":
        return {"database_id": resolved_id}, "database"
    return {"page_id": resolved_id}, "page"


def _merge_properties(
    *,
    explicit_properties: Optional[Dict[str, Any]],
    title: Optional[str],
    title_property: Optional[str],
    parent_type: Literal["page", "database"],
) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    if explicit_properties:
        properties.update(explicit_properties)

    if title:
        key: str
        if parent_type == "database":
            key = title_property or "Name"
        else:
            # Notion requires the canonical "title" property when creating
            # pages beneath a page parent. Allow callers to provide
            # ``title_property`` but ignore the override so the API accepts the
            # payload instead of raising ``Invalid property identifier``.
            key = "title"
        existing = properties.get(key)
        if existing is None:
            properties[key] = {"title": _build_rich_text(title)}
        elif "title" in existing and not existing["title"]:
            existing["title"] = _build_rich_text(title)

    if not properties:
        raise NotionAPIError(
            "Unable to construct Notion properties. Provide a title or the full 'properties' payload that matches your parent schema."
        )

    return properties


def _build_page_payload(config: NotionConfig, data: NotionCreatePageInput) -> Dict[str, Any]:
    parent, parent_type = _build_parent(
        parent_id=data.get("parent_id"),
        parent_type=data.get("parent_type"),
        config=config,
    )

    properties = _merge_properties(
        explicit_properties=data.get("properties"),
        title=data.get("title"),
        title_property=data.get("title_property"),
        parent_type=parent_type,
    )

    payload: Dict[str, Any] = {
        "parent": parent,
        "properties": properties,
    }
    if children := data.get("children"):
        payload["children"] = children
    if icon := data.get("icon"):
        payload["icon"] = icon
    if cover := data.get("cover"):
        payload["cover"] = cover

    return payload


def _parse_filter_properties(values: Optional[Iterable[str]]) -> Optional[str]:
    if not values:
        return None
    cleaned = [value.strip() for value in values if value.strip()]
    return ",".join(cleaned) if cleaned else None


def _extract_title(data: Dict[str, Any]) -> Optional[str]:
    properties = data.get("properties") or {}
    for value in properties.values():
        if isinstance(value, dict) and value.get("type") == "title":
            rich_text = value.get("title") or []
            if rich_text:
                first = rich_text[0]
                if isinstance(first, dict):
                    text = first.get("plain_text")
                    if text:
                        return text
    title_obj = data.get("title")
    if isinstance(title_obj, list) and title_obj:
        first = title_obj[0]
        if isinstance(first, dict):
            return first.get("plain_text")
    return data.get("name") or data.get("id")


def _build_paragraph_block(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _build_rich_text(text)},
    }


def _format_result_heading(entry: Dict[str, Any]) -> str:
    object_type = entry.get("object", "unknown").title()
    identifier = entry.get("id", "(unknown id)")
    title = _extract_title(entry) or "(untitled)"
    return f"{object_type} • {title} • PAGE ID: {identifier}"


def _format_search_results(
    results: List[Dict[str, Any]],
    details: Sequence[Optional[str]],
    next_cursor: Optional[str],
) -> str:
    if not results:
        return "No matching Notion pages or databases were found."

    lines = [f"Found {len(results)} Notion results:", ""]
    for index, (entry, detail) in enumerate(zip(results, details), start=1):
        heading = f"{index}. {_format_result_heading(entry)}"
        lines.append(heading)
        if detail:
            lines.append(textwrap.indent(detail, "   "))
        if index < len(results):
            lines.append("")
    if next_cursor:
        lines.append("")
        lines.append(f"More results available. Use start_cursor='{next_cursor}' to continue.")
    return "\n".join(lines)


def _format_page_summary(page: Dict[str, Any]) -> str:
    title = _extract_title(page) or "(untitled)"
    page_id = page.get("id", "(unknown id)")
    url = page.get("url")
    last_edited = page.get("last_edited_time")
    created_time = page.get("created_time")
    properties = page.get("properties", {})

    lines = [f"Title: {title}", f"PAGE ID: {page_id}"]
    if url:
        lines.append(f"URL: {url}")
    if created_time:
        lines.append(f"Created: {created_time}")
    if last_edited:
        lines.append(f"Last edited: {last_edited}")

    if properties:
        lines.append("")
        lines.append("Properties:")
        for key, value in properties.items():
            if isinstance(value, dict):
                prop_type = value.get("type", "unknown")
                lines.append(f"- {key} ({prop_type})")
            else:
                lines.append(f"- {key}: {value}")

    return "\n".join(lines)


def _format_block_content(blocks: List[Dict[str, Any]]) -> str:
    if not blocks:
        return "No child blocks were returned for this page."

    lines = ["Block content:"]
    for block in blocks:
        block_type = block.get("type", "unknown")
        block_id = block.get("id", "unknown")
        if block_type == "paragraph":
            text_items = block.get("paragraph", {}).get("rich_text", [])
            text_content = "".join(item.get("plain_text", "") for item in text_items)
            lines.append(f"- Paragraph ({block_id}): {text_content}")
        elif block_type == "heading_1":
            text_items = block.get("heading_1", {}).get("rich_text", [])
            text_content = "".join(item.get("plain_text", "") for item in text_items)
            lines.append(f"- Heading 1 ({block_id}): {text_content}")
        elif block_type == "heading_2":
            text_items = block.get("heading_2", {}).get("rich_text", [])
            text_content = "".join(item.get("plain_text", "") for item in text_items)
            lines.append(f"- Heading 2 ({block_id}): {text_content}")
        elif block_type == "heading_3":
            text_items = block.get("heading_3", {}).get("rich_text", [])
            text_content = "".join(item.get("plain_text", "") for item in text_items)
            lines.append(f"- Heading 3 ({block_id}): {text_content}")
        else:
            lines.append(f"- {block_type.replace('_', ' ').title()} ({block_id})")

    return "\n".join(lines)


async def _fetch_block_children(
    page_id: str,
    *,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if start_cursor:
        params["start_cursor"] = start_cursor
    if page_size:
        params["page_size"] = page_size

    return await _request("GET", f"/blocks/{page_id}/children", params=params)


mcp: FastMCP = FastMCP("custom-notion")


async def _render_entry_detail(
    entry: Dict[str, Any],
    *,
    block_limit: int,
) -> Optional[str]:
    if entry.get("object") != "page":
        return None
    identifier = entry.get("id")
    if not identifier:
        return None
    try:
        return await notion_retrieve_page(
            identifier,
            include_children=True,
            page_size=block_limit,
        )
    except NotionAPIError as exc:  # pragma: no cover - network errors during tests
        return f"Failed to load page content: {exc}"


async def _collect_search_details(
    results: List[Dict[str, Any]],
    *,
    block_limit: int,
) -> List[Optional[str]]:
    tasks = [_render_entry_detail(entry, block_limit=block_limit) for entry in results]
    return await asyncio.gather(*tasks)


@mcp.tool(
    "notion_search",
    description=(
        "Search Notion for reminders, notes, and information you want to remember. "
        "Returns matching pages with their PAGE IDs (look for 'ID: ...' in results). "
        "Use this to find pages like 'Names to Remember', 'Project Ideas', or any stored information. "
        "When searching for specific details (like someone's name), this will return relevant pages WITH their content. "
        "If you see 'Additional blocks available' in the results, the content was truncated - "
        "immediately call notion_retrieve_page using the PAGE ID (not block IDs) with include_children=true to get ALL content. "
        "\n\n"
        "CRITICAL SEARCH STRATEGY for finding specific information: "
        "When user asks about a specific person/thing (e.g., 'who is the old lady at the park'), "
        "DO NOT search for that exact phrase. Instead: "
        "1. Search for the relevant page by title (e.g., 'Names' or 'Names to Remember'). "
        "2. Read through ALL the returned content to find matching entries. "
        "3. If no results or truncated, use notion_retrieve_page to get COMPLETE content. "
        "Notion search is literal - 'old lady at the park' won't match 'old lady park' in the content. "
        "Always retrieve the full page and search through it yourself for specific details."
    )
)
async def notion_search(
    query: Optional[str] = None,
    *,
    filter: Optional[Dict[str, Any]] = None,
    sort: Optional[Dict[str, Any]] = None,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
    include_content: bool = True,
    content_block_limit: Optional[int] = None,
) -> str:
    """Search for reminders, notes, and stored information in Notion workspace.

    Use this tool to find previously saved information, reminders, or notes. Perfect for:
    - Searching for names to remember (e.g., "names to remember", "people I met")
    - Finding notes about specific topics or subjects
    - Retrieving stored reminders and memory aids
    - Looking up information you've saved for later recall

    IMPORTANT SEARCH STRATEGY:
    - For finding specific details within notes, search for the PAGE TITLE first
    - Example: Instead of "old lady at the park", search for "Names" to find the names page,
      then read through the complete content to find entries about "old lady" or "park"
    - Notion search is literal and won't match "old lady at the park" with "old lady park"

    Examples:
    - Search "names to remember" or "Names" to find a note containing names
    - Search "project ideas" to retrieve saved project notes
    - Search "books to read" to find your reading list

    Authentication requires ``NOTION_TOKEN`` (preferred) or ``NOTION_API_KEY`` to
    be present in the environment. Optional ``NOTION_VERSION`` mirrors the
    upstream configuration and defaults to ``2022-06-28``. Set
    ``include_content=False`` to return metadata only. ``content_block_limit``
    controls how many child blocks are retrieved per page (defaults to 100).
    """

    payload = _build_search_payload(
        query,
        filter=filter,
        sort=sort,
        start_cursor=start_cursor,
        page_size=page_size,
    )
    response = await _request("POST", "/search", json=payload)
    results = response.get("results") or []
    block_limit = max(1, content_block_limit or DEFAULT_SEARCH_BLOCK_LIMIT)
    details = (
        await _collect_search_details(results, block_limit=block_limit)
        if include_content and results
        else [None] * len(results)
    )
    return _format_search_results(results, details, response.get("next_cursor"))


@mcp.tool(
    "notion_retrieve_page",
    description=(
        "Retrieve the COMPLETE content of a specific Notion page/note by its PAGE ID. "
        "IMPORTANT: Use the PAGE ID from search results (e.g., 'ID: 29896b0b-3790-8118-...'), NOT block IDs. "
        "Use this when notion_search returns truncated content and you need ALL blocks from the page. "
        "Perfect for reading entire 'Names to Remember' lists or any page where you need to search through ALL entries. "
        "Always use include_children=true when you need to find specific information within a page."
    )
)
async def notion_retrieve_page(
    page_id: str,
    *,
    filter_properties: Optional[List[str]] = None,
    include_children: bool = True,
    start_cursor: Optional[str] = None,
    page_size: Optional[int] = None,
) -> str:
    """Retrieve detailed content from a reminder or note page in Notion.

    IMPORTANT: page_id must be the PAGE ID from search results (e.g., '29896b0b-3790-8118-b115-e843978e56ba'),
    NOT a block ID (which appears in parentheses after block types like 'Paragraph (block-id)').

    Use this tool to read the full content of a specific reminder, note, or stored information.
    Perfect for accessing complete details after finding a page via search.

    Common use cases:
    - Read all names from a "names to remember" note
    - Review detailed information from a reminder page
    - Check the full content of a note you've found

    Set ``include_children=True`` to fetch the complete page content with all blocks.
    Use ``start_cursor`` and ``page_size`` to paginate through long documents.

    Authentication requires ``NOTION_TOKEN`` (preferred) or ``NOTION_API_KEY``.
    """

    params: Dict[str, Any] = {}
    if parsed := _parse_filter_properties(filter_properties):
        params["filter_properties"] = parsed

    page = await _request("GET", f"/pages/{page_id}", params=params)
    summary = _format_page_summary(page)

    if not include_children:
        return summary

    blocks_response = await _fetch_block_children(
        page_id,
        start_cursor=start_cursor,
        page_size=page_size,
    )
    blocks_output = _format_block_content(blocks_response.get("results", []))
    if blocks_response.get("has_more") and blocks_response.get("next_cursor"):
        blocks_output += (
            "\n\nAdditional blocks available. "
            f"Use start_cursor='{blocks_response['next_cursor']}' to continue."
        )

    return f"{summary}\n\n{blocks_output}"


@mcp.tool(
    "notion_create_page",
    description=(
        "Create a new reminder note or memory storage page in Notion. "
        "Use this to create pages like 'Names to Remember', 'Books to Read', 'Project Ideas', etc. "
        "You can set a title and optionally add initial content blocks."
    )
)
async def notion_create_page(
    data: NotionCreatePageInput,
) -> str:
    """Create a new reminder, note, or memory storage page in Notion.

    Use this tool to save new information, create reminders, or store things to remember later.
    Perfect for:
    - Creating a "names to remember" note to store new names
    - Saving reminders about tasks or things to do
    - Creating notes about topics you want to remember
    - Storing information for future reference

    Examples:
    - Create a page titled "Names to Remember" with initial names
    - Create a "Project Ideas" page to store your ideas
    - Create reminder notes with titles like "Things to Buy" or "Books to Read"

    If ``parent_id`` is omitted the server will fall back to ``NOTION_DATABASE_ID``
    or ``NOTION_PAGE_ID``. Provide ``title`` for simple notes or supply ``properties``
    that match your database schema when creating structured entries.

    Authentication requires ``NOTION_TOKEN`` (preferred) or ``NOTION_API_KEY``.
    """

    config = await _get_config()
    payload = _build_page_payload(config, data)
    response = await _request("POST", "/pages", json=payload)
    title = _extract_title(response) or "(untitled)"
    url = response.get("url") or "(no public URL)"
    identifier = response.get("id", "(unknown id)")
    return f"Created Notion page '{title}' with ID {identifier}. URL: {url}"


def _build_children_payload(data: NotionAppendChildrenInput) -> Dict[str, Any]:
    children: List[Dict[str, Any]] = []
    if paragraphs := data.get("paragraphs"):
        for value in paragraphs:
            text = str(value)
            if text.strip():
                children.append(_build_paragraph_block(text))
    if explicit_children := data.get("children"):
        children.extend(explicit_children)
    if not children:
        raise NotionAPIError(
            "Unable to append Notion blocks. Provide 'paragraphs' text or the raw 'children' payload matching Notion's schema."
        )
    return {"children": children}


@mcp.tool(
    "notion_append_block_children",
    description=(
        "Add new content to an existing Notion page/note. "
        "Use this to append new entries to lists like adding a new name to 'Names to Remember', "
        "a new book to 'Books to Read', or any new reminder to an existing page."
    )
)
async def notion_append_block_children(data: NotionAppendChildrenInput) -> str:
    """Add new content to an existing reminder or note page in Notion.

    Use this tool to add more information to existing notes or reminders. Perfect for:
    - Adding a new name to your "names to remember" note
    - Appending new items to an existing reminder list
    - Adding additional information to a note you've already created

    Examples:
    - Add "John Smith - met at conference" to your names note
    - Append new book titles to your reading list
    - Add new items to your shopping list or todo reminders
    """

    block_id = data.get("block_id")
    if not block_id:
        raise NotionAPIError("block_id is required to append Notion blocks.")

    payload = _build_children_payload(data)
    response = await _request("PATCH", f"/blocks/{block_id}/children", json=payload)
    appended = len(response.get("results") or payload.get("children", []))
    return f"Appended {appended} block(s) to Notion block {block_id}."


def _build_block_update_payload(data: NotionUpdateBlockInput) -> Dict[str, Any]:
    if explicit := data.get("block"):
        payload = dict(explicit)
    elif paragraph := data.get("paragraph"):
        payload = {
            "paragraph": {
                "rich_text": _build_rich_text(paragraph),
            }
        }
    else:
        raise NotionAPIError(
            "Unable to build Notion block update payload. Provide 'paragraph' text or the full 'block' body."
        )

    if "object" in payload:
        payload.pop("object")
    if "id" in payload:
        payload.pop("id")

    if "archived" not in payload and "archived" in data:
        payload["archived"] = data["archived"]

    return payload


@mcp.tool(
    "notion_update_block",
    description=(
        "Update or modify existing content in a Notion reminder or note. "
        "Use this to correct information, update details, or archive old reminders."
    )
)
async def notion_update_block(data: NotionUpdateBlockInput) -> str:
    """Update or modify content in an existing reminder or note block.

    Use this tool to edit, correct, or update information in your notes and reminders.
    Perfect for:
    - Updating a name with additional context or corrections
    - Modifying reminder text to reflect changes
    - Correcting or enhancing stored information

    Examples:
    - Update "John" to "John Smith - CEO at Tech Corp"
    - Change a reminder note with updated details
    - Edit stored information to keep it current and accurate
    """

    block_id = data.get("block_id")
    if not block_id:
        raise NotionAPIError("block_id is required to update a Notion block.")

    payload = _build_block_update_payload(data)
    response = await _request("PATCH", f"/blocks/{block_id}", json=payload)
    block_type = response.get("type", payload.keys())
    return f"Updated Notion block {block_id} ({block_type})."


if __name__ == "__main__":
    mcp.run()
