# Multimodal Image Implementation Plan

## Overview
Implement image input and output support in chat using Google Drive for public URL hosting instead of ngrok.

## Current State Analysis

### What We Have
1. ✅ **Attachment Upload System** (`AttachmentService`)
   - Stores images locally in `data/uploads/session_id/`
   - Supports: PNG, JPEG, WebP, GIF, PDF
   - Creates `display_url` (local) and `delivery_url` (ngrok or local)

2. ✅ **Google Drive MCP Server** (`gdrive_server.py`)
   - Full CRUD operations on Drive files
   - Upload, download, permissions management
   - Public sharing tools: `gdrive_check_public_access`, `gdrive_file_permissions`

3. ✅ **Chat Schema** (`ChatMessage`)
   - Currently: `content: Any` (typically string)
   - Needs: Support for OpenRouter multimodal format

### OpenRouter Image Format Requirements

**Input Format (what we need to send):**
```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "What's in this image?"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "https://drive.google.com/uc?export=view&id=FILE_ID"
      }
    }
  ]
}
```

**Alternative - Base64 (not preferred due to size):**
```json
{
  "type": "image_url",
  "image_url": {
    "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
  }
}
```

### Key Requirements
- Images must be accessible via public HTTPS URLs
- URL format for GDrive: `https://drive.google.com/uc?export=view&id={file_id}`
- File must have "Anyone with the link" permission
- Models check `input_modalities: ["text", "image"]` in their architecture

## Implementation Plan - Step by Step

### Phase 1: Schema & Core Functions (Steps 1-4)

#### Step 1: Add GDrive Public URL Tool
**File:** `src/backend/mcp_servers/gdrive_server.py`

```python
@mcp.tool("gdrive_get_public_url")
async def get_public_url(
    file_id: str,
    user_email: str = DEFAULT_USER_EMAIL,
) -> Dict[str, Any]:
    """
    Ensure a Drive file is publicly viewable and return the direct-view URL.
    """
    # 1. Get file permissions
    # 2. If missing, create "anyone:reader" permission via Drive API
    # 3. Verify public access and surface precise errors on failure
    # 4. Return: {"url": "https://drive.google.com/uc?...", "file_id": "...", "public": true}
```

**Test:** Create test file, verify URL format, check public access requirement.

---

#### Step 2: Update ChatMessage Schema
**File:** `src/backend/schemas/chat.py`

```python
from typing import Union, List, Dict

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Union[str, List[Dict[str, Any]]]  # ← Changed from Any
    # ... rest unchanged
```

**Test:**
- Old format still works: `ChatMessage(role="user", content="hello")`
- New format works: `ChatMessage(role="user", content=[{"type": "text", "text": "hello"}])`

---

#### Step 3: Add GDrive Upload Method to AttachmentService
**File:** `src/backend/services/attachments.py`

```python
async def upload_to_gdrive(
    self,
    attachment_id: str,
    user_email: str = "jck411@gmail.com",
) -> str:
    """
    Upload a stored attachment to Google Drive (once) and make it public.
    Returns the cached public viewing URL.

    Steps:
    1. Resolve attachment from DB (and check for cached Drive metadata)
    2. If missing, read file from disk and upload via gdrive_server.create_drive_file
    3. Set public permissions (or reuse existing)
    4. Persist `gdrive_file_id`, `gdrive_public_url`, `gdrive_uploaded_at`
    5. Return cached public URL
    """
```

**Schema update:** Add nullable fields to `Attachment` model/table for Drive metadata.

**Test:** Upload test image, verify file appears in Drive, verify URL is cached on subsequent calls without duplicate uploads.

---

#### Step 4: Add URL Helper Function
**File:** `src/backend/mcp_servers/gdrive_helpers.py`

```python
def build_drive_direct_url(file_id: str) -> str:
    """Build the direct-view URL for a Google Drive file."""
    return f"https://drive.google.com/uc?export=view&id={file_id}"
```

**Test:** Unit test with known file IDs.

---

### Phase 2: Orchestrator Integration (Step 5)

#### Step 5: Transform Attachments in Orchestrator
**File:** `src/backend/chat/orchestrator.py`

Add new method:
```python
async def _transform_message_content(
    self,
    content: Any,
    session_id: str,
) -> Any:
    """
    Convert message content with local attachment references to
    OpenRouter multimodal format with cached GDrive URLs.

    Input:
    - String → unchanged
    - List with metadata.attachment_id → upload to GDrive, return multimodal format

    Output:
    - String (unchanged) or List[Dict] with image_url entries
    """
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return content

    transformed = []
    for item in content:
        if not isinstance(item, dict):
            transformed.append(item)
            continue

        # Check if this is an attachment reference
        metadata = item.get("metadata", {})
        attachment_id = metadata.get("attachment_id")

        if not attachment_id:
            transformed.append(item)
            continue

        # Get mime type - only process images
        mime_type = metadata.get("mime_type", "")
        if not mime_type.startswith("image/"):
            transformed.append(item)
            continue

        # Use cached Drive metadata when available; upload once per attachment
        try:
            stored = await self._attachment_service.resolve(attachment_id)
            if stored.gdrive_public_url:
                gdrive_url = stored.gdrive_public_url
            else:
                gdrive_url = await self._upload_attachment_to_gdrive(
                    attachment_id, session_id
                )

            # Replace with OpenRouter image_url format on a copy only
            transformed.append({
                "type": "image_url",
                "image_url": {
                    "url": gdrive_url
                }
            })
        except Exception as exc:
            logger.error(f"Failed to upload attachment {attachment_id}: {exc}")
            # Fallback: keep original or, for small files, inline base64 data URI
            transformed.append(item)

    return transformed if transformed else content
```

Call this in `process_stream` before sending to StreamingHandler:
```python
# In process_stream, when assembling outbound payload:
conversation = await self._repo.get_messages(session_id)
wire_messages = []

for message in conversation:
    payload = message.model_dump()  # or copy dict
    payload["content"] = await self._transform_message_content(
        payload.get("content"),
        session_id,
    )
    wire_messages.append(payload)
```

**Note:** Never mutate the ORM/Pydantic objects returned from the repository in-place. Always work on shallow copies so stored conversation history remains untouched.

**Fallback:** Implement `_inline_base64_image(attachment)` in the orchestrator (or attachment service) so we can gracefully embed small images when Drive calls fail or the user explicitly disables Drive syncing.

**Test:**
1. Upload image via API
2. Send chat message with attachment
3. Verify only new attachments trigger Drive uploads and stored history remains unchanged

---

### Phase 3: Testing (Steps 6-8)

#### Step 6: Schema Tests
**File:** `tests/test_multimodal_schema.py`

```python
def test_chat_message_string_content():
    msg = ChatMessage(role="user", content="hello")
    assert msg.content == "hello"

def test_chat_message_multimodal_content():
    msg = ChatMessage(
        role="user",
        content=[
            {"type": "text", "text": "What's this?"},
            {"type": "image_url", "image_url": {"url": "https://example.com/img.jpg"}}
        ]
    )
    assert isinstance(msg.content, list)
    assert len(msg.content) == 2

def test_chat_completion_request_multimodal():
    req = ChatCompletionRequest(
        messages=[
            ChatMessage(
                role="user",
                content=[
                    {"type": "text", "text": "Describe"},
                    {"type": "image_url", "image_url": {"url": "https://..."}}
                ]
            )
        ]
    )
    payload = req.to_openrouter_payload("default-model")
    assert isinstance(payload["messages"][0]["content"], list)
```

---

#### Step 7: GDrive Upload Tests
**File:** `tests/test_gdrive_image_upload.py`

```python
@pytest.mark.asyncio
async def test_upload_image_to_gdrive(attachment_service, test_image):
    # 1. Create local attachment
    attachment_id = await attachment_service.save_upload(...)

    # 2. Upload to GDrive
    with mock.patch("services.attachments.gdrive_client") as gdrive:
        gdrive.upload_file.return_value = "file-123"
        gdrive.ensure_public.return_value = "https://drive.google.com/uc?export=view&id=file-123"
        gdrive_url = await attachment_service.upload_to_gdrive(attachment_id)

    # 3. Verify URL format
    assert "drive.google.com/uc?export=view&id=" in gdrive_url

    # 4. Ensure metadata persisted for future reuse
    stored = await attachment_service.resolve(attachment_id)
    assert stored.gdrive_file_id == "file-123"
    assert stored.gdrive_public_url == gdrive_url
```

> Uses `from unittest import mock`.

---

#### Step 8: E2E Chat with Image
**File:** `tests/test_chat_with_image.py`

```python
@pytest.mark.asyncio
async def test_chat_with_image_attachment(client, test_image_path):
    # 1. Upload image
    with open(test_image_path, "rb") as f:
        resp = await client.post(
            "/api/uploads",
            files={"file": ("test.jpg", f, "image/jpeg")},
            data={"session_id": "test-session"}
        )
    attachment = resp.json()["attachment"]

    # 2. Send chat with image reference
    chat_req = {
        "session_id": "test-session",
        "model": "openai/gpt-4o",  # Vision-capable model
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": attachment["deliveryUrl"]},
                        "metadata": {
                            "attachment_id": attachment["id"],
                            "mime_type": "image/jpeg",
                        },
                    }
                ]
            }
        ]
    }

    # 3. Stream response
    async with client.stream("POST", "/api/chat/stream", json=chat_req) as resp:
        chunks = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                chunks.append(line[6:])

    # 4. Verify we got content back and transformation used the Drive URL
    assert len(chunks) > 0
    assert "[DONE]" in chunks[-1]
    assert any("drive.google.com/uc?export=view" in chunk for chunk in chunks)
```

---

### Phase 4: Frontend Integration (Step 10)

#### Step 10: Update Frontend Message Format
**File:** `frontend/src/lib/api/chat.ts` (or equivalent)

Current format:
```typescript
{
  role: "user",
  content: "text message"
}
```

New format for images:
```typescript
{
  role: "user",
  content: [
    { type: "text", text: "What's in this image?" },
    {
      type: "image_url",
      image_url: {
        url: attachmentDeliveryUrl
      },
      metadata: {
        attachment_id: attachmentId  // For reference tracking
      }
    }
  ]
}
```

**Changes needed:**
1. Detect when message has attachments
2. Build content array instead of string
3. Include attachment metadata for backend tracking

---

### Phase 5: Image Output Support (Step 9)

**Investigation Tasks:**
1. Check `/api/models` response for models with `output_modalities: ["image"]`
2. Review OpenRouter docs for image generation format
3. Plan response handling (likely base64 in response)
4. Update streaming handler to detect image outputs
5. Store generated images as attachments
6. Display in frontend

**Note:** This is a future enhancement after input is working.

---

## Migration Strategy

### Backward Compatibility
- Old format (string content) continues to work
- New format (array content) is additive
- Frontend can be updated independently
- No breaking changes to existing conversations

### Rollout Order
1. ✅ Backend schema changes (backward compatible)
2. ✅ Backend orchestrator transformation (transparent)
3. ✅ Tests (ensure stability)
4. Frontend changes (enables UI features)
5. Database migration deployed (adds Drive metadata columns)

### Testing Between Steps
Each step should be tested independently:
- **Step 1:** Test tool in isolation via MCP
- **Step 2:** Test schema with unit tests
- **Step 3:** Test GDrive upload independently
- **Step 4:** Test URL formatting
- **Step 5:** Test full transformation pipeline
- **Step 6-8:** Automated test suite
- **Step 10:** Manual testing in UI

---

## Configuration

### Environment Variables
```bash
# Already configured for Google OAuth
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/google-auth/callback

# For GDrive uploads (default folder)
GDRIVE_UPLOADS_FOLDER_ID=root  # or specific folder ID
```

### Settings
```python
# src/backend/config.py
class Settings(BaseSettings):
    # ... existing ...

    # NEW: GDrive integration
    gdrive_uploads_folder: str = "root"
    gdrive_default_user_email: str = "jck411@gmail.com"
```

---

## Monitoring & Debugging

### Logging Points
1. When attachment is uploaded locally
2. When attachment is uploaded to GDrive
3. When content is transformed for OpenRouter
4. When public URL is generated
5. If any step fails (with fallback behavior)

### Debug Endpoints
Add debug endpoint:
```python
@router.get("/api/debug/attachment/{attachment_id}")
async def debug_attachment(attachment_id: str):
    return {
        "local_path": ...,
        "gdrive_id": ...,
        "gdrive_url": ...,
        "public": ...,
    }
```

---

## Success Criteria

### Must Have (MVP)
- ✅ Upload image locally
- ✅ Upload image to GDrive automatically
- ✅ Make image public
- ✅ Get public URL
- ✅ Send image URL to vision-capable OpenRouter model
- ✅ Receive text response about image

### Nice to Have (Future)
- Support multiple images per message
- Support image generation (output)
- Cache GDrive URLs (don't re-upload)
- Support video/audio modalities
- Download GDrive images locally for faster access

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| GDrive quota limits | High | Implement caching, reuse existing uploads |
| Public URL exposes images | Medium | Use short-lived tokens or private shares |
| Upload failures | Medium | Retry logic + fallback to ngrok |
| Schema breaking changes | High | Extensive backward compatibility tests |
| Large images timeout | Medium | Implement async upload queue |

---

## Next Actions

1. **Start with Step 1** - Add `gdrive_get_public_url` tool
2. **Test it** - Verify it works with existing Drive files
3. **Move to Step 2** - Update schema
4. **Continue sequentially** - Each step builds on previous

Would you like to begin with Step 1?
