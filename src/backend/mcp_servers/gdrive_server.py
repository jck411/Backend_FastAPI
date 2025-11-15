"""Custom MCP server for Google Drive integration."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple

import httpx
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

if TYPE_CHECKING:

    class FastMCP:
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        def tool(
            self, name: str
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...

        def run(self) -> None: ...

else:
    from mcp.server.fastmcp import FastMCP

from backend.mcp_servers.pdf_server import extract_bytes as kb_extract_bytes
from backend.services.attachments import AttachmentService
from backend.services.google_auth.auth import (
    DEFAULT_USER_EMAIL,
    get_drive_service,
)

mcp = FastMCP("custom-gdrive")
DRIVE_FIELDS_MINIMAL = (
    "files(id, name, mimeType, size, modifiedTime, webViewLink, iconLink)"
)
# Maximum file size in bytes for download operations (50MB)
MAX_CONTENT_BYTES = 50 * 1024 * 1024

# Global attachment service reference - set by application at runtime
_attachment_service: AttachmentService | None = None
_attachment_service_lock = asyncio.Lock()


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _success_response(
    data: Any | None = None,
    *,
    message: Optional[str] = None,
    warnings: Optional[Sequence[str]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    payload: Dict[str, Any] = {"ok": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    if warnings:
        payload["warnings"] = list(warnings)
    if meta:
        payload["meta"] = meta
    return json.dumps(payload)


def _error_response(
    message: str,
    *,
    code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    warnings: Optional[Sequence[str]] = None,
) -> str:
    payload: Dict[str, Any] = {
        "ok": False,
        "error": {"message": message},
    }
    if code:
        payload["error"]["code"] = code
    if details:
        payload["error"]["details"] = details
    if warnings:
        payload["warnings"] = list(warnings)
    return json.dumps(payload)


def _format_drive_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "mime_type": item.get("mimeType"),
        "size_bytes": _safe_int(item.get("size")),
        "modified_time": item.get("modifiedTime"),
        "web_view_link": item.get("webViewLink"),
        "web_content_link": item.get("webContentLink"),
        "icon_link": item.get("iconLink"),
        "parents": item.get("parents"),
        "drive_id": item.get("driveId"),
    }


def _format_permission(permission: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": permission.get("id"),
        "type": permission.get("type"),
        "role": permission.get("role"),
        "email_address": permission.get("emailAddress"),
        "domain": permission.get("domain"),
        "allow_file_discovery": permission.get("allowFileDiscovery"),
        "display_name": permission.get("displayName"),
    }


async def _get_attachment_service() -> AttachmentService:
    """Get or create the attachment service instance."""
    global _attachment_service
    if _attachment_service is not None:
        return _attachment_service
    async with _attachment_service_lock:
        if _attachment_service is None:
            # Import here to avoid circular dependencies
            from backend.config import get_settings
            from backend.repository import ChatRepository

            settings = get_settings()
            # Initialize repository for attachment service
            db_path = settings.chat_database_path
            repository = ChatRepository(db_path)
            await repository.initialize()
            _attachment_service = AttachmentService(
                repository,
                max_size_bytes=settings.attachments_max_size_bytes,
                retention_days=settings.attachments_retention_days,
            )
    return _attachment_service


def _get_drive_service_or_error(
    user_email: str,
) -> Tuple[Optional[Any], Optional[str]]:
    """Get Drive service or return error message.

    Returns:
        (service, None) on success
        (None, error_message) on failure
    """
    try:
        service = get_drive_service(user_email)
        return service, None
    except ValueError as exc:
        return None, (
            f"Authentication error: {exc}. Click 'Connect Google Services' in Settings "
            "to authorize this account."
        )
    except Exception as exc:
        return None, f"Error creating Google Drive service: {exc}"


def _normalize_parent_id(parent_id: Optional[str]) -> str:
    """Normalize parent folder ID, treating empty/None as root."""
    if not parent_id or not parent_id.strip():
        return "root"
    return parent_id.strip()


def _escape_query_term(value: str) -> str:
    """Escape special characters in Drive query terms."""
    # Escape backslashes first, then single quotes
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _has_anyone_link_access(permissions: List[Dict[str, Any]]) -> bool:
    """Check if permissions include 'anyone with the link' access.

    Args:
        permissions: List of permission dictionaries from Drive API

    Returns:
        True if any permission grants public link access
    """
    return any(
        perm.get("type") == "anyone"
        and perm.get("role") in {"reader", "writer", "commenter"}
        for perm in permissions
    )


def _build_drive_list_params(
    *,
    query: str,
    page_size: int,
    drive_id: Optional[str],
    include_items_from_all_drives: bool,
    corpora: Optional[str],
) -> Dict[str, object]:
    """Compose the parameters for Drive files().list requests."""

    params: Dict[str, object] = {
        "q": query,
        "pageSize": max(page_size, 1),
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": include_items_from_all_drives,
        "fields": f"nextPageToken, {DRIVE_FIELDS_MINIMAL}",
        "orderBy": "modifiedTime desc",
    }

    if drive_id:
        params["driveId"] = drive_id
        params["corpora"] = corpora or "drive"
    elif corpora:
        params["corpora"] = corpora

    return params


async def _download_request_bytes(
    request: Any, max_size: Optional[int] = None
) -> bytes:
    """Stream a Drive media request into bytes using the resumable downloader.

    Args:
        request: The Drive API media request
        max_size: Maximum allowed size in bytes (defaults to MAX_CONTENT_BYTES)

    Returns:
        Downloaded bytes

    Raises:
        ValueError: If content exceeds max_size
    """
    if max_size is None:
        max_size = MAX_CONTENT_BYTES

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    loop = asyncio.get_running_loop()
    done = False
    while not done:
        _, done = await loop.run_in_executor(None, downloader.next_chunk)
        # Check size after each chunk
        current_size = buffer.tell()
        if current_size > max_size:
            raise ValueError(
                f"File size ({current_size} bytes) exceeds maximum allowed size "
                f"({max_size} bytes, ~{max_size // (1024 * 1024)}MB)"
            )

    return buffer.getvalue()


def _is_structured_drive_query(query: str) -> bool:
    """Detect if query is a structured Drive query vs plain text.

    Conservative heuristic: only treat as structured if it clearly looks
    like a Drive query with field operators.
    """
    # Look for field operators that are characteristic of Drive queries
    # e.g., "name=", "mimeType contains", "'id' in parents"
    field_patterns = [
        r"\b(name|mimeType|fullText|modifiedTime|createdTime|trashed|starred)\s*(=|!=|contains)\s*['\"]",
        r"['\"][^'\"]+['\"]\s+in\s+parents\b",
        r"\b(and|or)\s+(name|mimeType|fullText|trashed|starred)\s*(=|!=|contains)",
    ]

    for pattern in field_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return True

    return False


def _detect_file_type_query(query: str) -> Optional[str]:
    """Detect if query is asking for a specific file type and return MIME type filter.

    Maps common file type keywords to Google Drive MIME type queries.
    Returns None if no file type is detected.

    Examples:
        "image" -> "mimeType contains 'image/'"
        "latest pdf" -> "mimeType = 'application/pdf'"
        "spreadsheet" -> "mimeType = 'application/vnd.google-apps.spreadsheet'"
    """
    query_lower = query.lower()

    # Map keywords to MIME type filters
    # Using "contains" for broader matches, "=" for exact matches
    type_mappings = [
        # Images - match any image type
        (["image", "images", "photo", "photos", "picture", "pictures", "img", "png", "jpg", "jpeg", "gif"], 
         "mimeType contains 'image/'"),
        
        # PDFs
        (["pdf", "pdfs"], 
         "mimeType = 'application/pdf'"),
        
        # Google Docs
        (["document", "documents", "doc", "docs", "google doc", "google docs"], 
         "mimeType = 'application/vnd.google-apps.document'"),
        
        # Google Sheets
        (["spreadsheet", "spreadsheets", "sheet", "sheets", "google sheet", "google sheets"], 
         "mimeType = 'application/vnd.google-apps.spreadsheet'"),
        
        # Google Slides
        (["presentation", "presentations", "slide", "slides", "google slide", "google slides"], 
         "mimeType = 'application/vnd.google-apps.presentation'"),
        
        # Folders
        (["folder", "folders", "directory", "directories"], 
         "mimeType = 'application/vnd.google-apps.folder'"),
        
        # Videos
        (["video", "videos", "movie", "movies", "mp4", "avi", "mov"], 
         "mimeType contains 'video/'"),
        
        # Audio
        (["audio", "sound", "music", "mp3", "wav"], 
         "mimeType contains 'audio/'"),
        
        # Text files
        (["text file", "text files", "txt"], 
         "mimeType = 'text/plain'"),
    ]

    # Check each mapping
    for keywords, mime_filter in type_mappings:
        # Check if any keyword matches the query (as whole word or part of phrase)
        for keyword in keywords:
            # Match keyword as whole word or with common modifiers
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_lower):
                return mime_filter

    return None


async def _locate_child_folder(
    service: Any,
    *,
    parent_id: str,
    folder_name: str,
    drive_id: Optional[str],
    include_items_from_all_drives: bool,
    corpora: Optional[str],
    page_size: int = 10,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Return the first folder named ``folder_name`` beneath ``parent_id``."""

    escaped_name = _escape_query_term(folder_name.strip())
    query = (
        f"'{parent_id}' in parents and "
        f"name = '{escaped_name}' and "
        "mimeType = 'application/vnd.google-apps.folder' and trashed=false"
    )
    params = _build_drive_list_params(
        query=query,
        page_size=min(page_size, 100),
        drive_id=drive_id,
        include_items_from_all_drives=include_items_from_all_drives,
        corpora=corpora,
    )

    folders: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    # Paginate until we have enough results or no more pages
    while len(folders) < page_size:
        if page_token:
            params["pageToken"] = page_token

        try:
            results = await asyncio.to_thread(service.files().list(**params).execute)
        except Exception as exc:
            return None, (
                f"Error resolving folder '{folder_name}' under parent '{parent_id}': {exc}"
            )

        page_folders = [
            item
            for item in results.get("files", [])
            if item.get("mimeType") == "application/vnd.google-apps.folder"
        ]
        folders.extend(page_folders)

        page_token = results.get("nextPageToken")
        if not page_token or len(folders) >= page_size:
            break

    if not folders:
        return None, None

    warning: Optional[str] = None
    if len(folders) > 1:
        candidates = ", ".join(
            f"{item.get('name', '(unknown)')} (ID: {item.get('id', 'unknown')})"
            for item in folders[1:4]
        )
        warning = (
            f"Multiple folders named '{folder_name}' found; using the most recently "
            f"modified match (ID: {folders[0].get('id', 'unknown')})."
        )
        if candidates:
            warning += f" Other candidates: {candidates}"

    return folders[0], warning


async def _resolve_folder_reference(
    service: Any,
    *,
    folder_id: Optional[str],
    folder_name: Optional[str],
    folder_path: Optional[str],
    drive_id: Optional[str],
    include_items_from_all_drives: bool,
    corpora: Optional[str],
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Resolve user folder selection inputs to a concrete folder ID."""

    warnings: List[str] = []

    normalized_id = (folder_id or "").strip()
    normalized_path = (folder_path or "").strip().strip("/")
    normalized_name = (folder_name or "").strip()

    base_id = normalized_id if normalized_id else "root"
    base_label = "root" if base_id == "root" else base_id

    if normalized_path:
        parent_id = base_id
        label_parts: List[str] = [] if base_id == "root" else [base_label]
        for segment in [
            part.strip() for part in normalized_path.split("/") if part.strip()
        ]:
            located, note = await _locate_child_folder(
                service,
                parent_id=parent_id,
                folder_name=segment,
                drive_id=drive_id,
                include_items_from_all_drives=include_items_from_all_drives,
                corpora=corpora,
            )
            scope = "/".join(label_parts) if label_parts else base_label
            if located is None:
                missing_context = scope or (
                    "root" if parent_id == "root" else parent_id
                )
                return (
                    None,
                    f"Unable to find folder '{segment}' within '{missing_context}'.",
                    warnings,
                )
            if note:
                warnings.append(note)
            parent_id = located.get("id", parent_id)
            label_parts.append(located.get("name", segment))

        final_label = "/".join(label_parts) if label_parts else base_label
        return parent_id, final_label or normalized_path, warnings

    if (not normalized_id or normalized_id.lower() == "root") and normalized_name:
        located, note = await _locate_child_folder(
            service,
            parent_id=base_id,
            folder_name=normalized_name,
            drive_id=drive_id,
            include_items_from_all_drives=include_items_from_all_drives,
            corpora=corpora,
        )
        scope = "root" if base_id == "root" else base_label
        if located is None:
            return (
                None,
                f"No folder named '{normalized_name}' was found under '{scope}'.",
                warnings,
            )
        if note:
            warnings.append(note)
        label = located.get("name", normalized_name)
        if scope != "root":
            label = f"{scope}/{label}"
        return located.get("id"), label, warnings

    final_id = normalized_id or "root"
    final_label = "root" if final_id == "root" else final_id
    return final_id, final_label, warnings


@mcp.tool("gdrive_search_files")
async def search_drive_files(
    query: str,
    user_email: str = DEFAULT_USER_EMAIL,
    page_size: int = 10,
    drive_id: Optional[str] = None,
    include_items_from_all_drives: bool = True,
    corpora: Optional[str] = None,
) -> str:
    """Search for files in Google Drive.
    
    Intelligently handles different query types:
    - File type queries (e.g., "image", "pdf", "spreadsheet") filter by MIME type
    - Structured queries (e.g., "name='report'") are passed through as-is
    - Text queries search in file names
    
    Examples:
        "image" -> Returns only image files (jpg, png, gif, etc.)
        "latest pdf" -> Returns PDF files, sorted by modification time
        "budget spreadsheet" -> Returns spreadsheet files with "budget" in the name
    """
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    is_structured = _is_structured_drive_query(query)
    escaped_query = _escape_query_term(query)
    mime_filter: Optional[str] = None
    search_terms: Optional[str] = None

    if is_structured:
        final_query = query
        strategy = "structured"
    else:
        mime_filter = _detect_file_type_query(query)
        if mime_filter:
            search_terms_value = query.lower()
            for keywords, _ in [
                (
                    [
                        "image",
                        "images",
                        "photo",
                        "photos",
                        "picture",
                        "pictures",
                        "img",
                        "png",
                        "jpg",
                        "jpeg",
                        "gif",
                    ],
                    None,
                ),
                (["pdf", "pdfs"], None),
                (["document", "documents", "doc", "docs"], None),
                (["spreadsheet", "spreadsheets", "sheet", "sheets"], None),
                (["presentation", "presentations", "slide", "slides"], None),
                (["folder", "folders"], None),
                (["video", "videos", "movie", "movies"], None),
                (["audio", "sound", "music"], None),
            ]:
                for keyword in keywords:
                    pattern = r"\b" + re.escape(keyword) + r"\b"
                    search_terms_value = re.sub(pattern, "", search_terms_value)

            search_terms_value = re.sub(
                r"\b(latest|recent|new|old|my)\b", "", search_terms_value
            )
            search_terms_value = search_terms_value.strip()
            search_terms = search_terms_value or None

            if search_terms:
                escaped_terms = _escape_query_term(search_terms)
                final_query = f"{mime_filter} and name contains '{escaped_terms}'"
                strategy = "mime_filter_with_name"
            else:
                final_query = mime_filter
                strategy = "mime_filter"
        else:
            final_query = f"name contains '{escaped_query}'"
            strategy = "name_contains"

    params = _build_drive_list_params(
        query=final_query,
        page_size=min(page_size, 100),
        drive_id=drive_id,
        include_items_from_all_drives=include_items_from_all_drives,
        corpora=corpora,
    )

    files: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    while len(files) < page_size:
        if page_token:
            params["pageToken"] = page_token

        try:
            results = await asyncio.to_thread(service.files().list(**params).execute)
        except Exception as exc:
            return _error_response(
                f"Error searching Drive files: {exc}", code="GOOGLE_API_ERROR"
            )

        page_files = results.get("files", [])
        files.extend(page_files)

        page_token = results.get("nextPageToken")
        if not page_token or len(files) >= page_size:
            break

    files = files[:page_size]
    formatted_files = [_format_drive_item(item) for item in files]

    return _success_response(
        data={
            "user_email": user_email,
            "count": len(formatted_files),
            "files": formatted_files,
            "next_page_token": page_token,
            "query": {
                "original": query,
                "resolved": final_query,
                "strategy": strategy,
                "mime_filter": mime_filter,
                "search_terms": search_terms,
                "page_size": page_size,
                "drive_id": drive_id,
                "include_items_from_all_drives": include_items_from_all_drives,
                "corpora": corpora,
            },
        },
        message=f"No files found for '{query}'." if not files else None,
    )


@mcp.tool("gdrive_list_folder")
async def list_drive_items(
    folder_id: Optional[str] = "root",
    folder_name: Optional[str] = None,
    folder_path: Optional[str] = None,
    user_email: str = DEFAULT_USER_EMAIL,
    page_size: int = 100,
    drive_id: Optional[str] = None,
    include_items_from_all_drives: bool = True,
    corpora: Optional[str] = None,
) -> str:
    """
    List the contents of a Google Drive folder.

    Provide one of the following to identify the folder:
    - `folder_id` (defaults to "root")
    - `folder_name` for a direct child under the selected parent
    - `folder_path` like "Reports/2024" relative to the parent/root
    """
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    resolved_id, display_label, warnings = await _resolve_folder_reference(
        service,
        folder_id=folder_id,
        folder_name=folder_name,
        folder_path=folder_path,
        drive_id=drive_id,
        include_items_from_all_drives=include_items_from_all_drives,
        corpora=corpora,
    )

    if resolved_id is None:
        return _error_response(
            display_label or "Unable to resolve folder selection.",
            code="FOLDER_RESOLUTION_FAILED",
            details={
                "folder_id": folder_id,
                "folder_name": folder_name,
                "folder_path": folder_path,
            },
            warnings=warnings,
        )

    query = f"'{resolved_id}' in parents and trashed=false"
    params = _build_drive_list_params(
        query=query,
        page_size=min(page_size, 100),
        drive_id=drive_id,
        include_items_from_all_drives=include_items_from_all_drives,
        corpora=corpora,
    )

    files: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    while len(files) < page_size:
        if page_token:
            params["pageToken"] = page_token

        try:
            results = await asyncio.to_thread(service.files().list(**params).execute)
        except Exception as exc:
            return _error_response(
                f"Error listing Drive items: {exc}", code="GOOGLE_API_ERROR"
            )

        page_files = results.get("files", [])
        files.extend(page_files)

        page_token = results.get("nextPageToken")
        if not page_token or len(files) >= page_size:
            break

    files = files[:page_size]
    formatted_items = [_format_drive_item(item) for item in files]

    return _success_response(
        data={
            "user_email": user_email,
            "folder": {
                "requested": {
                    "id": folder_id,
                    "name": folder_name,
                    "path": folder_path,
                },
                "resolved_id": resolved_id,
                "display_label": display_label,
            },
            "count": len(formatted_items),
            "items": formatted_items,
            "next_page_token": page_token,
        },
        warnings=warnings or None,
        message=(
            f"No items found in folder '{display_label}'."
            if not formatted_items
            else None
        ),
    )


@mcp.tool("gdrive_get_file_content")
async def get_drive_file_content(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    try:
        metadata = await asyncio.to_thread(
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error retrieving metadata for file {file_id}: {exc}",
            code="GOOGLE_API_ERROR",
        )

    mime_type = metadata.get("mimeType", "")
    export_mappings = {
        "application/vnd.google-apps.document": "text/plain",
        "application/vnd.google-apps.spreadsheet": "text/csv",
        "application/vnd.google-apps.presentation": "text/plain",
    }
    export_mime = export_mappings.get(mime_type)

    request = (
        service.files().export_media(fileId=file_id, mimeType=export_mime)
        if export_mime
        else service.files().get_media(fileId=file_id)
    )

    try:
        content_bytes = await _download_request_bytes(request)
    except ValueError as exc:
        return _error_response(f"File too large: {exc}", code="FILE_TOO_LARGE")
    except Exception as exc:
        return _error_response(
            f"Error downloading file content: {exc}", code="GOOGLE_API_ERROR"
        )

    content_length = len(content_bytes)
    office_mime_types = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    extraction_method = "utf-8-decode"
    body_text: str

    if mime_type == "application/pdf":
        try:
            def _extract_pdf() -> Tuple[str, bool]:
                payload = base64.b64encode(content_bytes).decode("ascii")
                result: Dict[str, Any] = kb_extract_bytes(
                    content_base64=payload,
                    mime_type=mime_type,
                )
                text = str(result.get("content") or result.get("text") or "").strip()
                used_ocr = False

                if not text:
                    try:
                        result_ocr: Dict[str, Any] = kb_extract_bytes(
                            content_base64=payload,
                            mime_type=mime_type,
                            force_ocr=True,
                        )
                        text = str(
                            result_ocr.get("content") or result_ocr.get("text") or ""
                        ).strip()
                        used_ocr = bool(text)
                    except Exception:
                        pass
                return text, used_ocr

            extracted_text, used_ocr = await asyncio.to_thread(_extract_pdf)
            extraction_method = "pdf_extractor_ocr" if used_ocr else "pdf_extractor"
            body_text = extracted_text

            if not body_text:
                try:
                    body_text = content_bytes.decode("utf-8")
                    extraction_method = "utf-8-decode"
                except UnicodeDecodeError:
                    body_text = (
                        f"[Binary or unsupported text encoding for mimeType '{mime_type}' - "
                        f"{content_length} bytes]"
                    )
                    extraction_method = "binary-placeholder"
        except Exception:
            try:
                body_text = content_bytes.decode("utf-8")
                extraction_method = "utf-8-decode"
            except UnicodeDecodeError:
                body_text = (
                    f"[Binary or unsupported text encoding for mimeType '{mime_type}' - "
                    f"{content_length} bytes]"
                )
                extraction_method = "binary-placeholder"
    elif mime_type in office_mime_types:
        try:
            body_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body_text = (
                f"[Binary Office document - text extraction not supported for mimeType '{mime_type}' - "
                f"{content_length} bytes]"
            )
            extraction_method = "binary-placeholder"
    else:
        try:
            body_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body_text = (
                f"[Binary or unsupported text encoding for mimeType '{mime_type}' - "
                f"{content_length} bytes]"
            )
            extraction_method = "binary-placeholder"

    return _success_response(
        data={
            "file": _format_drive_item(metadata),
            "content": body_text,
            "extraction": {
                "export_mime_type": export_mime,
                "method": extraction_method,
                "byte_length": content_length,
            },
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_create_file")
async def create_drive_file(
    file_name: str,
    user_email: str = DEFAULT_USER_EMAIL,
    content: Optional[str] = None,
    folder_id: str = "root",
    mime_type: str = "text/plain",
    file_url: Optional[str] = None,
) -> str:
    if not content and not file_url:
        return _error_response(
            "You must provide either 'content' or 'file_url'.", code="INVALID_INPUT"
        )

    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    normalized_folder_id = _normalize_parent_id(folder_id)

    data: bytes
    if file_url:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0, connect=5.0)
            ) as client:
                head_resp = await client.head(file_url, follow_redirects=True)
                if head_resp.status_code == 200:
                    content_length = head_resp.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_CONTENT_BYTES:
                        return _error_response(
                            (
                                f"File at URL is too large ({int(content_length)} bytes). "
                                f"Maximum allowed size is {MAX_CONTENT_BYTES} bytes "
                                f"(~{MAX_CONTENT_BYTES // (1024 * 1024)}MB)."
                            ),
                            code="PAYLOAD_TOO_LARGE",
                        )

                resp = await client.get(file_url, follow_redirects=True)
                resp.raise_for_status()
                data = await resp.aread()

                if len(data) > MAX_CONTENT_BYTES:
                    return _error_response(
                        (
                            f"File content from URL is too large ({len(data)} bytes). "
                            f"Maximum allowed size is {MAX_CONTENT_BYTES} bytes "
                            f"(~{MAX_CONTENT_BYTES // (1024 * 1024)}MB)."
                        ),
                        code="PAYLOAD_TOO_LARGE",
                    )

                content_type = resp.headers.get("Content-Type")
                if content_type and content_type != "application/octet-stream":
                    mime_type = content_type
        except httpx.TimeoutException:
            return _error_response(
                f"Request timed out while fetching file from URL '{file_url}'.",
                code="FILE_DOWNLOAD_TIMEOUT",
            )
        except httpx.HTTPStatusError as exc:
            return _error_response(
                f"HTTP error fetching file from URL '{file_url}': {exc.response.status_code}",
                code="FILE_DOWNLOAD_ERROR",
            )
        except Exception as exc:
            return _error_response(
                f"Failed to fetch file from URL '{file_url}': {exc}",
                code="FILE_DOWNLOAD_ERROR",
            )
    else:
        data = (content or "").encode("utf-8")

    metadata = {
        "name": file_name,
        "parents": [normalized_folder_id],
        "mimeType": mime_type,
    }
    media_stream = io.BytesIO(data)
    media = MediaIoBaseUpload(media_stream, mimetype=mime_type, resumable=False)

    try:
        created = await asyncio.to_thread(
            service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, name, mimeType, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error creating Drive file: {exc}", code="GOOGLE_API_ERROR"
        )

    created.setdefault("mimeType", mime_type)

    return _success_response(
        data={
            "file": _format_drive_item(created),
            "parent_folder_id": normalized_folder_id,
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_delete_file")
async def delete_drive_file(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
    permanent: bool = False,
) -> str:
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    try:
        metadata = await asyncio.to_thread(
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, parents",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error retrieving Drive file {file_id}: {exc}",
            code="GOOGLE_API_ERROR",
        )

    file_name = metadata.get("name", "(unknown)") if isinstance(metadata, dict) else "(unknown)"
    previous_parents = (
        (metadata.get("parents") or []) if isinstance(metadata, dict) else None
    )

    try:
        if permanent:
            await asyncio.to_thread(
                service.files().delete(fileId=file_id, supportsAllDrives=True).execute
            )
            return _success_response(
                data={
                    "file_id": file_id,
                    "file_name": file_name,
                    "action": "permanently_deleted",
                    "user_email": user_email,
                    "previous_parent_ids": previous_parents,
                }
            )

        trashed = await asyncio.to_thread(
            service.files()
            .update(
                fileId=file_id,
                body={"trashed": True},
                fields="id, name, trashed",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error deleting Drive file {file_id}: {exc}", code="GOOGLE_API_ERROR"
        )

    trashed_name = (
        trashed.get("name", file_name) if isinstance(trashed, dict) else file_name
    )
    return _success_response(
        data={
            "file_id": file_id,
            "file_name": trashed_name,
            "action": "trashed",
            "user_email": user_email,
            "previous_parent_ids": previous_parents,
        }
    )


@mcp.tool("gdrive_move_file")
async def move_drive_file(
    file_id: str,
    destination_folder_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    try:
        metadata = await asyncio.to_thread(
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, parents",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error retrieving Drive file {file_id}: {exc}",
            code="GOOGLE_API_ERROR",
        )

    current_parents = (
        (metadata.get("parents") or []) if isinstance(metadata, dict) else []
    )
    remove_parents = ",".join(current_parents)

    update_kwargs = {
        "fileId": file_id,
        "addParents": destination_folder_id,
        "fields": "id, name, parents",
        "supportsAllDrives": True,
    }
    if remove_parents:
        update_kwargs["removeParents"] = remove_parents

    try:
        updated = await asyncio.to_thread(
            service.files().update(**update_kwargs).execute
        )
    except Exception as exc:
        return _error_response(
            f"Error moving Drive file {file_id}: {exc}", code="GOOGLE_API_ERROR"
        )

    new_name = (
        updated.get("name", metadata.get("name", "(unknown)"))
        if isinstance(updated, dict)
        else metadata.get("name", "(unknown)")
    )
    return _success_response(
        data={
            "file_id": file_id,
            "file_name": new_name,
            "destination_folder_id": destination_folder_id,
            "previous_parent_ids": current_parents,
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_copy_file")
async def copy_drive_file(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
    new_name: Optional[str] = None,
    destination_folder_id: Optional[str] = None,
) -> str:
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    body: Dict[str, object] = {}
    if new_name:
        body["name"] = new_name
    if destination_folder_id:
        normalized_dest = _normalize_parent_id(destination_folder_id)
        body["parents"] = [normalized_dest]

    try:
        copied = await asyncio.to_thread(
            service.files()
            .copy(
                fileId=file_id,
                body=body,
                fields="id, name, mimeType, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error copying Drive file {file_id}: {exc}", code="GOOGLE_API_ERROR"
        )

    return _success_response(
        data={
            "source_file_id": file_id,
            "file": _format_drive_item(copied),
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_rename_file")
async def rename_drive_file(
    file_id: str,
    new_name: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    if not new_name.strip():
        return _error_response(
            "A non-empty new_name is required to rename a file.",
            code="INVALID_INPUT",
        )

    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    try:
        updated = await asyncio.to_thread(
            service.files()
            .update(
                fileId=file_id,
                body={"name": new_name},
                fields="id, name",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error renaming Drive file {file_id}: {exc}", code="GOOGLE_API_ERROR"
        )

    final_name = (
        updated.get("name", new_name) if isinstance(updated, dict) else new_name
    )
    return _success_response(
        data={
            "file_id": file_id,
            "file_name": final_name,
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_create_folder")
async def create_drive_folder(
    folder_name: str,
    user_email: str = DEFAULT_USER_EMAIL,
    parent_folder_id: str = "root",
) -> str:
    if not folder_name.strip():
        return _error_response(
            "A non-empty folder_name is required to create a folder.",
            code="INVALID_INPUT",
        )

    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    normalized_parent = _normalize_parent_id(parent_folder_id)

    body = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [normalized_parent],
    }

    try:
        created = await asyncio.to_thread(
            service.files()
            .create(
                body=body,
                fields="id, name, mimeType, parents, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error creating Drive folder '{folder_name}': {exc}",
            code="GOOGLE_API_ERROR",
        )

    return _success_response(
        data={
            "folder": _format_drive_item(created),
            "parent_folder_id": normalized_parent,
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_file_permissions")
async def get_drive_file_permissions(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    try:
        metadata = await asyncio.to_thread(
            service.files()
            .get(
                fileId=file_id,
                fields=(
                    "id, name, mimeType, size, modifiedTime, owners, permissions, "
                    "webViewLink, webContentLink, shared, sharingUser, viewersCanCopyContent"
                ),
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error retrieving permissions for file {file_id}: {exc}",
            code="GOOGLE_API_ERROR",
        )

    permissions = metadata.get("permissions") or []
    has_public = _has_anyone_link_access(permissions)

    owners = [
        {
            "display_name": owner.get("displayName"),
            "email_address": owner.get("emailAddress"),
        }
        for owner in (metadata.get("owners") or [])
    ]
    sharing_user = metadata.get("sharingUser") or {}

    return _success_response(
        data={
            "file": _format_drive_item(metadata),
            "size_bytes": _safe_int(metadata.get("size")),
            "modified_time": metadata.get("modifiedTime"),
            "owners": owners,
            "permissions": [_format_permission(p) for p in permissions],
            "shared": metadata.get("shared", False),
            "sharing_user": {
                "display_name": sharing_user.get("displayName"),
                "email_address": sharing_user.get("emailAddress"),
            }
            if sharing_user
            else None,
            "viewers_can_copy_content": metadata.get("viewersCanCopyContent"),
            "links": {
                "view": metadata.get("webViewLink"),
                "download": metadata.get("webContentLink"),
            },
            "has_public_link": has_public,
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_display_image")
async def display_drive_image(
    file_id: str,
    session_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Download an image from Google Drive and display it in the chat."""
    if not session_id or not session_id.strip():
        return _error_response(
            "session_id is required to display the image in chat.",
            code="INVALID_INPUT",
        )

    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    try:
        metadata = await asyncio.to_thread(
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, size, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error retrieving metadata for file {file_id}: {exc}",
            code="GOOGLE_API_ERROR",
        )

    mime_type = metadata.get("mimeType", "")
    file_name = metadata.get("name", "image")

    if not mime_type.startswith("image/"):
        return _error_response(
            (
                f"File '{file_name}' is not an image (type: {mime_type}). "
                "Only image files can be displayed."
            ),
            code="UNSUPPORTED_MIME_TYPE",
        )

    request = service.files().get_media(fileId=file_id)

    try:
        image_bytes = await _download_request_bytes(request, max_size=MAX_CONTENT_BYTES)
    except ValueError as exc:
        return _error_response(f"Image too large: {exc}", code="FILE_TOO_LARGE")
    except Exception as exc:
        return _error_response(
            f"Error downloading image: {exc}", code="GOOGLE_API_ERROR"
        )

    try:
        from backend.services.attachments import AttachmentError, AttachmentTooLarge

        attachment_service = await _get_attachment_service()
        record = await attachment_service.save_bytes(
            session_id=session_id,
            data=image_bytes,
            mime_type=mime_type,
            filename_hint=file_name,
        )
    except AttachmentTooLarge as exc:
        return _error_response(f"Image rejected: {exc}", code="PAYLOAD_TOO_LARGE")
    except AttachmentError as exc:
        return _error_response(
            f"Failed to store image: {exc}", code="ATTACHMENT_STORAGE_ERROR"
        )

    attachment_metadata = record.get("metadata") or {}
    stored_filename = attachment_metadata.get("filename") or file_name
    signed_url = record.get("signed_url") or record.get("display_url")
    expires_at = record.get("expires_at") or record.get("signed_url_expires_at")

    return _success_response(
        data={
            "file": _format_drive_item(metadata),
            "attachment": {
                "attachment_id": record.get("attachment_id"),
                "filename": stored_filename,
                "size_bytes": record.get("size_bytes"),
                "signed_url": signed_url,
                "signed_url_expires_at": expires_at,
            },
            "session_id": session_id,
            "user_email": user_email,
        }
    )


@mcp.tool("gdrive_check_public_access")
async def check_drive_file_public_access(
    file_name: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    service, error_msg = _get_drive_service_or_error(user_email)
    if error_msg:
        return _error_response(error_msg, code="DRIVE_SERVICE_ERROR")
    assert service is not None

    escaped_name = _escape_query_term(file_name)
    query = f"name = '{escaped_name}'"
    params = {
        "q": query,
        "pageSize": 10,
        "fields": "files(id, name, mimeType, webViewLink, shared)",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }

    try:
        results = await asyncio.to_thread(service.files().list(**params).execute)
    except Exception as exc:
        return _error_response(
            f"Error searching for file '{file_name}': {exc}",
            code="GOOGLE_API_ERROR",
        )

    files = results.get("files", [])
    candidate_summaries = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "mime_type": item.get("mimeType"),
            "web_view_link": item.get("webViewLink"),
            "shared": item.get("shared"),
        }
        for item in files
    ]

    if not files:
        return _success_response(
            data={
                "file_name": file_name,
                "matches": [],
                "user_email": user_email,
            },
            message=f"No file found with name '{file_name}'.",
        )

    first = files[0]
    file_id = first.get("id")
    try:
        metadata = await asyncio.to_thread(
            service.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, permissions, webViewLink, webContentLink, shared",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return _error_response(
            f"Error retrieving permissions for file '{file_id}': {exc}",
            code="GOOGLE_API_ERROR",
        )

    permissions = metadata.get("permissions") or []
    has_public = _has_anyone_link_access(permissions)
    remediation = (
        "Drive → Share → 'Anyone with the link' → 'Viewer'"
        if not has_public
        else None
    )

    return _success_response(
        data={
            "file_name": file_name,
            "matches": candidate_summaries,
            "evaluated_file": {
                "file": _format_drive_item(metadata),
                "permissions": [_format_permission(p) for p in permissions],
                "has_public_link": has_public,
                "shared": metadata.get("shared", False),
                "direct_public_link": f"https://drive.google.com/uc?export=view&id={file_id}"
                if has_public
                else None,
                "remediation": remediation,
            },
            "user_email": user_email,
        }
    )


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "run",
    "search_drive_files",
    "list_drive_items",
    "get_drive_file_content",
    "create_drive_file",
    "delete_drive_file",
    "move_drive_file",
    "copy_drive_file",
    "rename_drive_file",
    "create_drive_folder",
    "get_drive_file_permissions",
    "display_drive_image",
    "check_drive_file_public_access",
]
