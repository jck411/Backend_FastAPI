"""Custom MCP server for Gmail integration."""

from __future__ import annotations

import asyncio
import base64
from email.mime.text import MIMEText
from typing import Dict, Iterable, List, Literal, Optional

from mcp.server.fastmcp import FastMCP

from backend.config import get_settings
from backend.services.google_auth.auth import (
    authorize_user,
    get_credentials,
    get_gmail_service,
)

mcp = FastMCP("custom-gmail")

DEFAULT_USER_EMAIL = "jck411@gmail.com"
GMAIL_BATCH_SIZE = 25
HTML_BODY_TRUNCATE_LIMIT = 20000


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
    "send_gmail_message",
    "draft_gmail_message",
    "get_gmail_thread_content",
    "get_gmail_threads_content_batch",
    "list_gmail_labels",
    "manage_gmail_label",
    "modify_gmail_message_labels",
    "batch_modify_gmail_message_labels",
]
