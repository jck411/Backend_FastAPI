"""Custom MCP server for Google Drive integration."""

from __future__ import annotations

import asyncio
import io
import zipfile
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Tuple

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

from backend.config import get_settings
from backend.services.google_auth.auth import (
    authorize_user,
    get_credentials,
    get_drive_service,
)

mcp = FastMCP("custom-gdrive")

DEFAULT_USER_EMAIL = "jck411@gmail.com"
DRIVE_BATCH_SIZE = 25
DRIVE_FIELDS_MINIMAL = (
    "files(id, name, mimeType, size, modifiedTime, webViewLink, iconLink)"
)


def _escape_query_term(value: str) -> str:
    return value.replace("'", "\\'")


def _resolve_redirect_uri(redirect_uri: Optional[str]) -> str:
    if redirect_uri:
        return redirect_uri

    try:
        settings = get_settings()
        return settings.google_oauth_redirect_uri
    except Exception:
        return "http://localhost:8000/api/google-auth/callback"


def _build_drive_list_params(
    *,
    query: str,
    page_size: int,
    drive_id: Optional[str],
    include_items_from_all_drives: bool,
    corpora: Optional[str],
) -> Dict[str, object]:
    params: Dict[str, object] = {
        "q": query,
        "pageSize": max(page_size, 1),
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": include_items_from_all_drives,
        "fields": DRIVE_FIELDS_MINIMAL,
        "orderBy": "modifiedTime desc",
    }

    if drive_id:
        params["driveId"] = drive_id
        params["corpora"] = corpora or "drive"
    elif corpora:
        params["corpora"] = corpora

    return params


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
    """Return the first folder matching folder_name under parent_id plus optional warning."""

    escaped_name = _escape_query_term(folder_name.strip())
    query = (
        f"'{parent_id}' in parents and "
        f"name = '{escaped_name}' and "
        "mimeType = 'application/vnd.google-apps.folder' and trashed=false"
    )
    params = _build_drive_list_params(
        query=query,
        page_size=page_size,
        drive_id=drive_id,
        include_items_from_all_drives=include_items_from_all_drives,
        corpora=corpora,
    )

    try:
        results = await asyncio.to_thread(service.files().list(**params).execute)
    except Exception as exc:
        return None, (
            f"Error resolving folder '{folder_name}' under parent '{parent_id}': {exc}"
        )

    folders = [
        item
        for item in results.get("files", [])
        if item.get("mimeType") == "application/vnd.google-apps.folder"
    ]
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
    """Return (folder_id, display_label, warnings) or (None, error_message, warnings)."""

    warnings: List[str] = []

    normalized_id = (folder_id or "").strip()
    normalized_path = (folder_path or "").strip().strip("/")
    normalized_name = (folder_name or "").strip()

    base_id = normalized_id if normalized_id else "root"
    base_label = "root" if base_id == "root" else base_id

    if normalized_path:
        parent_id = base_id
        label_parts: List[str] = [] if base_id == "root" else [base_label]
        for segment in [part.strip() for part in normalized_path.split("/") if part.strip()]:
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
                missing_context = scope or ("root" if parent_id == "root" else parent_id)
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


def _iter_text(el) -> Iterable[str]:
    text = (el.text or "").strip()
    if text:
        yield text

    for child in el:
        yield from _iter_text(child)
        tail = (child.tail or "").strip()
        if tail:
            yield tail


def _extract_office_xml_text(data: bytes, mime_type: str) -> Optional[str]:
    """Best-effort extraction of text from Office Open XML documents."""
    targets: Dict[str, tuple[str, ...]] = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            "word/",
        ),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
            "ppt/",
        ),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("xl/",),
    }

    prefixes = targets.get(mime_type)
    if not prefixes:
        return None

    try:
        namespace_filter = prefixes
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            snippets: List[str] = []
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                if not name.startswith(namespace_filter):
                    continue
                with archive.open(name) as xml_file:
                    try:
                        import xml.etree.ElementTree as ET

                        root = ET.fromstring(xml_file.read())
                    except Exception:
                        continue
                    for fragment in _iter_text(root):
                        snippets.append(fragment)
            combined = "\n".join(fragment for fragment in snippets if fragment)
            return combined or None
    except zipfile.BadZipFile:
        return None


def _check_public_link_permission(permissions: List[Dict[str, object]]) -> bool:
    for perm in permissions or []:
        if perm.get("type") == "anyone" and perm.get("role") in {
            "reader",
            "commenter",
            "writer",
        }:
            return True
    return False


def _get_drive_image_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=view&id={file_id}&page=1&attredirects=0"


@mcp.tool("gdrive_auth_status")
async def auth_status(user_email: str = DEFAULT_USER_EMAIL) -> str:
    try:
        credentials = get_credentials(user_email)
    except FileNotFoundError:
        credentials = None
    except Exception as exc:
        return f"Error checking authorization status: {exc}"

    if credentials:
        expiry = getattr(credentials, "expiry", None)
        expiry_text = expiry.isoformat() if expiry else "unknown expiry"
        return (
            f"{user_email} is already authorized for Google Drive. "
            f"Existing token expires at {expiry_text}. "
            "Use gdrive_generate_auth_url with force=true to start a fresh consent flow."
        )

    return (
        f"No stored Google Drive credentials found for {user_email}. "
        "Run gdrive_generate_auth_url to generate an authorization link."
    )


@mcp.tool("gdrive_generate_auth_url")
async def generate_auth_url(
    user_email: str = DEFAULT_USER_EMAIL,
    redirect_uri: Optional[str] = None,
    force: bool = False,
) -> str:
    try:
        credentials = get_credentials(user_email)
    except FileNotFoundError:
        credentials = None
    except Exception as exc:
        return f"Error checking existing credentials: {exc}"

    if credentials and not force:
        expiry = getattr(credentials, "expiry", None)
        expiry_text = expiry.isoformat() if expiry else "unknown expiry"
        return (
            f"{user_email} already has stored credentials (expires {expiry_text}). "
            "Set force=true if you want to start a fresh consent flow."
        )

    try:
        effective_redirect = _resolve_redirect_uri(redirect_uri)
        auth_url = authorize_user(user_email, effective_redirect)
    except FileNotFoundError as exc:
        return (
            "Missing OAuth client configuration. "
            f"{exc}. Ensure client_secret_*.json is placed in the credentials directory."
        )
    except Exception as exc:
        return f"Error generating authorization URL: {exc}"

    effective_redirect = _resolve_redirect_uri(redirect_uri)

    return (
        "Follow these steps to finish Google Drive authorization:\n"
        f"1. Visit: {auth_url}\n"
        "2. Approve access to your Drive account.\n"
        f"3. You will be redirected to {effective_redirect}; the backend will store the token automatically.\n"
        "After completing the flow, run gdrive_auth_status to confirm success.\n"
        "Note: Google may warn that the app is unverified. Choose Advanced → Continue to proceed for testing accounts added on the OAuth consent screen."
    )


@mcp.tool("gdrive_search_files")
async def search_drive_files(
    query: str,
    user_email: str = DEFAULT_USER_EMAIL,
    page_size: int = 10,
    drive_id: Optional[str] = None,
    include_items_from_all_drives: bool = True,
    corpora: Optional[str] = None,
) -> str:
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

    # Basic heuristic to detect Drive query syntax
    structured_keywords = [
        "name ",
        "mimeType",
        "modifiedTime",
        "fullText",
        "parents",
        " and ",
        " or ",
        "'",
    ]
    is_structured = any(keyword in query for keyword in structured_keywords)
    escaped_query = _escape_query_term(query)
    final_query = query if is_structured else f"fullText contains '{escaped_query}'"

    params = _build_drive_list_params(
        query=final_query,
        page_size=page_size,
        drive_id=drive_id,
        include_items_from_all_drives=include_items_from_all_drives,
        corpora=corpora,
    )

    try:
        results = await asyncio.to_thread(service.files().list(**params).execute)
    except Exception as exc:
        return f"Error searching Drive files: {exc}"

    files = results.get("files", [])
    if not files:
        return f"No files found for '{query}'."

    lines = [
        f"Found {len(files)} files for {user_email} matching '{query}':",
        "",
    ]
    for item in files:
        size_text = f", Size: {item.get('size', 'N/A')}" if "size" in item else ""
        lines.append(
            f'- Name: "{item.get("name", "(unknown)")}" '
            f"(ID: {item.get('id', 'unknown')}, Type: {item.get('mimeType', 'unknown')}"
            f"{size_text}, Modified: {item.get('modifiedTime', 'N/A')}) "
            f"Link: {item.get('webViewLink', '#')}"
        )
    return "\n".join(lines)


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
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

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
        detail_lines = [display_label or "Unable to resolve folder selection."]
        if warnings:
            detail_lines.extend(warnings)
        return "\n".join(detail_lines)

    query = f"'{resolved_id}' in parents and trashed=false"
    params = _build_drive_list_params(
        query=query,
        page_size=page_size,
        drive_id=drive_id,
        include_items_from_all_drives=include_items_from_all_drives,
        corpora=corpora,
    )

    try:
        results = await asyncio.to_thread(service.files().list(**params).execute)
    except Exception as exc:
        return f"Error listing Drive items: {exc}"

    files = results.get("files", [])
    if not files:
        response_lines = [f"No items found in folder '{display_label}'."]
        if warnings:
            response_lines.extend(warnings)
        return "\n".join(response_lines)

    lines = [
        f"Found {len(files)} items in folder '{display_label}' for {user_email}:",
        "",
    ]
    for item in files:
        size_text = f", Size: {item.get('size', 'N/A')}" if "size" in item else ""
        lines.append(
            f'- Name: "{item.get("name", "(unknown)")}" '
            f"(ID: {item.get('id', 'unknown')}, Type: {item.get('mimeType', 'unknown')}"
            f"{size_text}, Modified: {item.get('modifiedTime', 'N/A')}) "
            f"Link: {item.get('webViewLink', '#')}"
        )
    if warnings:
        lines.extend(["", *warnings])
    return "\n".join(lines)


@mcp.tool("gdrive_get_file_content")
async def get_drive_file_content(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

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
        return f"Error retrieving metadata for file {file_id}: {exc}"

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

    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    loop = asyncio.get_running_loop()
    done = False
    try:
        while not done:
            _, done = await loop.run_in_executor(None, downloader.next_chunk)
    except Exception as exc:
        return f"Error downloading file content: {exc}"

    content_bytes = buffer.getvalue()
    office_mime_types = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    body_text: str
    if mime_type in office_mime_types:
        extracted = _extract_office_xml_text(content_bytes, mime_type)
        if extracted:
            body_text = extracted
        else:
            try:
                body_text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                body_text = (
                    f"[Binary or unsupported text encoding for mimeType '{mime_type}' - "
                    f"{len(content_bytes)} bytes]"
                )
    else:
        try:
            body_text = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body_text = (
                f"[Binary or unsupported text encoding for mimeType '{mime_type}' - "
                f"{len(content_bytes)} bytes]"
            )

    header = (
        f'File: "{metadata.get("name", "Unknown File")}" '
        f"(ID: {file_id}, Type: {mime_type})\n"
        f"Link: {metadata.get('webViewLink', '#')}\n\n--- CONTENT ---\n"
    )
    return header + body_text


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
        return "You must provide either 'content' or 'file_url'."

    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

    data: bytes
    if file_url:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                data = await resp.aread()
                content_type = resp.headers.get("Content-Type")
                if content_type and content_type != "application/octet-stream":
                    mime_type = content_type
        except Exception as exc:
            return f"Failed to fetch file from URL '{file_url}': {exc}"
    else:
        data = (content or "").encode("utf-8")

    metadata = {
        "name": file_name,
        "parents": [folder_id],
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
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return f"Error creating Drive file: {exc}"

    link = created.get("webViewLink", "N/A")
    return (
        f"Successfully created file '{created.get('name', file_name)}' "
        f"(ID: {created.get('id', 'unknown')}) in folder '{folder_id}' for {user_email}. "
        f"Link: {link}"
    )


@mcp.tool("gdrive_delete_file")
async def delete_drive_file(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
    permanent: bool = False,
) -> str:
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

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
        return f"Error retrieving Drive file {file_id}: {exc}"

    file_name = (
        metadata.get("name", "(unknown)") if isinstance(metadata, dict) else "(unknown)"
    )

    try:
        if permanent:
            await asyncio.to_thread(
                service.files().delete(fileId=file_id, supportsAllDrives=True).execute
            )
            return f"File '{file_name}' (ID: {file_id}) permanently deleted."

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
        return f"Error deleting Drive file {file_id}: {exc}"

    trashed_name = (
        trashed.get("name", file_name) if isinstance(trashed, dict) else file_name
    )
    return f"File '{trashed_name}' (ID: {file_id}) moved to trash."


@mcp.tool("gdrive_move_file")
async def move_drive_file(
    file_id: str,
    destination_folder_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

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
        return f"Error retrieving Drive file {file_id}: {exc}"

    current_parents = metadata.get("parents", []) if isinstance(metadata, dict) else []
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
        return f"Error moving Drive file {file_id}: {exc}"

    new_name = (
        updated.get("name", metadata.get("name", "(unknown)"))
        if isinstance(updated, dict)
        else metadata.get("name", "(unknown)")
    )
    return (
        f"File '{new_name}' (ID: {file_id}) moved to folder '{destination_folder_id}'."
    )


@mcp.tool("gdrive_copy_file")
async def copy_drive_file(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
    new_name: Optional[str] = None,
    destination_folder_id: Optional[str] = None,
) -> str:
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

    body: Dict[str, object] = {}
    if new_name:
        body["name"] = new_name
    if destination_folder_id:
        body["parents"] = [destination_folder_id]

    try:
        copied = await asyncio.to_thread(
            service.files()
            .copy(
                fileId=file_id,
                body=body,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return f"Error copying Drive file {file_id}: {exc}"

    copy_name = copied.get("name", "(unknown)")
    copy_id = copied.get("id", "(unknown)")
    link = copied.get("webViewLink", "N/A")
    return (
        f"Created copy '{copy_name}' (ID: {copy_id}) from file {file_id}. Link: {link}"
    )


@mcp.tool("gdrive_rename_file")
async def rename_drive_file(
    file_id: str,
    new_name: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    if not new_name.strip():
        return "A non-empty new_name is required to rename a file."

    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

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
        return f"Error renaming Drive file {file_id}: {exc}"

    final_name = (
        updated.get("name", new_name) if isinstance(updated, dict) else new_name
    )
    return f"File {file_id} renamed to '{final_name}'."


@mcp.tool("gdrive_create_folder")
async def create_drive_folder(
    folder_name: str,
    user_email: str = DEFAULT_USER_EMAIL,
    parent_folder_id: str = "root",
) -> str:
    if not folder_name.strip():
        return "A non-empty folder_name is required to create a folder."

    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

    body = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_folder_id or "root"],
    }

    try:
        created = await asyncio.to_thread(
            service.files()
            .create(
                body=body,
                fields="id, name, parents, webViewLink",
                supportsAllDrives=True,
            )
            .execute
        )
    except Exception as exc:
        return f"Error creating Drive folder '{folder_name}': {exc}"

    folder_id = created.get("id", "(unknown)")
    link = created.get("webViewLink", "N/A")
    return (
        f"Created folder '{created.get('name', folder_name)}' "
        f"(ID: {folder_id}) under parent '{parent_folder_id}'. Link: {link}"
    )


@mcp.tool("gdrive_file_permissions")
async def get_drive_file_permissions(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

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
        return f"Error retrieving permissions for file {file_id}: {exc}"

    lines = [
        f"File: {metadata.get('name', 'Unknown')}",
        f"ID: {file_id}",
        f"Type: {metadata.get('mimeType', 'Unknown')}",
        f"Size: {metadata.get('size', 'N/A')} bytes",
        f"Modified: {metadata.get('modifiedTime', 'N/A')}",
        "",
        "Sharing Status:",
        f"  Shared: {metadata.get('shared', False)}",
    ]
    sharing_user = metadata.get("sharingUser")
    if sharing_user:
        lines.append(
            f"  Shared by: {sharing_user.get('displayName', 'Unknown')} "
            f"({sharing_user.get('emailAddress', 'Unknown')})"
        )

    permissions = metadata.get("permissions", [])
    if permissions:
        lines.append(f"  Number of permissions: {len(permissions)}")
        lines.append("  Permissions:")
        for perm in permissions:
            perm_type = perm.get("type", "unknown")
            role = perm.get("role", "unknown")
            if perm_type == "anyone":
                lines.append(f"    - Anyone with the link ({role})")
            elif perm_type in {"user", "group"}:
                lines.append(
                    f"    - {perm_type.title()}: {perm.get('emailAddress', 'unknown')} ({role})"
                )
            elif perm_type == "domain":
                lines.append(f"    - Domain: {perm.get('domain', 'unknown')} ({role})")
            else:
                lines.append(f"    - {perm_type} ({role})")
    else:
        lines.append("  No additional permissions (private file)")

    lines.extend(
        [
            "",
            "URLs:",
            f"  View Link: {metadata.get('webViewLink', 'N/A')}",
        ]
    )
    if metadata.get("webContentLink"):
        lines.append(f"  Direct Download Link: {metadata['webContentLink']}")

    if _check_public_link_permission(permissions):
        lines.extend(
            [
                "",
                "✅ This file is shared with 'Anyone with the link' - it can be inserted into Google Docs.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "❌ This file is NOT shared with 'Anyone with the link' - it cannot be inserted into Google Docs.",
                "   To fix: Right-click the file in Google Drive → Share → Anyone with the link → Viewer",
            ]
        )

    return "\n".join(lines)


@mcp.tool("gdrive_check_public_access")
async def check_drive_file_public_access(
    file_name: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    try:
        service = get_drive_service(user_email)
    except ValueError as exc:
        return f"Authentication error: {exc}. Use gdrive_generate_auth_url to authorize this account."
    except Exception as exc:
        return f"Error creating Google Drive service: {exc}"

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
        return f"Error searching for file '{file_name}': {exc}"

    files = results.get("files", [])
    if not files:
        return f"No file found with name '{file_name}'."

    lines: List[str] = []
    if len(files) > 1:
        lines.append(f"Found {len(files)} files with name '{file_name}':")
        for item in files:
            item_name = item.get("name", "(unknown)")
            item_id = item.get("id", "unknown")
            lines.append(f"  - {item_name} (ID: {item_id})")
        lines.extend(["", "Checking the first file...", ""])

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
        return f"Error retrieving permissions for file '{file_id}': {exc}"

    permissions = metadata.get("permissions", [])
    has_public = _check_public_link_permission(permissions)

    lines.extend(
        [
            f"File: {metadata.get('name', 'Unknown')}",
            f"ID: {metadata.get('id', 'unknown')}",
            f"Type: {metadata.get('mimeType', 'unknown')}",
            f"Shared: {metadata.get('shared', False)}",
            "",
        ]
    )

    if has_public:
        lines.extend(
            [
                "✅ PUBLIC ACCESS ENABLED - This file can be inserted into Google Docs.",
                f"Use with insert_doc_image_url: {_get_drive_image_url(file_id)}",
            ]
        )
    else:
        lines.extend(
            [
                "❌ NO PUBLIC ACCESS - Cannot insert into Google Docs.",
                "Fix: Drive → Share → 'Anyone with the link' → 'Viewer'.",
            ]
        )

    return "\n".join(lines)


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "run",
    "auth_status",
    "generate_auth_url",
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
    "check_drive_file_public_access",
]
