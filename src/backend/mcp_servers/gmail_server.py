"""Custom MCP server for Gmail integration."""

from __future__ import annotations

import asyncio
import base64
import mimetypes
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.mime.text import MIMEText
from email.utils import collapse_rfc2231_value
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Literal, Optional
from uuid import uuid4

# For local, in-process document extraction (no external URLs needed)
try:  # pragma: no cover - optional import used by attachment text tool
    from kreuzberg._mcp import server as kreuzberg_server  # type: ignore
except Exception:  # pragma: no cover - graceful degradation if not installed
    kreuzberg_server = None  # type: ignore

if TYPE_CHECKING:
    # Lightweight stub to keep type checkers happy without importing heavy generics
    class FastMCP:  # pragma: no cover - type checking only
        def __init__(self, *args: Any, **kwargs: Any) -> None: ...

        def tool(
            self, name: str
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...

        def run(self) -> None: ...
else:  # Runtime import
    from mcp.server.fastmcp import FastMCP

from backend.config import get_settings
from backend.repository import ChatRepository
from backend.utils import build_storage_name
from backend.services.google_auth.auth import (
    authorize_user,
    get_credentials,
    get_gmail_service,
)

mcp = FastMCP("custom-gmail")

DEFAULT_USER_EMAIL = "jck411@gmail.com"
GMAIL_BATCH_SIZE = 25
HTML_BODY_TRUNCATE_LIMIT = 20000

# Local repository singleton for persisting attachments
_repository: ChatRepository | None = None
_repository_lock = asyncio.Lock()


def _project_root() -> Path:
    module_path = Path(__file__).resolve()
    # src/backend/mcp_servers -> project root is three parents up
    return module_path.parents[3]


def _resolve_under(base: Path, p: Path) -> Path:
    if p.is_absolute():
        return p.resolve()
    resolved = (base / p).resolve()
    # keep behavior consistent with app factory safety
    if not resolved.is_relative_to(base):
        raise ValueError(f"Configured path {resolved} escapes project root {base}")
    return resolved


def _resolve_chat_db_path() -> Path:
    settings = get_settings()
    return _resolve_under(_project_root(), settings.chat_database_path)


async def _get_repository() -> ChatRepository:
    global _repository
    if _repository is not None:
        return _repository
    async with _repository_lock:
        if _repository is None:
            repo = ChatRepository(_resolve_chat_db_path())
            await repo.initialize()
            _repository = repo
    return _repository


def _resolve_redirect_uri(redirect_uri: Optional[str]) -> str:
    if redirect_uri:
        return redirect_uri

    try:
        settings = get_settings()
        return settings.google_oauth_redirect_uri
    except Exception:
        return "http://localhost:8000/api/google-auth/callback"


def _decode_base64(data: Optional[str]) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_message_bodies(payload: Dict) -> Dict[str, str]:
    text_body = ""
    html_body = ""
    parts: List[Dict] = [payload] if payload else []

    while parts:
        part = parts.pop(0)
        mime_type = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")

        if data:
            decoded = _decode_base64(data)
            if mime_type == "text/plain" and not text_body:
                text_body = decoded
            elif mime_type == "text/html" and not html_body:
                html_body = decoded
            elif not mime_type and not text_body:
                text_body = decoded

        sub_parts = part.get("parts", [])
        if sub_parts:
            parts.extend(sub_parts)

    return {"text": text_body, "html": html_body}


def _iter_payload_parts(payload: Dict) -> Iterable[Dict[str, Any]]:
    if not payload:
        return []
    # Breadth-first traversal to reach leaf parts
    queue: List[Dict[str, Any]] = []
    if payload.get("parts"):
        queue.extend(payload.get("parts", []))
    else:
        queue.append(payload)

    while queue:
        part = queue.pop(0)
        yield part
        sub_parts = part.get("parts") or []
        if sub_parts:
            queue.extend(sub_parts)


def _extract_attachments(payload: Dict) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []
    for part in _iter_payload_parts(payload):
        filename = (part.get("filename") or "").strip()
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")
        mime_type = part.get("mimeType") or "application/octet-stream"
        if filename and attachment_id:
            size = body.get("size") or 0
            # Disposition (inline/attachment) if present in headers
            disposition = None
            for header in part.get("headers", []) or []:
                if header.get("name") == "Content-Disposition":
                    disposition = header.get("value")
                    break
            attachments.append(
                {
                    "filename": filename,
                    "mimeType": mime_type,
                    "size": size,
                    "attachmentId": attachment_id,
                    "partId": part.get("partId"),
                    "disposition": disposition,
                }
            )
    return attachments


def _find_attachment_part(
    payload: Dict, target_attachment_id: str
) -> Optional[Dict[str, Any]]:
    for part in _iter_payload_parts(payload):
        body = part.get("body") or {}
        if body.get("attachmentId") == target_attachment_id:
            return part
    return None


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value.strip()


def _sanitize_filename(name: str) -> str:
    candidate = (name or "").strip().strip("\x00")
    if not candidate:
        return "attachment"
    candidate = candidate.replace("\\", "/")
    candidate = candidate.split("/")[-1]
    return candidate or "attachment"


def _extract_filename_from_headers(
    headers: Iterable[Dict[str, Any]] | None,
) -> str | None:
    if not headers:
        return None
    for header in headers:
        name = header.get("name")
        if name not in {"Content-Disposition", "Content-Type"}:
            continue
        value = header.get("value")
        if not value:
            continue
        message = Message()
        message[name] = value
        for param_name, param_value in message.get_params(header=name, failobj=[]):
            if not param_name:
                continue
            if param_name.lower() not in {"filename", "name"}:
                continue
            if isinstance(param_value, tuple):
                candidate = collapse_rfc2231_value(param_value)
            else:
                candidate = param_value
            candidate = _decode_header_value(candidate)
            if candidate and candidate.lower() != "attachment":
                return candidate
    return None


def _resolve_attachment_filename(part: Optional[Dict[str, Any]]) -> str:
    if not part:
        return "attachment"
    raw = _decode_header_value((part.get("filename") or "").strip())
    if raw and raw.lower() != "attachment":
        return _sanitize_filename(raw)
    header_name = _extract_filename_from_headers(part.get("headers"))
    if header_name:
        return _sanitize_filename(header_name)
    return _sanitize_filename(raw)


def _format_body_content(text_body: str, html_body: str) -> str:
    if text_body.strip():
        return text_body
    if html_body.strip():
        content = html_body
        if len(content) > HTML_BODY_TRUNCATE_LIMIT:
            content = (
                content[:HTML_BODY_TRUNCATE_LIMIT] + "\n\n[HTML content truncated...]"
            )
        return "[HTML content converted]\n" + content
    return "[No readable content found]"


def _extract_headers(payload: Dict, header_names: Iterable[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if not payload:
        return headers
    for header in payload.get("headers", []):
        name = header.get("name")
        value = header.get("value")
        if name in header_names and value is not None:
            headers[name] = value
    return headers


def _prepare_gmail_message(
    subject: str,
    body: str,
    to: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    body_format: Literal["plain", "html"] = "plain",
) -> tuple[str, Optional[str]]:
    normalized_format = body_format.lower()
    if normalized_format not in {"plain", "html"}:
        raise ValueError("body_format must be either 'plain' or 'html'.")

    reply_subject = subject
    if in_reply_to and not subject.lower().startswith("re:"):
        reply_subject = f"Re: {subject}"

    message = MIMEText(body, normalized_format)
    message["subject"] = reply_subject

    if to:
        message["to"] = to
    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return raw_message, thread_id


def _generate_gmail_web_url(item_id: str, account_index: int = 0) -> str:
    return f"https://mail.google.com/mail/u/{account_index}/#all/{item_id}"


def _resolve_attachments_dir() -> Path:
    settings = get_settings()
    return _resolve_under(_project_root(), settings.attachments_dir)


def _build_attachment_urls(attachment_id: str) -> tuple[str, str]:
    """Return (display_url, delivery_url) for stored attachments.

    - delivery_url always uses localhost to avoid reliance on public tunnels.
    - display_url uses configured public base if present, otherwise localhost.
    """
    settings = get_settings()
    api_path = f"/api/uploads/{attachment_id}/content"
    local_base = "http://localhost:8000"
    public_base = (
        str(settings.attachments_public_base_url)
        if settings.attachments_public_base_url
        else None
    )
    display = f"{(public_base or local_base).rstrip('/')}{api_path}"
    delivery = f"{local_base.rstrip('/')}{api_path}"
    return display, delivery


def _format_thread_content(thread_data: Dict, thread_id: str) -> str:
    messages = thread_data.get("messages", []) if thread_data else []
    if not messages:
        return f"No messages found in thread '{thread_id}'."

    first_headers = _extract_headers(messages[0].get("payload", {}), ["Subject"])
    thread_subject = first_headers.get("Subject", "(no subject)")

    lines = [
        f"Thread ID: {thread_id}",
        f"Subject: {thread_subject}",
        f"Messages: {len(messages)}",
        "",
    ]

    for idx, message in enumerate(messages, start=1):
        headers = _extract_headers(
            message.get("payload", {}),
            ["From", "Date", "Subject"],
        )
        sender = headers.get("From", "(unknown sender)")
        date = headers.get("Date", "(unknown date)")
        subject = headers.get("Subject", thread_subject)

        bodies = _extract_message_bodies(message.get("payload", {}))
        body_text = _format_body_content(bodies.get("text", ""), bodies.get("html", ""))

        lines.append(f"=== Message {idx} ===")
        lines.append(f"From: {sender}")
        lines.append(f"Date: {date}")
        if subject != thread_subject:
            lines.append(f"Subject: {subject}")
        lines.append("")
        lines.append(body_text)
        lines.append("")

    return "\n".join(lines)


@mcp.tool("gmail_auth_status")
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
            f"{user_email} is already authorized for Gmail. "
            f"Existing token expires at {expiry_text}. "
            "Use gmail_generate_auth_url with force=true to start a fresh consent flow."
        )

    return (
        f"No stored Gmail credentials found for {user_email}. "
        "Run gmail_generate_auth_url to generate an authorization link."
    )


@mcp.tool("gmail_generate_auth_url")
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
        "Follow these steps to finish Gmail authorization:\n"
        f"1. Visit: {auth_url}\n"
        "2. Approve access to your Gmail account.\n"
        f"3. You will be redirected to {effective_redirect}; the backend will store the token automatically.\n"
        "After completing the flow, run gmail_auth_status to confirm success.\n"
        "Note: Google may warn that the app is unverified. Choose Advanced → Continue to proceed for testing accounts added on the OAuth consent screen."
    )


@mcp.tool("search_gmail_messages")
async def search_gmail_messages(
    query: str,
    user_email: str = DEFAULT_USER_EMAIL,
    page_size: int = 10,
) -> str:
    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        response = await asyncio.to_thread(
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max(page_size, 1))
            .execute
        )
    except Exception as exc:
        return f"Error searching Gmail messages: {exc}"

    messages = response.get("messages", []) or []
    next_token = response.get("nextPageToken")

    if not messages:
        return f"No messages found for query '{query}'."

    lines = [
        f"Found {len(messages)} messages matching '{query}':",
        "",
    ]

    for idx, message in enumerate(messages, start=1):
        message_id = message.get("id", "unknown")
        thread_id = message.get("threadId", "unknown")
        snippet = message.get("snippet", "(no snippet)")
        message_url = (
            _generate_gmail_web_url(message_id) if message_id != "unknown" else "N/A"
        )
        thread_url = (
            _generate_gmail_web_url(thread_id) if thread_id != "unknown" else "N/A"
        )

        lines.extend(
            [
                f"{idx}. Message ID: {message_id}",
                f"   Thread ID: {thread_id}",
                f"   Message URL: {message_url}",
                f"   Thread URL:  {thread_url}",
                f"   Snippet: {snippet}",
                "",
            ]
        )

    if next_token:
        lines.append(f"Next page token: {next_token}")

    return "\n".join(lines)


@mcp.tool("get_gmail_message_content")
async def get_gmail_message_content(
    message_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        metadata = await asyncio.to_thread(
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["Subject", "From"],
            )
            .execute
        )
        full_message = await asyncio.to_thread(
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )
    except Exception as exc:
        return f"Error retrieving Gmail message {message_id}: {exc}"

    headers = _extract_headers(metadata.get("payload", {}), ["Subject", "From"])
    subject = headers.get("Subject", "(no subject)")
    sender = headers.get("From", "(unknown sender)")

    bodies = _extract_message_bodies(full_message.get("payload", {}))
    body_text = _format_body_content(bodies.get("text", ""), bodies.get("html", ""))

    return "\n".join(
        [
            f"Subject: {subject}",
            f"From: {sender}",
            "",
            "--- BODY ---",
            body_text,
        ]
    )


@mcp.tool("list_gmail_message_attachments")
async def list_gmail_message_attachments(
    message_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """List attachments for a Gmail message including filename, mimeType, size, and IDs."""
    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        message = await asyncio.to_thread(
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )
    except Exception as exc:
        return f"Error retrieving Gmail message {message_id}: {exc}"

    payload = message.get("payload", {})
    attachments = _extract_attachments(payload)
    if not attachments:
        return f"No attachments found for message '{message_id}'."

    lines = [f"Found {len(attachments)} attachments in message {message_id}:", ""]
    for idx, att in enumerate(attachments, start=1):
        lines.extend(
            [
                f"{idx}. Filename: {att.get('filename')}",
                f"   MIME: {att.get('mimeType')}",
                f"   Size: {att.get('size')} bytes",
                f"   Attachment ID: {att.get('attachmentId')}",
                f"   Part ID: {att.get('partId')}",
                (
                    f"   Disposition: {att.get('disposition')}"
                    if att.get("disposition")
                    else ""
                ),
                "",
            ]
        )
    return "\n".join(line for line in lines if line != "")


@mcp.tool("download_gmail_attachment")
async def download_gmail_attachment(
    message_id: str,
    attachment_id: str,
    session_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Download a Gmail attachment and persist it in local storage.

    Returns a summary including the internal attachment ID and a local URL.
    Public URLs (e.g., ngrok) are no longer required for delivery and will only
    be shown as a convenience if configured.
    """
    if not session_id or not session_id.strip():
        return "session_id is required to register the attachment."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    # Fetch message to locate metadata for the attachment (filename/mime)
    try:
        message = await asyncio.to_thread(
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute
        )
    except Exception as exc:
        return f"Error retrieving Gmail message {message_id}: {exc}"

    payload = message.get("payload", {})
    attachment_entry = None
    for candidate in _extract_attachments(payload):
        if candidate.get("attachmentId") == attachment_id:
            attachment_entry = candidate
            break

    part = _find_attachment_part(payload, attachment_id)
    # If we can't locate metadata, fall back to sensible defaults while still
    # attempting the download to avoid blocking on Gmail quirks.
    filename = "attachment"
    if attachment_entry:
        candidate = _sanitize_filename(
            _decode_header_value(attachment_entry.get("filename") or "")
        )
        if candidate and candidate.lower() != "attachment":
            filename = candidate
    if (not filename or filename == "attachment") and part:
        filename = _resolve_attachment_filename(part)

    mime_type = None
    if attachment_entry and attachment_entry.get("mimeType"):
        mime_type = attachment_entry.get("mimeType")
    if not mime_type and part:
        mime_type = part.get("mimeType")
    if not mime_type:
        mime_type = "application/octet-stream"

    # Download the raw attachment bytes
    try:
        att_obj = await asyncio.to_thread(
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute
        )
    except Exception as exc:
        # If we couldn't even fetch the attachment object and we also
        # didn't find a matching part, report the original guidance to list.
        if not part:
            return (
                f"Attachment '{attachment_id}' was not found in message '{message_id}'. "
                "Use list_gmail_message_attachments to enumerate available attachments."
            )
        return f"Error downloading Gmail attachment {attachment_id}: {exc}"

    data_b64 = att_obj.get("data")
    if not data_b64:
        return "Downloaded attachment did not contain data."

    try:
        content_bytes = base64.urlsafe_b64decode(data_b64)
    except Exception:
        return "Failed to decode attachment content."

    size_bytes = len(content_bytes)
    settings = get_settings()
    max_size = int(settings.attachments_max_size_bytes)
    if size_bytes > max_size:
        return (
            f"Attachment is {size_bytes} bytes which exceeds limit of {max_size} bytes."
        )

    # Determine file extension
    ext = Path(filename).suffix
    if not ext:
        guessed = mimetypes.guess_extension(mime_type)
        ext = guessed or ""

    internal_id = uuid4().hex
    stored_name = build_storage_name(internal_id, ext, filename)
    relative_path = Path(session_id) / stored_name
    storage_base = _resolve_attachments_dir()
    absolute_path = (storage_base / relative_path).resolve()

    # Safety: ensure we don't escape storage dir
    storage_resolved = storage_base.resolve()
    if (
        storage_resolved not in absolute_path.parents
        and absolute_path != storage_resolved
    ):
        return "Resolved attachment path escaped storage directory"

    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    # Write file to disk off the main thread
    try:
        await asyncio.to_thread(absolute_path.write_bytes, content_bytes)
    except Exception as exc:
        return f"Failed to write attachment to storage: {exc}"

    # Persist metadata in repository
    try:
        repository = await _get_repository()
        await repository.ensure_session(session_id)
        now = datetime.now(timezone.utc)
        retention_days = int(settings.attachments_retention_days)
        expires_at = (
            now + timedelta(days=retention_days) if retention_days > 0 else None
        )
        display_url, delivery_url = _build_attachment_urls(internal_id)
        part_id = None
        if part and part.get("partId"):
            part_id = part.get("partId")
        elif attachment_entry and attachment_entry.get("partId"):
            part_id = attachment_entry.get("partId")

        metadata: Dict[str, Any] = {
            "filename": filename,
            "gmail": {
                "message_id": message_id,
                "attachment_id": attachment_id,
                "part_id": part_id,
            },
        }
        record = await repository.add_attachment(
            attachment_id=internal_id,
            session_id=session_id,
            storage_path=str(relative_path),
            mime_type=mime_type,
            size_bytes=size_bytes,
            display_url=display_url,
            delivery_url=delivery_url,
            metadata=metadata,
            expires_at=expires_at,
        )
    except Exception as exc:
        # best-effort cleanup
        try:
            absolute_path.unlink(missing_ok=True)
        except Exception:
            pass
        return f"Failed to register attachment: {exc}"

    uploaded_at = record.get("created_at")
    expires_at_iso = record.get("expires_at")
    lines = [
        "Attachment saved!",
        f"Attachment ID: {internal_id}",
        f"Filename: {filename}",
        f"MIME: {mime_type}",
        f"Size: {size_bytes} bytes",
        f"Local URL: {delivery_url}",
        f"Uploaded At: {uploaded_at}",
        f"Expires At: {expires_at_iso or 'none'}",
    ]
    if display_url != delivery_url:
        lines.insert(6, f"Public URL: {display_url}")
    return "\n".join(lines)


async def _download_and_register_attachment(
    service: Any,
    message_id: str,
    attachment_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Internal helper to download and register an attachment; returns record info.

    Returns a dict with keys: internal_id, filename, mime_type, size_bytes,
    display_url, delivery_url, record.
    """
    # Fetch message to locate metadata
    message = await asyncio.to_thread(
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute
    )
    payload = message.get("payload", {})
    attachment_entry = None
    for candidate in _extract_attachments(payload):
        if candidate.get("attachmentId") == attachment_id:
            attachment_entry = candidate
            break

    part = _find_attachment_part(payload, attachment_id)

    filename = "attachment"
    if attachment_entry:
        candidate = _sanitize_filename(
            _decode_header_value(attachment_entry.get("filename") or "")
        )
        if candidate and candidate.lower() != "attachment":
            filename = candidate
    if (not filename or filename == "attachment") and part:
        filename = _resolve_attachment_filename(part)

    mime_type = None
    if attachment_entry and attachment_entry.get("mimeType"):
        mime_type = attachment_entry.get("mimeType")
    if not mime_type and part:
        mime_type = part.get("mimeType")
    if not mime_type:
        mime_type = "application/octet-stream"

    # Download bytes
    att_obj = await asyncio.to_thread(
        service.users()
        .messages()
        .attachments()
        .get(userId="me", messageId=message_id, id=attachment_id)
        .execute
    )
    data_b64 = att_obj.get("data")
    if not data_b64:
        raise RuntimeError("Downloaded attachment did not contain data")
    content_bytes = base64.urlsafe_b64decode(data_b64)
    size_bytes = len(content_bytes)

    settings = get_settings()
    max_size = int(settings.attachments_max_size_bytes)
    if size_bytes > max_size:
        raise RuntimeError(
            f"Attachment is {size_bytes} bytes which exceeds limit of {max_size} bytes."
        )

    # Determine file extension
    ext = Path(filename).suffix
    if not ext:
        # Handle common mime types explicitly for more consistent extensions
        if mime_type.lower() == "application/pdf":
            ext = ".pdf"
        else:
            guessed = mimetypes.guess_extension(mime_type)
            ext = guessed or ""

    internal_id = uuid4().hex
    stored_name = build_storage_name(internal_id, ext, filename)
    relative_path = Path(session_id) / stored_name
    storage_base = _resolve_attachments_dir()
    absolute_path = (storage_base / relative_path).resolve()

    storage_resolved = storage_base.resolve()
    if (
        storage_resolved not in absolute_path.parents
        and absolute_path != storage_resolved
    ):
        raise RuntimeError("Resolved attachment path escaped storage directory")

    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(absolute_path.write_bytes, content_bytes)

    # Persist metadata
    repository = await _get_repository()
    await repository.ensure_session(session_id)
    now = datetime.now(timezone.utc)
    retention_days = int(settings.attachments_retention_days)
    expires_at = now + timedelta(days=retention_days) if retention_days > 0 else None
    display_url, delivery_url = _build_attachment_urls(internal_id)
    metadata: Dict[str, Any] = {
        "filename": filename,
        "gmail": {
            "message_id": message_id,
            "attachment_id": attachment_id,
            "part_id": part.get("partId") if part else None,
        },
    }
    record = await repository.add_attachment(
        attachment_id=internal_id,
        session_id=session_id,
        storage_path=str(relative_path),
        mime_type=mime_type,
        size_bytes=size_bytes,
        display_url=display_url,
        delivery_url=delivery_url,
        metadata=metadata,
        expires_at=expires_at,
    )

    return {
        "internal_id": internal_id,
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "display_url": display_url,
        "delivery_url": delivery_url,
        "record": record,
        "absolute_path": str(absolute_path),
        "relative_path": str(relative_path),
    }


@mcp.tool("read_gmail_attachment_text")
async def read_gmail_attachment_text(
    message_id: str,
    session_id: str,
    attachment_id: Optional[str] = None,
    filename_contains: Optional[str] = None,
    prefer_mime: Optional[str] = "application/pdf",
    force_ocr: bool = False,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Download a Gmail attachment and return extracted text locally (no ngrok).

    Selection priority when attachment_id is not provided:
    1) First attachment whose filename contains `filename_contains` (case-insensitive)
    2) First attachment whose MIME matches `prefer_mime` (if provided)
    3) First attachment in the message
    """
    if not session_id or not session_id.strip():
        return "session_id is required to register the attachment."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    # If no attachment_id provided, pick one from the message
    selected_attachment_id = attachment_id
    selected_filename = None
    selected_mime = None

    if not selected_attachment_id:
        try:
            message = await asyncio.to_thread(
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute
            )
        except Exception as exc:
            return f"Error retrieving Gmail message {message_id}: {exc}"

        attachments = _extract_attachments(message.get("payload", {}))
        if not attachments:
            return f"No attachments found for message '{message_id}'."

        def _match(att: Dict[str, Any]) -> int:
            score = 0
            name = (att.get("filename") or "").lower()
            mime = (att.get("mimeType") or "").lower()
            if filename_contains and filename_contains.lower() in name:
                score += 2
            if prefer_mime and prefer_mime.lower() == mime:
                score += 1
            return score

        attachments_sorted = sorted(attachments, key=_match, reverse=True)
        top = attachments_sorted[0]
        selected_attachment_id = str(top.get("attachmentId"))
        selected_filename = top.get("filename")
        selected_mime = top.get("mimeType")

    # Download and register
    try:
        info = await _download_and_register_attachment(
            service, message_id, str(selected_attachment_id), session_id
        )
    except Exception as exc:
        return f"Failed to download/register attachment: {exc}"

    internal_id = info["internal_id"]
    filename = selected_filename or info["filename"]
    mime_type = (
        selected_mime or info["mime_type"] or "application/octet-stream"
    ).lower()

    # Read bytes and extract via kreuzberg, no URLs involved
    try:
        repository = await _get_repository()
        record = await repository.get_attachment(internal_id)
        if not record:
            return f"Attachment not found after save: {internal_id}"
        storage_path = record.get("storage_path")
        if not storage_path:
            return "Attachment record missing storage path"
        base = _resolve_attachments_dir()
        abs_path = (base / storage_path).resolve()
        content_bytes = await asyncio.to_thread(abs_path.read_bytes)
    except Exception as exc:
        return f"Failed to read stored attachment: {exc}"

    if kreuzberg_server is None:
        return (
            "Extraction unavailable: kreuzberg document tools are not installed. "
            "You can still access the file locally."
        )

    import base64 as _b64  # local alias to avoid confusion

    try:
        payload_b64 = _b64.b64encode(content_bytes).decode("ascii")
        result: Dict[str, Any] = await asyncio.to_thread(
            kreuzberg_server.extract_bytes,
            payload_b64,
            mime_type,
            force_ocr,
            False,  # chunk_content
            False,  # extract_tables
            False,  # extract_entities
            False,  # extract_keywords
            "tesseract",  # ocr_backend
            1000,  # max_chars
            200,  # max_overlap
            10,  # keyword_count
            False,  # auto_detect_language
            None,  # tesseract_lang
            None,  # tesseract_psm
            None,  # tesseract_output_format
            None,  # enable_table_detection
        )
    except Exception as exc:
        return f"Extraction failed: {exc}"

    text = str(result.get("content") or result.get("text") or "").strip()
    if text:
        header = (
            f"Attachment text extracted!\n"
            f"Attachment ID: {internal_id}\n"
            f"Filename: {filename}\n"
            f"MIME: {mime_type}\n\n"
        )
        return header + text

    # Optional OCR retry for PDFs if not already forced
    if not force_ocr and mime_type == "application/pdf":
        try:
            ocr_result: Dict[str, Any] = await asyncio.to_thread(
                kreuzberg_server.extract_bytes,
                payload_b64,
                mime_type,
                True,  # force_ocr
                False,
                False,
                False,
                "tesseract",
                1000,
                200,
                10,
                False,
                None,
                None,
                None,
                None,
            )
            ocr_text = str(
                ocr_result.get("content") or ocr_result.get("text") or ""
            ).strip()
            if ocr_text:
                header = (
                    f"Attachment text extracted (OCR)!\n"
                    f"Attachment ID: {internal_id}\n"
                    f"Filename: {filename}\n"
                    f"MIME: {mime_type}\n\n"
                )
                return header + ocr_text
        except Exception:
            pass

    # Final fallback
    try:
        return content_bytes.decode("utf-8")
    except Exception:
        return f"[Binary content; {len(content_bytes)} bytes; mime={mime_type}]"


@mcp.tool("extract_gmail_attachment_by_id")
async def extract_gmail_attachment_by_id(
    message_id: str,
    attachment_id: str,
    session_id: str,
    force_ocr: bool = False,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Convenience wrapper: download + extract a Gmail attachment by ID.

    This is equivalent to calling ``read_gmail_attachment_text`` with
    ``attachment_id`` specified, keeping parameters minimal for common flows.
    """
    return await read_gmail_attachment_text(
        message_id=message_id,
        session_id=session_id,
        attachment_id=attachment_id,
        force_ocr=force_ocr,
        user_email=user_email,
    )

@mcp.tool("get_gmail_messages_content_batch")
async def get_gmail_messages_content_batch(
    message_ids: List[str],
    user_email: str = DEFAULT_USER_EMAIL,
    format: Literal["full", "metadata"] = "full",
) -> str:
    if not message_ids:
        return "No message IDs provided."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    output: List[str] = []
    for chunk_start in range(0, len(message_ids), GMAIL_BATCH_SIZE):
        chunk = message_ids[chunk_start : chunk_start + GMAIL_BATCH_SIZE]
        for message_id in chunk:
            try:
                message = await asyncio.to_thread(
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format=format,
                        metadataHeaders=["Subject", "From"]
                        if format == "metadata"
                        else None,
                    )
                    .execute
                )
            except Exception as exc:
                output.append(f"⚠️ Message {message_id}: {exc}")
                continue

            payload = message.get("payload", {})
            headers = _extract_headers(payload, ["Subject", "From"])
            subject = headers.get("Subject", "(no subject)")
            sender = headers.get("From", "(unknown sender)")
            message_url = _generate_gmail_web_url(message_id)

            if format == "metadata":
                output.extend(
                    [
                        f"Message ID: {message_id}",
                        f"Subject: {subject}",
                        f"From: {sender}",
                        f"Web Link: {message_url}",
                        "",
                    ]
                )
            else:
                bodies = _extract_message_bodies(payload)
                body_text = _format_body_content(
                    bodies.get("text", ""), bodies.get("html", "")
                )

                output.extend(
                    [
                        f"Message ID: {message_id}",
                        f"Subject: {subject}",
                        f"From: {sender}",
                        f"Web Link: {message_url}",
                        "",
                        body_text,
                        "",
                        "---",
                        "",
                    ]
                )

    return f"Retrieved {len(message_ids)} messages:\n\n" + "\n".join(output).rstrip(
        "-\n "
    )


@mcp.tool("send_gmail_message")
async def send_gmail_message(
    user_email: str = DEFAULT_USER_EMAIL,
    to: str = "",
    subject: str = "",
    body: str = "",
    body_format: Literal["plain", "html"] = "plain",
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> str:
    if not to:
        return "Recipient email address (to) is required."
    if not subject:
        return "Subject is required."
    if not body:
        return "Body content is required."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        raw_message, final_thread_id = _prepare_gmail_message(
            subject=subject,
            body=body,
            to=to,
            cc=cc,
            bcc=bcc,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            body_format=body_format,
        )
    except ValueError as exc:
        return str(exc)

    payload: Dict[str, str] = {"raw": raw_message}
    if final_thread_id:
        payload["threadId"] = final_thread_id

    try:
        response = await asyncio.to_thread(
            service.users().messages().send(userId="me", body=payload).execute
        )
    except Exception as exc:
        return f"Error sending Gmail message: {exc}"

    message_id = response.get("id", "(unknown)")
    return f"Email sent! Message ID: {message_id}"


@mcp.tool("draft_gmail_message")
async def draft_gmail_message(
    user_email: str = DEFAULT_USER_EMAIL,
    subject: str = "",
    body: str = "",
    to: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    body_format: Literal["plain", "html"] = "plain",
) -> str:
    if not subject:
        return "Subject is required to create a draft."
    if not body:
        return "Body content is required to create a draft."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        raw_message, final_thread_id = _prepare_gmail_message(
            subject=subject,
            body=body,
            to=to,
            cc=cc,
            bcc=bcc,
            thread_id=thread_id,
            in_reply_to=in_reply_to,
            references=references,
            body_format=body_format,
        )
    except ValueError as exc:
        return str(exc)

    draft_body: Dict[str, Dict[str, str]] = {"message": {"raw": raw_message}}
    if final_thread_id:
        draft_body["message"]["threadId"] = final_thread_id

    try:
        response = await asyncio.to_thread(
            service.users().drafts().create(userId="me", body=draft_body).execute
        )
    except Exception as exc:
        return f"Error creating Gmail draft: {exc}"

    draft_id = response.get("id", "(unknown)")
    return f"Draft created! Draft ID: {draft_id}"


@mcp.tool("get_gmail_thread_content")
async def get_gmail_thread_content(
    thread_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        thread = await asyncio.to_thread(
            service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute
        )
    except Exception as exc:
        return f"Error retrieving Gmail thread {thread_id}: {exc}"

    return _format_thread_content(thread, thread_id)


@mcp.tool("get_gmail_threads_content_batch")
async def get_gmail_threads_content_batch(
    thread_ids: List[str],
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    if not thread_ids:
        return "No thread IDs provided."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    output: List[str] = []
    for chunk_start in range(0, len(thread_ids), GMAIL_BATCH_SIZE):
        chunk = thread_ids[chunk_start : chunk_start + GMAIL_BATCH_SIZE]
        for thread_id in chunk:
            try:
                thread = await asyncio.to_thread(
                    service.users()
                    .threads()
                    .get(userId="me", id=thread_id, format="full")
                    .execute
                )
            except Exception as exc:
                output.append(f"⚠️ Thread {thread_id}: {exc}")
                continue

            output.append(_format_thread_content(thread, thread_id))
            output.append("---")

    return f"Retrieved {len(thread_ids)} threads:\n\n" + "\n".join(output).rstrip(
        "-\n "
    )


@mcp.tool("list_gmail_labels")
async def list_gmail_labels(user_email: str = DEFAULT_USER_EMAIL) -> str:
    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        response = await asyncio.to_thread(
            service.users().labels().list(userId="me").execute
        )
    except Exception as exc:
        return f"Error listing Gmail labels: {exc}"

    labels = response.get("labels", []) or []
    if not labels:
        return "No labels found."

    system_labels: List[Dict] = []
    user_labels: List[Dict] = []

    for label in labels:
        if label.get("type") == "system":
            system_labels.append(label)
        else:
            user_labels.append(label)

    lines = [f"Found {len(labels)} labels:", ""]
    if system_labels:
        lines.append("System labels:")
        for label in system_labels:
            lines.append(f"- {label.get('name')} (ID: {label.get('id')})")
        lines.append("")

    if user_labels:
        lines.append("User labels:")
        for label in user_labels:
            lines.append(f"- {label.get('name')} (ID: {label.get('id')})")

    return "\n".join(lines).strip()


@mcp.tool("manage_gmail_label")
async def manage_gmail_label(
    action: Literal["create", "update", "delete"],
    user_email: str = DEFAULT_USER_EMAIL,
    name: Optional[str] = None,
    label_id: Optional[str] = None,
    label_list_visibility: Literal["labelShow", "labelHide"] = "labelShow",
    message_list_visibility: Literal["show", "hide"] = "show",
) -> str:
    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        if action == "create":
            if not name:
                return "Label name is required for create action."

            label_object = {
                "name": name,
                "labelListVisibility": label_list_visibility,
                "messageListVisibility": message_list_visibility,
            }
            response = await asyncio.to_thread(
                service.users().labels().create(userId="me", body=label_object).execute
            )
            return (
                "Label created successfully!\n"
                f"Name: {response.get('name')}\n"
                f"ID: {response.get('id')}"
            )

        if action in {"update", "delete"} and not label_id:
            return "Label ID is required for update and delete actions."

        if action == "update":
            current = await asyncio.to_thread(
                service.users().labels().get(userId="me", id=label_id).execute
            )
            label_object = {
                "id": label_id,
                "name": name if name is not None else current.get("name"),
                "labelListVisibility": label_list_visibility,
                "messageListVisibility": message_list_visibility,
            }
            updated = await asyncio.to_thread(
                service.users()
                .labels()
                .update(userId="me", id=label_id, body=label_object)
                .execute
            )
            return (
                "Label updated successfully!\n"
                f"Name: {updated.get('name')}\n"
                f"ID: {updated.get('id')}"
            )

        if action == "delete":
            label = await asyncio.to_thread(
                service.users().labels().get(userId="me", id=label_id).execute
            )
            label_name = label.get("name", label_id)
            await asyncio.to_thread(
                service.users().labels().delete(userId="me", id=label_id).execute
            )
            return f"Label '{label_name}' (ID: {label_id}) deleted successfully!"

        return f"Unsupported action: {action}"
    except Exception as exc:
        return f"Error managing Gmail label: {exc}"


@mcp.tool("modify_gmail_message_labels")
async def modify_gmail_message_labels(
    message_id: str,
    add_label_ids: Optional[List[str]] = None,
    remove_label_ids: Optional[List[str]] = None,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    add_label_ids = add_label_ids or []
    remove_label_ids = remove_label_ids or []
    if not add_label_ids and not remove_label_ids:
        return "At least one of add_label_ids or remove_label_ids must be provided."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    body = {}
    if add_label_ids:
        body["addLabelIds"] = add_label_ids
    if remove_label_ids:
        body["removeLabelIds"] = remove_label_ids

    try:
        await asyncio.to_thread(
            service.users()
            .messages()
            .modify(userId="me", id=message_id, body=body)
            .execute
        )
    except Exception as exc:
        return f"Error modifying labels for message {message_id}: {exc}"

    actions = []
    if add_label_ids:
        actions.append(f"Added labels: {', '.join(add_label_ids)}")
    if remove_label_ids:
        actions.append(f"Removed labels: {', '.join(remove_label_ids)}")

    return (
        "Message labels updated successfully!\n"
        f"Message ID: {message_id}\n"
        f"{'; '.join(actions)}"
    )


@mcp.tool("batch_modify_gmail_message_labels")
async def batch_modify_gmail_message_labels(
    message_ids: List[str],
    add_label_ids: Optional[List[str]] = None,
    remove_label_ids: Optional[List[str]] = None,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    if not message_ids:
        return "Message IDs are required for batch modification."

    add_label_ids = add_label_ids or []
    remove_label_ids = remove_label_ids or []
    if not add_label_ids and not remove_label_ids:
        return "At least one of add_label_ids or remove_label_ids must be provided."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Use gmail_generate_auth_url to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    body: Dict[str, List[str]] = {"ids": message_ids}
    if add_label_ids:
        body["addLabelIds"] = add_label_ids
    if remove_label_ids:
        body["removeLabelIds"] = remove_label_ids

    try:
        await asyncio.to_thread(
            service.users().messages().batchModify(userId="me", body=body).execute
        )
    except Exception as exc:
        return f"Error modifying labels for messages {message_ids}: {exc}"

    actions = []
    if add_label_ids:
        actions.append(f"Added labels: {', '.join(add_label_ids)}")
    if remove_label_ids:
        actions.append(f"Removed labels: {', '.join(remove_label_ids)}")

    return f"Labels updated for {len(message_ids)} messages: {'; '.join(actions)}"


def run() -> None:  # pragma: no cover - integration entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI helper
    run()


__all__ = [
    "mcp",
    "run",
    "auth_status",
    "generate_auth_url",
    "search_gmail_messages",
    "get_gmail_message_content",
    "get_gmail_messages_content_batch",
    "list_gmail_message_attachments",
    "download_gmail_attachment",
    "send_gmail_message",
    "draft_gmail_message",
    "get_gmail_thread_content",
    "get_gmail_threads_content_batch",
    "list_gmail_labels",
    "manage_gmail_label",
    "modify_gmail_message_labels",
    "batch_modify_gmail_message_labels",
]
