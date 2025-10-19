# OpenRouter Image Input/Output Formats

## Key Findings from Documentation

### Image Input Modalities

#### Supported Input Formats

OpenRouter follows the OpenAI-compatible format for multimodal messages:

**Format 1: Public HTTPS URL (Recommended)**
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
        "url": "https://example.com/image.jpg"
      }
    }
  ]
}
```

**Format 2: Base64 Data URI**
```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "Describe this image"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
      }
    }
  ]
}
```

### Model Requirements

To use image inputs, models must have:
```json
{
  "architecture": {
    "modality": "text+image->text",
    "input_modalities": ["text", "image"],
    "output_modalities": ["text"]
  }
}
```

### Example Vision-Capable Models

From the documentation:

1. **OpenAI GPT-4o**
   - `id`: `"openai/gpt-4o"`
   - Input: text, image, file
   - Context: 128K tokens
   - Pricing: $0.003613 per image

2. **Meta Llama 3.2 90B Vision**
   - `id`: `"meta-llama/llama-3.2-90b-vision-instruct"`
   - Input: text, image
   - Context: 131K tokens
   - Pricing: $0.001734 per image

3. **Google Gemini**
   - `id`: `"gemini"`
   - Input: text, image, file, audio
   - Context: 1M tokens
   - Pricing: $0.00516 per image

4. **Amazon Nova Lite 1.0**
   - `id`: `"amazon/nova-lite-v1"`
   - Input: text, image
   - Context: 300K tokens
   - Pricing: $0.00009 per image (very cheap!)

5. **Qwen VL Max**
   - `id`: `"qwen/qwen-vl-max"`
   - Input: text, image
   - Context: 7.5K tokens
   - Pricing: $0.001024 per image

### Image Constraints (from xAI Grok docs)

- **Maximum size**: 20 MiB per image
- **Formats**: JPG/JPEG, PNG
- **Number of images**: No limit
- **Order**: Any mix of text and images allowed

### Google Drive Image URLs

For public Google Drive files, use this URL format:
```
https://drive.google.com/uc?export=view&id={FILE_ID}
```

**Requirements:**
- File must have "Anyone with the link" can view permission
- Image must be in supported format (JPG, PNG, WebP, GIF)
- File must be under 20 MiB

**Verification:**
```python
# Check if file has public access
permissions = file.get("permissions", [])
has_public = any(
    p.get("type") == "anyone" and p.get("role") in {"reader", "commenter", "writer"}
    for p in permissions
)
```

### Image Output (Generation)

Some models support image generation as output:
```json
{
  "architecture": {
    "output_modalities": ["image"]
  }
}
```

**Response format (likely):**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,iVBORw0KGgo..."
          }
        }
      ]
    }
  }]
}
```

**Note:** Image generation requires specific models and different pricing structure.

## Implementation Recommendations

### For Image Input

1. **Use Google Drive URLs** (not base64):
   - Avoids request size limits
   - Faster processing
   - More cost-effective
   - Easier debugging

2. **Upload flow:**
   ```
   User uploads → Local storage → GDrive upload → Make public → Get URL → Send to OpenRouter
   ```

3. **URL caching:**
   - Store GDrive file_id with attachment
   - Reuse if same image sent again
   - Check public access before reusing

4. **Error handling:**
   ```python
   try:
       gdrive_url = await upload_and_get_url(attachment)
   except GDriveError:
       # Fallback to base64 (for small images)
       with open(attachment.path, "rb") as f:
           b64 = base64.b64encode(f.read()).decode()
           url = f"data:{attachment.mime_type};base64,{b64}"
   ```

### For Image Output

1. **Detection:**
   ```python
   if "image_url" in response["choices"][0]["message"]["content"]:
       # Handle image response
   ```

2. **Storage:**
   ```python
   # Save generated image as attachment
   await attachment_service.save_base64(
       session_id=session_id,
       data=base64_data,
       mime_type="image/png",
       source="generated"
   )
   ```

3. **Display:**
   ```typescript
   // Frontend
   if (content.type === "image_url") {
       return <img src={content.image_url.url} alt="Generated" />
   }
   ```

## Testing Strategy

### Unit Tests
```python
def test_format_multimodal_message():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "What's this?"},
            {"type": "image_url", "image_url": {"url": "https://..."}}
        ]
    }
    assert validate_openrouter_format(msg)

def test_gdrive_url_format():
    url = build_drive_url("abc123")
    assert url == "https://drive.google.com/uc?export=view&id=abc123"
```

### Integration Tests
```python
@pytest.mark.asyncio
async def test_upload_to_gdrive_and_chat():
    # Upload image
    attachment_id = await upload_image("test.jpg")

    # Get GDrive URL
    gdrive_url = await get_gdrive_url(attachment_id)

    # Send to OpenRouter
    response = await chat_with_image(gdrive_url, "What's in this image?")

    # Verify response
    assert "assistant" in response["choices"][0]["message"]["role"]
    assert len(response["choices"][0]["message"]["content"]) > 0
```

### Manual Testing Checklist
- [ ] Upload JPG image → verify local storage
- [ ] Upload to GDrive → verify appears in Drive
- [ ] Check public access → verify URL is accessible
- [ ] Send to GPT-4o → verify receives description
- [ ] Send to Gemini → verify receives description
- [ ] Try with PNG → verify works
- [ ] Try with WebP → verify works
- [ ] Try with large image (10MB+) → verify within limits
- [ ] Try with multiple images → verify all processed



## References

- OpenRouter API Docs: https://openrouter.ai/docs
- OpenAI Vision Guide: https://platform.openai.com/docs/guides/vision
- Google Drive API: https://developers.google.com/drive/api/guides/manage-uploads
- Anthropic Vision: https://docs.anthropic.com/en/docs/build-with-claude/vision
