"""Custom MCP server for Gmail integration."""

from __future__ import annotations

import asyncio
import base64
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

# For local, in-process document extraction (no external URLs needed)
try:  # pragma: no cover - optional import used by attachment text tool
    from kreuzberg._mcp import server as kreuzberg_server  # type: ignore
except Exception:  # pragma: no cover - graceful degradation if not installed
    kreuzberg_server = None  # type: ignore

from fastmcp import FastMCP

from backend.config import get_settings
from backend.repository import ChatRepository
from backend.services.attachments import (
    AttachmentError,
    AttachmentService,
    AttachmentTooLarge,
)
from backend.services.gmail_download_simple import (
    extract_filename_from_part,
    fetch_gmail_attachment_data,
    find_attachment_part,
)
from backend.services.google_auth.auth import (
    DEFAULT_USER_EMAIL,
    get_gmail_service,
)

# Default port for HTTP transport
DEFAULT_HTTP_PORT = 9005

mcp = FastMCP("custom-gmail")
GMAIL_BATCH_SIZE = 25
HTML_BODY_TRUNCATE_LIMIT = 20000


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


_repository: ChatRepository | None = None
_repository_lock = asyncio.Lock()
_attachment_service: AttachmentService | None = None
_attachment_service_lock = asyncio.Lock()


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


async def _get_attachment_service() -> AttachmentService:
    global _attachment_service
    if _attachment_service is not None:
        return _attachment_service
    async with _attachment_service_lock:
        if _attachment_service is None:
            settings = get_settings()
            repository = await _get_repository()
            _attachment_service = AttachmentService(
                repository,
                max_size_bytes=settings.attachments_max_size_bytes,
                retention_days=settings.attachments_retention_days,
            )
    return _attachment_service


def _extract_message_bodies(payload: dict) -> dict:
    """Extract plain text and HTML body from a Gmail message payload.

    Args:
        payload: The message payload from Gmail API

    Returns:
        Dictionary with 'text' and 'html' keys containing body content
    """
    text_body = ""
    html_body = ""
    parts = [payload] if "parts" not in payload else payload.get("parts", [])
    part_queue = list(parts)  # Use a queue for BFS traversal of parts

    while part_queue:
        part = part_queue.pop(0)
        mime_type = part.get("mimeType", "")
        body_data = part.get("body", {}).get("data")

        if body_data:
            try:
                decoded_data = base64.urlsafe_b64decode(body_data).decode(
                    "utf-8", errors="ignore"
                )
                if mime_type == "text/plain" and not text_body:
                    text_body = decoded_data
                elif mime_type == "text/html" and not html_body:
                    html_body = decoded_data
            except Exception:
                pass

        # Add sub-parts to queue for multipart messages
        if mime_type.startswith("multipart/") and "parts" in part:
            part_queue.extend(part.get("parts", []))

    # Check the main payload if it has body data directly
    if payload.get("body", {}).get("data"):
        try:
            decoded_data = base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="ignore"
            )
            mime_type = payload.get("mimeType", "")
            if mime_type == "text/plain" and not text_body:
                text_body = decoded_data
            elif mime_type == "text/html" and not html_body:
                html_body = decoded_data
        except Exception:
            pass

    return {"text": text_body, "html": html_body}


def _format_body_content(text_body: str, html_body: str) -> str:
    """Format message body content with HTML fallback and truncation.

    Args:
        text_body: Plain text body content
        html_body: HTML body content

    Returns:
        Formatted body content string
    """
    if text_body.strip():
        return text_body
    elif html_body.strip():
        # Truncate very large HTML to keep responses manageable
        if len(html_body) > HTML_BODY_TRUNCATE_LIMIT:
            html_body = (
                html_body[:HTML_BODY_TRUNCATE_LIMIT] + "\n\n[HTML content truncated...]"
            )
        return f"[HTML Content Converted]\n{html_body}"
    else:
        return "[No readable content found]"


def _extract_attachments(payload: dict) -> List[Dict[str, Any]]:
    """Extract attachment metadata from a Gmail message payload.

    Args:
        payload: The message payload from Gmail API

    Returns:
        List of attachment dictionaries with filename, mimeType, size,
        attachmentId, partId, and disposition
    """
    attachments = []

    def search_parts(part: dict) -> None:
        """Recursively search for attachments in message parts"""
        # Check if this part is an attachment
        body = part.get("body", {})
        if part.get("filename") and body.get("attachmentId"):
            att_dict: Dict[str, Any] = {
                "filename": part["filename"],
                "mimeType": part.get("mimeType", "application/octet-stream"),
                "size": body.get("size", 0),
                "attachmentId": body["attachmentId"],
                "partId": part.get("partId", ""),
            }
            # Add disposition if present
            headers = {h.get("name"): h.get("value") for h in part.get("headers", [])}
            if "Content-Disposition" in headers:
                att_dict["disposition"] = headers["Content-Disposition"]
            attachments.append(att_dict)

        # Recursively search sub-parts
        if "parts" in part:
            for subpart in part["parts"]:
                search_parts(subpart)

    # Start searching from the root payload
    search_parts(payload)
    return attachments


def _extract_headers(payload: dict, header_names: List[str]) -> Dict[str, str]:
    """Extract specified headers from a Gmail message payload.

    Args:
        payload: The message payload from Gmail API
        header_names: List of header names to extract

    Returns:
        Dictionary mapping header names to their values
    """
    headers = {}
    for header in payload.get("headers", []):
        name = header.get("name", "")
        if name in header_names:
            headers[name] = header.get("value", "")
    return headers


def _generate_gmail_web_url(item_id: str, account_index: int = 0) -> str:
    """Generate a Gmail web interface URL for a message or thread.

    Args:
        item_id: Message ID or thread ID
        account_index: Account index for multi-account setups (default 0)

    Returns:
        Gmail web interface URL
    """
    return f"https://mail.google.com/mail/u/{account_index}/#all/{item_id}"


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
    from_email: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Prepare a Gmail message for sending.

    Args:
        subject: Email subject
        body: Email body content
        to: Recipient email address
        cc: CC email address
        bcc: BCC email address
        thread_id: Thread ID for replies
        in_reply_to: Message-ID being replied to
        references: Chain of Message-IDs for threading
        body_format: "plain" or "html"
        from_email: Sender email address

    Returns:
        Tuple of (base64-encoded raw message, final thread_id)
    """
    if body_format == "html":
        message = MIMEText(body, "html")
    else:
        message = MIMEText(body, "plain")

    message["Subject"] = subject
    if to:
        message["To"] = to
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    if from_email:
        message["From"] = from_email

    # Add threading headers
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references

    # Encode message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    return raw_message, thread_id


def _format_thread_content(thread_data: dict, thread_id: str) -> str:
    """Format Gmail thread content for display.

    Args:
        thread_data: Thread data from Gmail API
        thread_id: Thread ID

    Returns:
        Formatted thread content string
    """
    messages = thread_data.get("messages", [])
    if not messages:
        return f"Thread {thread_id} has no messages."

    # Get thread subject from first message
    first_payload = messages[0].get("payload", {})
    first_headers = _extract_headers(first_payload, ["Subject"])
    thread_subject = first_headers.get("Subject", "(no subject)")

    content_lines = [
        f"Thread ID: {thread_id}",
        f"Subject: {thread_subject}",
        f"Messages: {len(messages)}",
        f"Web Link: {_generate_gmail_web_url(thread_id)}",
        "",
    ]

    # Format each message in the thread
    for i, message in enumerate(messages, 1):
        payload = message.get("payload", {})
        headers = _extract_headers(payload, ["From", "Date", "Subject", "To", "Cc"])
        sender = headers.get("From", "(unknown sender)")
        date = headers.get("Date", "(unknown date)")
        subject = headers.get("Subject", "(no subject)")
        to = headers.get("To", "")
        cc = headers.get("Cc", "")

        # Extract both text and HTML bodies
        bodies = _extract_message_bodies(payload)
        text_body = bodies.get("text", "")
        html_body = bodies.get("html", "")

        # Format body content with HTML fallback
        body_data = _format_body_content(text_body, html_body)

        # Add message to content
        content_lines.extend(
            [
                f"=== Message {i} ===",
                f"From: {sender}",
                f"Date: {date}",
            ]
        )

        # Only show subject if it's different from thread subject
        if subject != thread_subject:
            content_lines.append(f"Subject: {subject}")

        if to:
            content_lines.append(f"To: {to}")
        if cc:
            content_lines.append(f"Cc: {cc}")

        content_lines.extend(
            [
                "",
                body_data,
                "",
            ]
        )

    return "\n".join(content_lines)


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
            "Click 'Connect Google Services' in Settings to authorize this account."
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

    # Fetch metadata for each message to get subjects and attachments
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

        # Fetch subject and attachments from message metadata
        subject = "(no subject)"
        attachments = []
        if message_id != "unknown":
            try:
                full_message = await asyncio.to_thread(
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute
                )
                payload = full_message.get("payload", {})
                headers = _extract_headers(payload, ["Subject"])
                subject = headers.get("Subject", "(no subject)")
                attachments = _extract_attachments(payload)
            except Exception:
                # If fetch fails, continue with defaults
                pass

        message_lines = [
            f"{idx}. Subject: {subject}",
            f"   Message ID: {message_id}",
            f"   Thread ID: {thread_id}",
            f"   Message URL: {message_url}",
            f"   Thread URL:  {thread_url}",
            f"   Snippet: {snippet}",
        ]

        if attachments:
            message_lines.append(f"   Attachments ({len(attachments)}):")
            for att_idx, att in enumerate(attachments, start=1):
                att_filename = att.get("filename", "unknown")
                att_size = att.get("size", 0)
                att_mime = att.get("mimeType", "unknown")
                att_id = att.get("attachmentId", "unknown")
                size_kb = att_size / 1024 if att_size else 0
                message_lines.append(
                    f"      {att_idx}. {att_filename} ({size_kb:.1f} KB, {att_mime})"
                )
                message_lines.append(f"         ID: {att_id}")

        message_lines.append("")
        lines.extend(message_lines)

    if next_token:
        lines.append(f"Next page token: {next_token}")

    return "\n".join(lines)


@mcp.tool("get_gmail_message_content")
async def get_gmail_message_content(
    message_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """**Gmail emails ONLY** - retrieve content of a Gmail message by message ID.

    ⚠️ CRITICAL: This tool is for GMAIL MESSAGE IDs ONLY (16-character base64 strings).
    DO NOT use Google Drive file IDs here - they will fail with "Invalid id value".

    For Google Drive files, use gdrive_get_file_content instead.

    Args:
        message_id: Gmail message ID (16-char format like "18d2a3b4c5d6e7f8")
                   Get this from list_gmail_messages, NOT from Drive file listings
        user_email: User's email for authentication

    Returns:
        Email subject, sender, and body content

    ID Format Guide:
        ✅ Gmail message ID: "18d2a3b4c5d6e7f8" (16 characters, from list_gmail_messages)
        ❌ Drive file ID: "1mJ9MIWIashvrW5lpvDMrQZxTy4DhmWpx" (longer alphanumeric)
    """
    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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

    Preserves the original filename when available and avoids redundant API
    calls by delegating to a shared helper. Returns the internal attachment ID
    and a local URL.
    """
    if not session_id or not session_id.strip():
        return "session_id is required to register the attachment."

    try:
        service = get_gmail_service(user_email)
    except ValueError as exc:
        return (
            f"Authentication error: {exc}. "
            "Click 'Connect Google Services' in Settings to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    try:
        data = await fetch_gmail_attachment_data(service, message_id, attachment_id)
    except Exception as exc:
        return f"Failed to download attachment: {exc}"

    try:
        attachment_service = await _get_attachment_service()
        record = await attachment_service.save_bytes(
            session_id=session_id,
            data=data["content_bytes"],
            mime_type=data["mime_type"],
            filename_hint=data["filename"],
        )
    except AttachmentTooLarge as exc:
        return f"Attachment rejected: {exc}"
    except AttachmentError as exc:
        return f"Failed to store attachment: {exc}"

    metadata = record.get("metadata") or {}
    filename = metadata.get("filename") or data["filename"]
    signed_url = record.get("signed_url") or record.get("display_url")
    expires_at = record.get("expires_at") or record.get("signed_url_expires_at")

    lines = [
        "Attachment stored in chat history!",
        f"Attachment ID: {record.get('attachment_id')}",
        f"Filename: {filename}",
        f"MIME: {record.get('mime_type')}",
        f"Size: {record.get('size_bytes')} bytes",
        f"Signed URL: {signed_url}",
    ]
    if expires_at:
        lines.append(f"Expires At: {expires_at}")
    return "\n".join(lines)


@mcp.tool("debug_gmail_attachment_metadata")
async def debug_gmail_attachment_metadata(
    message_id: str,
    attachment_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> str:
    """Inspect Gmail part metadata for an attachment to diagnose filename issues.

    Returns key fields including partId, mimeType, Gmail-provided filename, and
    relevant headers. Use this if a saved file falls back to file.bin.
    """
    try:
        service = get_gmail_service(user_email)
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
    part = find_attachment_part(payload, attachment_id)
    if not part:
        return (
            "Attachment part not found in message payload. "
            "Ensure attachment_id belongs to this message."
        )

    headers = {h.get("name"): h.get("value") for h in (part.get("headers") or [])}
    effective = extract_filename_from_part(part)
    body = part.get("body") or {}
    lines = [
        f"partId: {part.get('partId')}",
        f"mimeType: {part.get('mimeType')}",
        f"gmail_filename_field: {part.get('filename')}",
        f"resolved_filename: {effective}",
        f"attachmentId: {body.get('attachmentId')}",
        f"size: {body.get('size')}",
        "",
        "Headers:",
    ]
    for key in (
        "Content-Disposition",
        "Content-Type",
        "Content-ID",
        "Content-Description",
        "Content-Location",
        "X-Attachment-Id",
        "X-Attachment-Info",
    ):
        if key in headers:
            lines.append(f"- {key}: {headers.get(key)}")
    if len(lines) <= 7:
        lines.append("(no relevant headers found on this part)")
    return "\n".join(lines)


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
            "Click 'Connect Google Services' in Settings to authorize this account."
        )
    except Exception as exc:
        return f"Error creating Gmail service: {exc}"

    # If no attachment_id provided, pick one from the message
    selected_attachment_id = attachment_id
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
        selected_mime = top.get("mimeType")

    try:
        data = await fetch_gmail_attachment_data(
            service, message_id, str(selected_attachment_id)
        )
    except Exception as exc:
        return f"Failed to download attachment: {exc}"

    filename = data["filename"]
    mime_type = (
        data.get("mime_type") or selected_mime or "application/octet-stream"
    ).lower()
    content_bytes = data["content_bytes"]

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
            f"Attachment text extracted!\nFilename: {filename}\nMIME: {mime_type}\n\n"
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
    """**Gmail email attachments ONLY** - extract text from file attached to Gmail message.

    This tool is for attachments sent via Gmail email. NOT for Google Drive files.
    For Google Drive documents, use extract_document with the Drive URL directly.

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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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
            "Click 'Connect Google Services' in Settings to authorize this account."
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


def run(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = DEFAULT_HTTP_PORT,
) -> None:  # pragma: no cover - integration entrypoint
    """Run the MCP server with the specified transport."""
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=host,
            port=port,
            json_response=True,
            stateless_http=True,
            uvicorn_config={"access_log": False},
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover - CLI helper
    import argparse
    parser = argparse.ArgumentParser(description="Gmail MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol to use",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind HTTP server to",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help="Port for HTTP server",
    )
    args = parser.parse_args()
    run(args.transport, args.host, args.port)


__all__ = [
    "mcp",
    "run",
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
