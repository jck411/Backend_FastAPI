# Gmail Attachments (Local-Only Flow)

This guide explains how Gmail attachments are handled without requiring ngrok or any public URL.

## Summary
- The Gmail MCP server saves attachments to local storage and registers metadata in the chat database.
- Delivery URLs in Gmail flows now default to `http://localhost:8000` to avoid reliance on ngrok.
- A new one‑shot tool, `read_gmail_attachment_text`, downloads an attachment and returns extracted text directly (no external HTTP fetch).
- Public URLs are optional and used only for display if configured via `ATTACHMENTS_PUBLIC_BASE_URL`.

## Tools

- `list_gmail_message_attachments` — enumerate attachments for a message.
- `download_gmail_attachment` — save an attachment to local storage and return metadata and a Local URL.
- `read_gmail_attachment_text` — download + extract the attachment content in one step (preferred).
- `extract_saved_attachment` (from the PDF server) — extract text from a previously saved attachment by internal ID.
  - Tip: The PDF server also accepts local file paths under `data/uploads` via `extract_document`. You can pass either an absolute path like `/home/jack/Backend_FastAPI/data/uploads/<session>/<file>.pdf` or a path relative to `data/uploads` (e.g. `current/file.pdf`). Files outside `data/uploads` are handled by the upstream extractor as before.
  - You can list and search local uploads using:
    - `list_upload_paths(subdir?, pattern?, max_results?)` — enumerate files/folders under `data/uploads`. Results include `original_filename` (when available) from stored metadata; prefer this over the hashed storage name.
    - `search_upload_paths(query, session_id?, max_results?)` — find files by substring or glob (e.g., `*.pdf`).

## Environment

- `.env` (optional):
  - `ATTACHMENTS_PUBLIC_BASE_URL` — if set, a Public URL is shown for convenience, but Gmail processing still uses the Local URL.
  - If you do not want ngrok at all, either remove this setting or set it to `http://localhost:8000`.
- Restart the backend after changing `.env`.

## Typical Flows

### A) One‑shot read (recommended)
1) Call `read_gmail_attachment_text` with a `message_id` and `session_id`.
   - You can specify either `attachment_id` or let the tool pick the best candidate using `filename_contains` and/or `prefer_mime`:

```json
{
  "message_id": "<gmail_message_id>",
  "session_id": "current",
  "filename_contains": "policy",    // optional
  "prefer_mime": "application/pdf", // optional
  "force_ocr": true                  // optional, helpful for scanned PDFs
}
```

The tool returns the extracted text (with an OCR retry for PDFs if needed) and basic attachment details.

### B) Manual two‑step
1) `list_gmail_message_attachments` to find the `attachmentId`.
2) `download_gmail_attachment` to save it locally. The output includes:
   - `Attachment ID` (internal id used by our storage)
   - `Local URL` (always `http://localhost:8000/...`)
   - `Public URL` (only shown if configured)
3) `extract_saved_attachment` (PDF server) with the returned internal id:

```json
{
  "attachment_id": "<internal_id_from_download>"
}
```

This returns extracted text from the saved file.

## Storage and Retention
- Files are stored under `data/uploads/<session_id>/`.
- The default retention is 7 days (`ATTACHMENTS_RETENTION_DAYS`), after which resources may be cleaned up.

## Notes
- If you previously used ngrok for downloads, you no longer need it for Gmail attachment extraction.
- Public URLs are still useful when you need to share a file externally or let third‑party services fetch it, but Gmail → PDF extraction runs entirely on localhost.
