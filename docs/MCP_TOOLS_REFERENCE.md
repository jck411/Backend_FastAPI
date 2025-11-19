# MCP Tools Reference

This document explains how to inspect the exact JSON schemas that the LLM receives for all MCP tools.

## Using MCP Inspector

The official [MCP Inspector](https://github.com/modelcontextprotocol/inspector) provides complete tool schemas including parameters, types, defaults, and descriptions.

### Inspect Individual Servers

**Note:** Run these commands from the project root directory (`/home/human/REPOS/Backend_FastAPI`) so the relative `.venv/bin/python` path resolves correctly.

#### UI Mode (Interactive Visual Inspector)
Open a web interface at `http://localhost:6274` to interactively browse and test tools:

```bash
# Calendar & Tasks server
npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_servers.calendar_server

# Gmail server
npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_servers.gmail_server

# Google Drive server
npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_servers.gdrive_server

# PDF & Document Extraction server
npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_servers.pdf_server

# Housekeeping server
npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_servers.housekeeping_server

# Calculator server
npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_servers.calculator_server

# Monarch Money server
npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_servers.monarch_server
```

#### CLI Mode (JSON Output)
Get complete tool schemas as JSON for scripting or documentation:

```bash
# List all tools with full schemas
npx @modelcontextprotocol/inspector --cli .venv/bin/python -m backend.mcp_servers.calendar_server --method tools/list

# Call a specific tool to test
npx @modelcontextprotocol/inspector --cli .venv/bin/python -m backend.mcp_servers.calendar_server \
  --method tools/call \
  --tool-name calendar_get_events \
  --tool-arg user_email=jck411@gmail.com

# Output to file for documentation
npx @modelcontextprotocol/inspector --cli .venv/bin/python -m backend.mcp_servers.calendar_server \
  --method tools/list > calendar_tools.json
```

## What MCP Inspector Shows

For each tool, the inspector provides:

- **name**: Exact tool function name
- **description**: Full docstring including parameters and return values
- **inputSchema**: Complete JSON Schema with:
  - Parameter names and types
  - Default values
  - Required vs optional fields
  - Nested object structures
  - Enum values for literals
- **outputSchema**: Return type structure

This is the **exact JSON** that gets sent to the LLM via OpenRouter/OpenAI APIs.

---

## Table of Contents

- [Google Authentication](#google-authentication)
- [Server Overview](#server-overview)
- [Tool Selection Guidelines](#tool-selection-guidelines)
- [Common Patterns](#common-patterns)

## Google Authentication

Google Calendar, Google Tasks, Gmail, and Google Drive share a single OAuth connection managed in the product UI.

**How to connect:**

1. Open System Settings modal in the chat UI
2. Locate the **Google services** card
3. Click **Connect Google Services** (opens Google consent popup)
4. Complete authorization (popup closes automatically)
5. Verify "Connected" status with token expiry time

Once connected, all Calendar, Tasks, Gmail, and Drive tools are available to the LLM.

---

## Server Overview

### Calculator Server
**Module**: `backend.mcp_servers.calculator_server`
**Tools**: Basic arithmetic operations (add, subtract, multiply, divide)

### Calendar & Tasks Server
**Module**: `backend.mcp_servers.calendar_server`
**Tools**: Google Calendar events, Google Tasks management, scheduling, task search
**Key Features**: Smart calendar aggregation, task context discovery, friendly calendar names

### Gmail Server
**Module**: `backend.mcp_servers.gmail_server`
**Tools**: Email search, message content, threads, attachments, sending, labels
**Key Features**: Batch operations, attachment extraction, thread management

### Google Drive Server
**Module**: `backend.mcp_servers.gdrive_server`
**Tools**: File search, folder listing, content extraction, file management, permissions
**Key Features**: Flexible path resolution, Google Workspace export, OCR fallback

### Housekeeping Server
**Module**: `backend.mcp_servers.housekeeping_server`
**Tools**: Current time, chat history, testing utilities
**Key Features**: Timezone-aware timestamps, conversation context

### PDF & Document Extraction Server
**Module**: `backend.mcp_servers.pdf_server`
**Tools**: Document extraction (PDF, Office, images), file search, batch processing
**Key Features**: OCR support, table/entity extraction, URL download support

### Monarch Money Server
**Module**: `backend.mcp_servers.monarch_server`
**Tools**: Account balances, transactions, budgets, cashflow, investment holdings
**Key Features**: Automated session management, MFA handling, multi-account aggregation

---

## Tool Selection Guidelines

| User Intent | Recommended Tool |
|------------|------------------|
| "What time is it?" | `current_time` |
| "What did I say earlier?" | `chat_history` |
| "What do I want to read?" | `search_all_tasks` |
| "What's on my schedule?" | `calendar_get_events` |
| "Create an event" | `calendar_create_event` |
| "Schedule a task" | `calendar_create_task` (include `due` parameter) |
| "Find email about..." | `search_gmail_messages` |
| "Read that attachment" | `read_gmail_attachment_text` or `extract_saved_attachment` |
| "What files do I have?" | `list_upload_paths` or `search_upload_paths` |
| "Extract text from..." | `extract_document` or `extract_saved_attachment` |
| "Find file in Drive" | `gdrive_search_files` |
| "Show my Drive folder" | `gdrive_list_folder` |
| "What's my net worth?" | `get_monarch_accounts` |
| "Show recent spending" | `get_monarch_transactions` |
| "Check my budget" | `get_monarch_budgets` |
| "Analyze my cashflow" | `get_monarch_cashflow` |
| "Show my investments" | `get_monarch_holdings` |
| "Spending by category" | `get_monarch_spending_by_category` |

---

## Common Patterns

### Personal Context Discovery
Before making recommendations, call `search_all_tasks`:
- Empty query → general overview
- Keywords → specific interests (e.g., "read", "watch", "buy")
- Surfaces user's plans, goals, preferences

For combined calendar + tasks view: `calendar_get_events(include_tasks=True)`

### File & Attachment Workflows

**Gmail → Storage → Extraction:**
1. `search_gmail_messages` → find message
2. `download_gmail_attachment` → save locally
3. `extract_saved_attachment` → get text content

**Direct Upload → Extraction:**
1. File uploaded via API
2. `list_upload_paths` → find it
3. `extract_saved_attachment` → extract content

### Calendar & Scheduling
- Use friendly names: "Mom's calendar" → resolves to ID
- Aggregate queries (no `calendar_id`) → search all calendars
- Always include `due` parameter when scheduling tasks
- Check `search_all_tasks` or `calendar_get_events(include_tasks=True)` before scheduling

### Document Intelligence
- PDFs: Auto OCR fallback if no text layer
- URLs: Auto-downloaded and processed
- Uploads: Direct access via attachment ID
- Tables/Entities/Keywords: Enable only when needed (overhead)

---

## Version Information

**Document Version:** 2.2
**Last Updated:** November 19, 2025
**Backend Version:** FastAPI + MCP Integration
**MCP Protocol:** Model Context Protocol

## Related Documentation

- [LLM Tool Decision Guide](./LLM_TOOL_DECISION_GUIDE.md) - How the LLM chooses which tools to use
- [MCP Inspector Repository](https://github.com/modelcontextprotocol/inspector) - Official inspection tool source
