# Image Upload Setup for LLM Chat

This guide explains how to set up image uploads so that LLMs can access your uploaded images.

Note (Gmail attachments): Gmail attachment downloads and PDF extraction now run entirely on localhost and do not require ngrok. Use this document only when you need third‑party LLMs to fetch files over HTTPS (e.g., images sent directly to the model).

## Why This Setup Is Needed

LLM providers (OpenAI, Anthropic, etc.) need to fetch images from publicly accessible HTTPS URLs. Since your FastAPI backend runs locally (`http://localhost:8000`), LLMs can't access the images directly.

**Solution**: Use ngrok to create a secure HTTPS tunnel that makes your local backend publicly accessible.

## One-Time Setup (Already Done)

✅ **ngrok account**: Free account at https://ngrok.com
✅ **Authtoken configured**: Your ngrok authtoken is saved
✅ **pyngrok installed**: Python package for ngrok integration
✅ **Scripts created**: `ngrok_tunnel.py` and `setup_ngrok.py`

## Every Time You Want to Use Images

### 1. Start Your Services (3 terminals)

**Terminal 1 - Backend:**
```bash
cd ~/Backend_FastAPI
uv run uvicorn backend.app:app --reload --app-dir src
```

**Terminal 2 - Frontend:**
```bash
cd ~/Backend_FastAPI/frontend
npm run dev
```

**Terminal 3 - Ngrok Tunnel:**
```bash
cd ~/Backend_FastAPI
uv run python ngrok_tunnel.py
```

### 2. The ngrok script will:
- Create an HTTPS tunnel (e.g., `https://abc123.ngrok-free.dev`)
- Automatically update your `.env` file with `ATTACHMENTS_PUBLIC_BASE_URL=https://abc123.ngrok-free.dev`
- Display the tunnel URL
- Keep running until you press Ctrl+C

### 3. Restart Backend (Important!)
Since the `.env` file was updated, restart your FastAPI backend:
- Press `Ctrl+C` in Terminal 1
- Run the backend command again:
```bash
uv run uvicorn backend.app:app --reload --app-dir src
```

### 4. Test Image Upload
- Upload an image through your frontend
- The response should include a `delivery_url` with your ngrok hostname
- LLMs can now access the image via the HTTPS URL

## Important Notes

### ⚠️ Tunnel URL Changes
- **Every time you restart ngrok, you get a new URL**
- The script automatically updates your `.env` file
- **Always restart your backend** after the tunnel starts

### 🔄 Development Workflow
1. Start backend → Start frontend → Start ngrok tunnel
2. Restart backend (to pick up new tunnel URL)
3. Upload images and chat with LLMs
4. When done: Ctrl+C all three terminals

### 🚫 When You Don't Need Images
If you're not uploading images to LLMs:
- You only need the backend and frontend running
- No need for ngrok tunnel

### 💡 Alternative: ngrok CLI
If you prefer using ngrok CLI directly:
```bash
ngrok http http://localhost:8000
```
Then manually add the HTTPS URL to your `.env` file:
```
ATTACHMENTS_PUBLIC_BASE_URL=https://your-ngrok-url.ngrok-free.dev
```

## Troubleshooting

### "Authentication failed" error
- Check if your authtoken is configured: `ngrok config check`
- Re-run setup: `uv run python setup_ngrok.py`

### Images not loading in LLM
- Verify the `delivery_url` in upload response has ngrok hostname
- Check that ngrok tunnel is still running
- Ensure backend was restarted after tunnel started

### Tunnel keeps disconnecting
- Free ngrok accounts have session limits
- Consider upgrading to paid plan for longer sessions
- Or simply restart the tunnel when needed

## Files Created
- `ngrok_tunnel.py` - Automated tunnel setup script
- `setup_ngrok.py` - One-time authtoken configuration
- `.env` - Contains `ATTACHMENTS_PUBLIC_BASE_URL` (auto-updated)

## How It Works

1. **Image Upload**: Frontend uploads image to FastAPI backend
2. **Storage**: Backend saves image to `data/uploads/session_id/`
3. **URL Generation**: Backend creates two URLs:
   - `display_url`: Local URL for debugging
   - `delivery_url`: Public ngrok URL for LLMs
4. **LLM Access**: LLM providers fetch image from `delivery_url`

The `_apply_public_base()` method in `AttachmentService` converts local URLs to ngrok URLs using the `ATTACHMENTS_PUBLIC_BASE_URL` environment variable.
