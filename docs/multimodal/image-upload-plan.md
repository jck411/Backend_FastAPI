# Image Upload MVP

## Goals
- Allow users to attach one or more images to a chat turn through the "+" button in the composer.
- Store attachments as metadata + URLs (no binary blobs) so they can persist with the conversation and be re-used when retrying or editing messages.
- Send image references to OpenRouter using the `image_url` modality while keeping the request payload light.
- Lay groundwork for adding PDFs and audio by sharing attachment plumbing, validation, and persistence patterns.

## Terminology
- **Attachment** – uploaded media + metadata tracked by the backend.
- **Content part** – one segment within a chat message. Each part is either text or an attachment reference.
- **Delivery URL** – signed/static URL that OpenRouter will fetch when invoking the model.
- **Display URL** – UI-friendly URL (object URL or CDN) for showing previews inside the chat UI.

## Data Model
### Message schema
- Extend `ConversationMessage` (frontend) and repository messages (backend) with `parts: ContentPart[]`.
- `ContentPart` union:
  - `text`: `{ type: 'text', text: string }`
  - `image`: `{ type: 'image', id: string, mimeType: string, sizeBytes: number, displayUrl: string, deliveryUrl: string, uploadedAt: string, expiresAt?: string | null, width?: number, height?: number, fileName?: string }`
- `ConversationMessage.content` stays for backwards compatibility (joined text from text parts) until tooling is fully updated.
- Persist `parts` by storing the full array in the `messages.content` column (serialized JSON); `_CONTENT_JSON_METADATA_KEY` already tracks structured payloads.

### Attachment catalog
- Create a lightweight `attachments` table or JSON index to track orphaned uploads (id, storage_key, mime, size, created_at, expires_at, last_used_at).
  - MVP: table `attachments(session_id TEXT, attachment_id TEXT PRIMARY KEY, storage_path TEXT, mime_type TEXT, size_bytes INTEGER, display_url TEXT, delivery_url TEXT, metadata TEXT, created_at DATETIME, expires_at DATETIME)`.
  - Enables cleanup jobs and auditing when attachments are deleted or expire.
- `messages` rows reference attachments only via `parts[].id` (no foreign key needed, but can be added later).

### Storage layout
- Configurable base path `settings.attachments_dir` (default `data/uploads`).
- Per-session subdirectories (`{session_id}/`) keep files grouped.
- Filenames use `{attachment_id}{extension}` to prevent clashes.
- Serve files through a dedicated route that validates the `attachment_id` and issues the file with proper headers.

## Backend API
### Upload
- `POST /api/uploads` (multipart/form-data, field `file` + optional `session_id`).
- Validations:
  - MIME whitelist: `image/png`, `image/jpeg`, `image/webp`, `image/gif`.
  - Max size (configurable, default 10 MB).
- On success:
  - Persist attachment metadata.
  - Store file on disk.
  - Respond with payload `{ attachment: { id, session_id, mimeType, sizeBytes, fileName, displayUrl, deliveryUrl, uploadedAt, expiresAt } }`.

### Download
- `GET /uploads/{attachment_id}` to stream the file with caching disabled by default.
  - Checks attachment exists and has not expired.
  - Optionally enforces session ownership via query/token.

### Delete (later)
- `DELETE /api/uploads/{attachment_id}` to remove unused attachments if a message is discarded.
- Cleanup job to purge expired attachments.

### Sending to OpenRouter
- When building the outbound payload, map each `image` part to:
  ```json
  {
    "type": "image_url",
    "image_url": { "url": "<deliveryUrl>" }
  }
  ```
- Text parts remain as `{"type":"text","text": ...}` ensuring prompts precede images.

## Frontend Integration
- Extend chat composer state to track `draft.attachments: AttachmentDraft[]` with lifecycle states (`queued` -> `uploading` -> `ready` -> `failed`).
- Use the "+" button to trigger a hidden `<input type="file" accept="image/*">` allowing multiple selections.
- Immediately create preview object URLs for UI thumbnails.
- Upload each selection via `POST /api/uploads`; update the draft entry with returned metadata.
- Disable send while any attachment is still uploading.
- On submit:
  - Construct `parts`: first text (if non-empty) then each `image` in upload order.
  - Call `chatStore.sendMessage({ text, parts, attachments })` (new signature) so the store can persist structured content.
  - Reset composer state and revoke object URLs.
- Update message rendering to use `parts`. Text parts continue to use Markdown; image parts render as `<img>` with fallback alt text and clickable lightbox.

## Validation & Best Practices
- Frontend guards: limit per-message image count (configurable, default 4), enforce size limits before upload, surface errors inline.
- Backend scanning hook placeholder for antivirus/image safety (future).
- Log upload + send events without including full URLs if they contain sensitive data; consider hashing if necessary.
- Add retention policy config (e.g., delete attachments 7 days after last use).

## Preparing for PDFs & Audio
- Attachment schema is extensible—additional `type` variants (`pdf`, `audio`) can reuse the same upload API with mime-specific validation.
- Delivery pipeline already carries generic fields (`id`, `mimeType`, `deliveryUrl`). Only the OpenRouter mapping layer changes per modality:
  - `pdf` -> `{"type":"file","file":{ "url": ... }}`
  - `audio` -> `{"type":"input_audio","input_audio":{ "url"|"data"... }}`
- Composer UI can enable new accept filters and preview components per attachment type without revisiting backend plumbing.

## Open Questions / Follow-ups
- Do we require signed URLs with expiry instead of static routes? (Depends on deployment environment.)
- Should attachment uploads require the session id to scope visibility? (Recommended for access control.)
- Define background job or CLI command for pruning expired/unused attachments.

