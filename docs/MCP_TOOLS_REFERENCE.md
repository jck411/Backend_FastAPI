# MCP Tools Reference

This document provides a human-readable reference for all Model Context Protocol (MCP) tools exposed to the LLM in this application.

## Table of Contents

- [Google Authentication](#google-authentication)
- [Calculator Server](#calculator-server)
- [Calendar & Tasks Server](#calendar--tasks-server)
- [Google Drive Server](#google-drive-server)
- [Gmail Server](#gmail-server)
- [Housekeeping Server](#housekeeping-server)
- [PDF & Document Extraction Server](#pdf--document-extraction-server)

## Google Authentication

Google Calendar, Google Tasks, Gmail, and Google Drive now share a single OAuth
connection that is managed in the product UI rather than through MCP tools.

**How to connect or refresh credentials:**

1. Open the System Settings modal in the chat UI and locate the **Google services** card.
2. Click **Connect Google Services**. A Google consent window will open in a popup.
3. Complete the authorization. The popup closes automatically and the modal shows the
   connection status, including the token expiry time.
4. Use the same button whenever you need to refresh scopes or re-authorize access.

Once connected, all Calendar, Tasks, Gmail, and Drive tools are available to the LLM
without any additional actions.

---

## Calculator Server

Simple arithmetic operations.

### Tools

#### `calculator_evaluate`
Perform basic arithmetic operations.

**Parameters:**
- `operation` (Literal): One of "add", "subtract", "multiply", "divide"
- `a` (float): First operand
- `b` (float): Second operand

**Returns:** String representation of the result

**Example Use Cases:**
- Simple calculations
- Mathematical operations in conversations

---

## Calendar & Tasks Server

Comprehensive Google Calendar and Google Tasks integration.

> **Authentication:** Use the "Connect Google Services" button in System Settings to
> authorize or refresh access for Calendar and Tasks tools.

### Calendar Event Tools

#### `calendar_get_events`
Retrieve events across user's Google calendars with smart aggregation.

**Parameters:**
- `user_email` (str): User's email address
- `calendar_id` (str, optional): Specific calendar ID or friendly name (e.g., "Family Calendar")
- `time_min` (str, optional): Start time (ISO 8601 or RFC3339)
- `time_max` (str, optional): End time (ISO 8601 or RFC3339)
- `max_results` (int, default: 25): Maximum events to return
- `query` (str, optional): Search query
- `detailed` (bool, default: False): Include full details

**Returns:** Formatted string with event details, including tasks if querying aggregate calendars

**What it exposes to LLM:**
- Calendar events with titles, times, locations, descriptions
- Event IDs and web links
- Deduplication across multiple calendars
- Integration with Google Tasks (due/overdue tasks)
- Smart calendar name resolution (supports friendly names like "Mom's work schedule")

#### `calendar_create_event`
Create a new calendar event.

**Parameters:**
- `user_email` (str): User's email address
- `summary` (str): Event title
- `start_time` (str): Start time (RFC3339 or YYYY-MM-DD for all-day)
- `end_time` (str): End time (RFC3339 or YYYY-MM-DD for all-day)
- `calendar_id` (str, optional, default: "primary"): Target calendar
- `description` (str, optional): Event description
- `location` (str, optional): Event location
- `attendees` (list[str], optional): Email addresses of attendees

**Returns:** Confirmation with event link

#### `calendar_update_event`
Update an existing calendar event.

**Parameters:**
- `user_email` (str): User's email address
- `event_id` (str): ID of event to update
- `calendar_id` (str, optional): Calendar ID
- `summary` (str, optional): New title
- `start_time` (str, optional): New start time
- `end_time` (str, optional): New end time
- `description` (str, optional): New description
- `location` (str, optional): New location
- `attendees` (list[str], optional): New attendee list

**Returns:** Confirmation with updated details

#### `calendar_delete_event`
Delete a calendar event.

**Parameters:**
- `user_email` (str): User's email address
- `event_id` (str): ID of event to delete
- `calendar_id` (str, optional): Calendar ID

**Returns:** Confirmation message

#### `calendar_list_calendars`
List all calendars the user has access to.

**Parameters:**
- `user_email` (str): User's email address
- `max_results` (int, default: 100): Maximum calendars to return

**Returns:** List of calendars with IDs, names, and access levels

### Google Tasks Tools

#### `calendar_list_task_lists`
List available Google Tasks lists.

**Parameters:**
- `user_email` (str): User's email address
- `max_results` (int, default: 100): Maximum lists to return
- `page_token` (str, optional): Pagination token

**Returns:** Formatted list of task lists with IDs and titles

#### `list_tasks`
List tasks from a specific Google Tasks list.

**Parameters:**
- `user_email` (str): User's email address
- `task_list_id` (str, optional): Task list ID or title
- `max_results` (int, optional): Maximum tasks to return
- `page_token` (str, optional): Pagination token
- `show_completed` (bool, default: False): Include completed tasks
- `show_deleted` (bool, default: False): Include deleted tasks
- `show_hidden` (bool, default: False): Include hidden tasks
- `due_min` (str, optional): Lower bound for due dates
- `due_max` (str, optional): Upper bound for due dates
- `task_filter` (str, default: "all"): Filter by "all", "scheduled", "unscheduled", "overdue", "upcoming"

**Returns:** Tasks with due dates, notes, IDs, and links

**What it exposes to LLM:**
- Task titles and status
- Due dates and scheduling information
- Task notes/descriptions
- Web links to tasks
- Pagination support for large lists

#### `search_all_tasks`
**IMPORTANT:** High-priority tool for understanding user context and preferences.

Search across ALL Google Tasks lists to understand what the user plans, wants, or needs.

**Parameters:**
- `user_email` (str): User's email address
- `query` (str, default: ""): Search keywords (empty string returns general overview)
- `task_list_id` (str, optional): Narrow to specific list
- `max_results` (int, default: 25): Maximum matches
- `include_completed` (bool, default: False): Include completed tasks
- `include_hidden` (bool, default: False): Include hidden tasks
- `include_deleted` (bool, default: False): Include deleted tasks
- `search_notes` (bool, default: True): Search task notes
- `due_min` (str, optional): Due date lower bound
- `due_max` (str, optional): Due date upper bound

**Returns:** Matching tasks with full details across all lists

**What it exposes to LLM:**
- User's plans, goals, and intentions
- Things they want to read, watch, buy, or do
- Personal preferences and interests
- Context for making personalized recommendations

**Use this tool when:**
- User asks "what do I want to read/watch/eat/buy?"
- Before offering suggestions or recommendations
- To understand user context for personalized responses
- With short keyword queries from user's request

#### `user_context_from_tasks`
High-priority alias that surfaces personal context from Google Tasks.

**Parameters:**
- `query` (str): Search query (empty for general overview + calendar)
- `user_email` (str): User's email address
- `max_results` (int, default: 25): Maximum results
- `include_completed` (bool, default: False): Include completed tasks

**Returns:** Task overview plus upcoming calendar snapshot when query is empty

**What it exposes to LLM:**
- Combined view of tasks and upcoming calendar events
- Personal context for recommendations
- User's current focus and priorities

#### `calendar_get_task`
Retrieve details of a specific task.

**Parameters:**
- `user_email` (str): User's email address
- `task_list_id` (str, default: "@default"): Task list ID
- `task_id` (str): Task identifier

**Returns:** Full task details including notes, due date, status

#### `calendar_create_task`
Create a new Google Task.

**IMPORTANT:** When user asks to "schedule a task for [date/time]", you MUST include the `due` parameter.

**Parameters:**
- `user_email` (str): User's email address
- `task_list_id` (str, default: "@default"): Task list ID
- `title` (str): Task title
- `notes` (str, optional): Detailed notes
- `due` (str, optional): **REQUIRED FOR SCHEDULING** - Due date/time (ISO 8601 or RFC3339)
- `parent` (str, optional): Parent task ID for subtasks
- `previous` (str, optional): Sibling task ID for positioning

**Returns:** Confirmation with task details and web link

#### `calendar_update_task`
Update an existing task.

**Parameters:**
- `user_email` (str): User's email address
- `task_list_id` (str, default: "@default"): Task list ID
- `task_id` (str): Task identifier
- `title` (str, optional): New title
- `notes` (str, optional): New notes
- `status` (str, optional): "needsAction" or "completed"
- `due` (str, optional): New due date/time

**Returns:** Confirmation with updated details

#### `calendar_delete_task`
Delete a task.

**Parameters:**
- `user_email` (str): User's email address
- `task_list_id` (str, default: "@default"): Task list ID
- `task_id` (str): Task identifier

**Returns:** Confirmation message

#### `calendar_move_task`
Move a task within or across task lists.

**Parameters:**
- `user_email` (str): User's email address
- `task_list_id` (str, default: "@default"): Current list ID
- `task_id` (str): Task identifier
- `parent` (str, optional): New parent task ID
- `previous` (str, optional): Sibling task ID for positioning
- `destination_task_list` (str, optional): Destination list ID

**Returns:** Confirmation with new position

#### `calendar_clear_completed_tasks`
Clear all completed tasks from a list (marks them hidden).

**Parameters:**
- `user_email` (str): User's email address
- `task_list_id` (str, default: "@default"): Task list ID

**Returns:** Confirmation message

---

## Google Drive Server

Comprehensive Google Drive file management and content extraction.

> **Authentication:** Use "Connect Google Services" in the System Settings modal to
> authorize Google Drive access before using these tools.

### File Search & Listing Tools

#### `gdrive_search_files`
Search for files in Google Drive.

**Parameters:**
- `query` (str): Search query (supports Drive query syntax or plain text)
- `user_email` (str): User's email address
- `page_size` (int, default: 10): Results per page
- `drive_id` (str, optional): Specific shared drive ID
- `include_items_from_all_drives` (bool, default: True): Include shared drives
- `corpora` (str, optional): Search scope ("user", "drive", "allDrives")

**Returns:** List of matching files with metadata

**What it exposes to LLM:**
- File names, IDs, MIME types
- File sizes and modification times
- Web view links
- Automatic detection of Drive query syntax vs. plain text

#### `gdrive_list_folder`
List contents of a Google Drive folder.

**Parameters:**
- `folder_id` (str, optional, default: "root"): Folder ID
- `folder_name` (str, optional): Folder name (searches under parent)
- `folder_path` (str, optional): Path like "Reports/2024" relative to root
- `user_email` (str): User's email address
- `page_size` (int, default: 100): Results per page
- `drive_id` (str, optional): Shared drive ID
- `include_items_from_all_drives` (bool, default: True): Include shared drives
- `corpora` (str, optional): Search scope

**Returns:** Contents of the folder with metadata

**What it exposes to LLM:**
- Flexible folder resolution (ID, name, or path)
- File and folder hierarchies
- Warnings when multiple folders match

### File Content Tools

#### `gdrive_get_file_content`
Retrieve and extract text content from a Drive file.

**Parameters:**
- `file_id` (str): File ID
- `user_email` (str): User's email address

**Returns:** Extracted text content

**What it exposes to LLM:**
- Text from Google Docs, Sheets, Presentations (exported as plain text/CSV)
- PDF text extraction (including OCR fallback)
- Office document text (Word, PowerPoint, Excel via XML parsing)
- Automatic export of Google Workspace files to readable formats

#### `gdrive_download_file`
Download a Drive file as base64-encoded bytes.

**Parameters:**
- `file_id` (str): File ID
- `user_email` (str): User's email address
- `export_mime_type` (str, optional): Export format for Google Workspace files

**Returns:** Dictionary with file metadata and base64 content

**What it exposes to LLM:**
- Binary file downloads
- Export control for Google Workspace files
- File metadata (name, MIME type, size, links)

### File Management Tools

#### `gdrive_create_file`
Create a new file in Google Drive.

**Parameters:**
- `file_name` (str): Name for the new file
- `user_email` (str): User's email address
- `content` (str, optional): Text content for the file
- `folder_id` (str, default: "root"): Parent folder ID
- `mime_type` (str, default: "text/plain"): File MIME type
- `file_url` (str, optional): URL to download file content from

**Returns:** Confirmation with file ID and web link

#### `gdrive_delete_file`
Delete or trash a Drive file.

**Parameters:**
- `file_id` (str): File ID
- `user_email` (str): User's email address
- `permanent` (bool, default: False): Permanently delete vs. move to trash

**Returns:** Confirmation message

#### `gdrive_move_file`
Move a file to a different folder.

**Parameters:**
- `file_id` (str): File ID
- `destination_folder_id` (str): Target folder ID
- `user_email` (str): User's email address

**Returns:** Confirmation message

#### `gdrive_copy_file`
Copy a Drive file.

**Parameters:**
- `file_id` (str): File ID
- `user_email` (str): User's email address
- `new_name` (str, optional): Name for the copy
- `destination_folder_id` (str, optional): Destination folder ID

**Returns:** Confirmation with copy ID and link

#### `gdrive_rename_file`
Rename a Drive file.

**Parameters:**
- `file_id` (str): File ID
- `new_name` (str): New file name
- `user_email` (str): User's email address

**Returns:** Confirmation with new name

#### `gdrive_create_folder`
Create a new folder in Google Drive.

**Parameters:**
- `folder_name` (str): Name for the new folder
- `user_email` (str): User's email address
- `parent_folder_id` (str, default: "root"): Parent folder ID

**Returns:** Confirmation with folder ID and link

### Permissions Tools

#### `gdrive_file_permissions`
Get detailed permissions and sharing status for a file.

**Parameters:**
- `file_id` (str): File ID
- `user_email` (str): User's email address

**Returns:** Comprehensive permissions report

**What it exposes to LLM:**
- File sharing status
- Individual permissions (users, groups, domains)
- Public link status
- Whether file can be inserted into Google Docs
- View and download links

#### `gdrive_check_public_access`
Check if a file has public "Anyone with the link" access.

**Parameters:**
- `file_name` (str): File name to search for
- `user_email` (str): User's email address

**Returns:** Public access status and instructions

**What it exposes to LLM:**
- Quick public access verification
- Instructions for enabling public sharing
- Direct Drive image URLs for document insertion

---

## Gmail Server

Comprehensive Gmail integration for reading, searching, sending, and managing email and attachments.

> **Authentication:** Start the authorization flow from the System Settings modal by
> clicking "Connect Google Services".

### Message Search & Retrieval Tools

#### `search_gmail_messages`
Search Gmail messages using Gmail search syntax.

**Parameters:**
- `query` (str): Gmail search query (supports full Gmail syntax)
- `user_email` (str): User's email address
- `page_size` (int, default: 10): Results per page

**Returns:** List of matching messages with metadata

**What it exposes to LLM:**
- Message IDs, thread IDs
- Subjects, senders, snippets
- Web links to messages and threads
- Attachment information (filename, size, MIME type, IDs)

#### `get_gmail_message_content`
Retrieve full content of a specific Gmail message.

**Parameters:**
- `message_id` (str): Message ID
- `user_email` (str): User's email address

**Returns:** Message subject, sender, and body text

**What it exposes to LLM:**
- Full message content (text or HTML)
- Automatic HTML-to-text conversion
- Message metadata

#### `get_gmail_messages_content_batch`
Retrieve content for multiple messages in one call.

**Parameters:**
- `message_ids` (list[str]): List of message IDs
- `user_email` (str): User's email address
- `format` (Literal["full", "metadata"], default: "full"): Response detail level

**Returns:** Batch message content

**What it exposes to LLM:**
- Efficient multi-message retrieval
- Choice between full content or metadata only
- Web links for each message

### Thread Tools

#### `get_gmail_thread_content`
Retrieve all messages in a Gmail thread.

**Parameters:**
- `thread_id` (str): Thread ID
- `user_email` (str): User's email address

**Returns:** Formatted thread conversation

**What it exposes to LLM:**
- Complete conversation history
- Message ordering within threads
- Subject, sender, date for each message
- Body content for all messages

#### `get_gmail_threads_content_batch`
Retrieve multiple threads in one call.

**Parameters:**
- `thread_ids` (list[str]): List of thread IDs
- `user_email` (str): User's email address

**Returns:** Batch thread content

### Attachment Tools

#### `list_gmail_message_attachments`
List attachments for a Gmail message.

**Parameters:**
- `message_id` (str): Message ID
- `user_email` (str): User's email address

**Returns:** Attachment metadata

**What it exposes to LLM:**
- Attachment filenames, MIME types, sizes
- Attachment and part IDs for downloading
- Content disposition information

#### `download_gmail_attachment`
Download and persist a Gmail attachment to local storage.

**Parameters:**
- `message_id` (str): Message ID
- `attachment_id` (str): Attachment ID
- `session_id` (str): Chat session ID for storage
- `user_email` (str): User's email address

**Returns:** Confirmation with internal attachment ID and signed URL

**What it exposes to LLM:**
- Persistent attachment storage
- Original filenames preserved
- Signed URLs for access
- Integration with chat history

#### `read_gmail_attachment_text`
Download a Gmail attachment and extract text content locally.

**Parameters:**
- `message_id` (str): Message ID
- `session_id` (str): Chat session ID
- `attachment_id` (str, optional): Specific attachment ID
- `filename_contains` (str, optional): Filter by filename substring
- `prefer_mime` (str, optional, default: "application/pdf"): Preferred MIME type
- `force_ocr` (bool, default: False): Force OCR for PDFs
- `user_email` (str): User's email address

**Returns:** Extracted text content

**What it exposes to LLM:**
- Automatic text extraction from attachments
- Smart attachment selection when ID not provided
- PDF text extraction with OCR fallback
- Support for Office documents
- No external URLs required (local processing)

#### `extract_gmail_attachment_by_id`
Convenience wrapper for extracting attachment text by ID.

**Parameters:**
- `message_id` (str): Message ID
- `attachment_id` (str): Attachment ID
- `session_id` (str): Chat session ID
- `force_ocr` (bool, default: False): Force OCR
- `user_email` (str): User's email address

**Returns:** Extracted text content

#### `debug_gmail_attachment_metadata`
Inspect Gmail attachment metadata for debugging.

**Parameters:**
- `message_id` (str): Message ID
- `attachment_id` (str): Attachment ID
- `user_email` (str): User's email address

**Returns:** Detailed part metadata and headers

**What it exposes to LLM:**
- Raw Gmail part structure
- Header inspection
- Filename resolution debugging

### Sending & Drafting Tools

#### `send_gmail_message`
Send a Gmail message.

**Parameters:**
- `user_email` (str): User's email address
- `to` (str): Recipient email address
- `subject` (str): Message subject
- `body` (str): Message body
- `body_format` (Literal["plain", "html"], default: "plain"): Body format
- `cc` (str, optional): CC recipients
- `bcc` (str, optional): BCC recipients
- `thread_id` (str, optional): Thread ID for replies
- `in_reply_to` (str, optional): Message ID being replied to
- `references` (str, optional): Reference message IDs

**Returns:** Confirmation with message ID

**What it exposes to LLM:**
- Email sending capability
- Reply threading support
- HTML and plain text formats
- CC/BCC support

#### `draft_gmail_message`
Create a Gmail draft.

**Parameters:**
- `user_email` (str): User's email address
- `subject` (str): Message subject
- `body` (str): Message body
- `to` (str, optional): Recipient email
- `cc` (str, optional): CC recipients
- `bcc` (str, optional): BCC recipients
- `thread_id` (str, optional): Thread ID
- `in_reply_to` (str, optional): Reply message ID
- `references` (str, optional): Reference IDs
- `body_format` (Literal["plain", "html"], default: "plain"): Body format

**Returns:** Confirmation with draft ID

### Label Management Tools

#### `list_gmail_labels`
List all Gmail labels.

**Parameters:**
- `user_email` (str): User's email address

**Returns:** System and user labels with IDs

**What it exposes to LLM:**
- All available labels
- System vs. user-created labels
- Label IDs for management

#### `manage_gmail_label`
Create, update, or delete Gmail labels.

**Parameters:**
- `action` (Literal["create", "update", "delete"]): Action to perform
- `user_email` (str): User's email address
- `name` (str, optional): Label name (required for create)
- `label_id` (str, optional): Label ID (required for update/delete)
- `label_list_visibility` (Literal["labelShow", "labelHide"], default: "labelShow"): Visibility
- `message_list_visibility` (Literal["show", "hide"], default: "show"): Message list visibility

**Returns:** Confirmation with label details

#### `modify_gmail_message_labels`
Add or remove labels from a single message.

**Parameters:**
- `message_id` (str): Message ID
- `add_label_ids` (list[str], optional): Labels to add
- `remove_label_ids` (list[str], optional): Labels to remove
- `user_email` (str): User's email address

**Returns:** Confirmation with changes

#### `batch_modify_gmail_message_labels`
Add or remove labels from multiple messages at once.

**Parameters:**
- `message_ids` (list[str]): List of message IDs
- `add_label_ids` (list[str], optional): Labels to add
- `remove_label_ids` (list[str], optional): Labels to remove
- `user_email` (str): User's email address

**Returns:** Confirmation with changes

**What it exposes to LLM:**
- Efficient batch label operations
- Message organization capabilities

---

## Housekeeping Server

Utility tools for time context and chat history management.

### Testing Tools

#### `test_echo`
Echo a message back for integration testing.

**Parameters:**
- `message` (str): Message to echo
- `uppercase` (bool, default: False): Return uppercased

**Returns:** Dictionary with message and uppercase flag

**What it exposes to LLM:**
- Server connectivity testing
- Basic request/response verification

### Time Context Tools

#### `current_time`
Get the current moment with precise timestamps and timezone information.

**Parameters:**
- `format` (Literal["iso", "unix"], default: "iso"): Output format

**Returns:** Comprehensive time data

**What it exposes to LLM:**
- Current UTC time (ISO 8601 and Unix timestamp)
- Current Eastern Time (ET/EDT) with timezone info
- Human-readable time display
- Timezone offset information
- Context lines for natural language use
- Exact time for scheduling and timing

**Use this tool when:**
- User asks "what time is it?"
- Need current timestamp for calculations
- Creating or scheduling events
- Need timezone conversions

### Chat History Tools

#### `chat_history`
Retrieve stored chat messages for a session with ISO timestamps.

**Parameters:**
- `session_id` (str, optional): Session identifier (auto-injected by orchestrator)
- `limit` (int, default: 20): Maximum messages to return
- `newest_first` (bool, default: False): Reverse chronological order

**Returns:** Message history with metadata

**What it exposes to LLM:**
- Previous conversation turns
- Message timestamps (UTC and Eastern Time)
- Message roles and content
- Parent/child message relationships
- Truncation status for long messages
- Guidance on referencing prior turns

**Use this tool when:**
- Need to reference earlier conversation context
- User asks "what did I say earlier?"
- Need precise timing of prior interactions
- Building on previous discussion topics

---

## PDF & Document Extraction Server

Advanced document intelligence powered by Kreuzberg, with custom enhancements for local file access and URL support.

### Core Extraction Tools

#### `extract_document`
Extract text and data from local files or HTTP(S) URLs.

**Parameters:**
- `file_path` (str): Filesystem path, HTTP URL, or HTTPS URL
- `mime_type` (str, optional): MIME type (auto-detected if not provided)
- `force_ocr` (bool, default: False): Force OCR even if text layer exists
- `chunk_content` (bool, default: False): Split content into chunks
- `extract_tables` (bool, default: False): Extract table structures
- `extract_entities` (bool, default: False): Extract named entities
- `extract_keywords` (bool, default: False): Extract keywords
- `ocr_backend` (str, default: "tesseract"): OCR engine to use
- `max_chars` (int, default: 1000): Max characters per chunk
- `max_overlap` (int, default: 200): Chunk overlap size
- `keyword_count` (int, default: 10): Number of keywords to extract
- `auto_detect_language` (bool, default: False): Auto-detect document language
- `tesseract_lang` (str, optional): Tesseract language code
- `tesseract_psm` (int, optional): Page segmentation mode
- `tesseract_output_format` (str, optional): Output format
- `enable_table_detection` (bool, optional): Enable table detection

**Returns:** Extracted content dictionary

**What it exposes to LLM:**
- Text from PDFs (including scanned documents via OCR)
- Office document text (Word, Excel, PowerPoint)
- Image text via OCR
- Table structures and data
- Named entities (people, places, organizations)
- Keywords and topics
- Support for HTTP(S) URLs (auto-downloads)
- Enhanced local file access for uploads

#### `extract_bytes`
Extract content from base64-encoded document bytes.

**Parameters:** Similar to `extract_document` but takes `content_base64` instead of file path

**Returns:** Extracted content dictionary

**What it exposes to LLM:**
- Same extraction capabilities as `extract_document`
- Works with in-memory content
- No filesystem access required

#### `extract_saved_attachment`
Extract and return text from a previously saved chat attachment.

**Parameters:**
- `attachment_id` (str): Internal attachment ID from upload or Gmail download
- `force_ocr` (bool, default: False): Force OCR
- `chunk_content` (bool, default: False): Split into chunks
- `extract_tables` (bool, default: False): Extract tables
- `extract_entities` (bool, default: False): Extract entities
- `extract_keywords` (bool, default: False): Extract keywords
- `max_chars` (int, default: 1000): Chunk size
- `max_overlap` (int, default: 200): Chunk overlap
- `keyword_count` (int, default: 10): Keyword count
- `auto_detect_language` (bool, default: False): Auto-detect language

**Returns:** Extracted text content (string)

**What it exposes to LLM:**
- Direct access to uploaded/saved attachments
- Automatic lookup by attachment ID
- Text extraction with OCR fallback
- No manual file path resolution needed
- Integration with chat attachment storage

**Use this tool when:**
- User uploaded a file earlier in the conversation
- Need to re-read an attachment
- Attachment ID is available from prior operations

### File Management Tools

#### `list_upload_paths`
List files under the configured uploads directory with metadata.

**Parameters:**
- `subdir` (str, optional): Subdirectory relative to uploads base
- `pattern` (str, optional): Glob or substring filter (e.g., "*.pdf", "invoice")
- `max_results` (int, default: 200): Limit number of results
- `include_dirs` (bool, default: False): Include directories in results

**Returns:** List of file/directory entries with metadata

**What it exposes to LLM:**
- File paths (relative and absolute)
- File sizes and modification times
- MIME types (inferred)
- Original filenames from chat history
- Attachment IDs for saved files
- Session IDs for file associations
- Display/delivery URLs
- Creation and expiration timestamps

**Use this tool when:**
- User asks "what files do I have?"
- Need to find previously uploaded files
- Browse uploads directory
- Search for specific file types

#### `search_upload_paths`
Search for files in uploads by filename or pattern.

**Parameters:**
- `query` (str): Search query (substring or glob pattern)
- `session_id` (str, optional): Limit to specific session subdirectory
- `max_results` (int, default: 100): Maximum results

**Returns:** Matching files with metadata (same as `list_upload_paths`)

**What it exposes to LLM:**
- Fast file search by name
- Session-scoped searches
- Pattern matching support
- Same rich metadata as listing

### Batch Extraction Tools

#### `batch_extract_document`
Extract content from multiple documents in parallel.

**Parameters:** Array of document specifications (same parameters as `extract_document`)

**Returns:** Array of extraction results

#### `batch_extract_bytes`
Extract content from multiple base64-encoded documents in parallel.

**Parameters:** Array of byte specifications (same parameters as `extract_bytes`)

**Returns:** Array of extraction results

### Simple Extraction Tool

#### `extract_simple`
Simplified extraction interface with minimal options.

**Parameters:**
- `file_path` (str): Path or URL to document
- `force_ocr` (bool, default: False): Force OCR

**Returns:** Extracted text content

**What it exposes to LLM:**
- Quick text extraction without complex options
- Good for simple "read this file" use cases

---

## Common Patterns and Best Practices

### Authentication Flow
1. Open the System Settings modal and review the **Google services** card.
2. Click **Connect Google Services** to launch the Google consent popup.
3. Complete the Google authorization flow; the popup closes automatically.
4. Confirm the card reports "Connected" and shows the token expiry timestamp.

### Personal Context Discovery
**Before making recommendations, always call `search_all_tasks` or `user_context_from_tasks`:**
- Use with empty query for general overview
- Use with keywords for specific interests
- This surfaces what the user wants/plans/needs
- Enables personalized, context-aware responses

### File and Attachment Workflows
1. **Gmail → Storage → Extraction:**
   - `search_gmail_messages` to find message
   - `download_gmail_attachment` to save locally
   - `extract_saved_attachment` or `read_gmail_attachment_text` to get content

2. **Direct Upload → Extraction:**
   - File uploaded via API
   - `list_upload_paths` or `search_upload_paths` to find it
   - `extract_saved_attachment` with attachment ID
   - Or `extract_document` with file path

### Calendar and Scheduling
- Use friendly names for calendars ("Mom's calendar" → resolves to actual ID)
- Aggregate queries (no calendar_id) search all configured calendars
- Include `due` parameter when creating scheduled tasks
- Use `user_context_from_tasks` before scheduling to avoid conflicts

### Document Intelligence
- PDFs: Automatic OCR fallback if no text layer
- URLs: Automatically downloaded and processed
- Uploads: Direct access via attachment ID (no path needed)
- Tables/Entities/Keywords: Enable only when needed (processing overhead)

---

## Tool Selection Guidelines

| User Intent | Recommended Tool(s) |
|------------|-------------------|
| "What time is it?" | `current_time` |
| "What did I say earlier?" | `chat_history` |
| "What do I want to read?" | `search_all_tasks` with query="read" |
| "What's on my schedule?" | `calendar_get_events` (no calendar_id) |
| "Create an event..." | `calendar_create_event` |
| "Schedule a task for tomorrow" | `calendar_create_task` with `due` parameter |
| "Find email about..." | `search_gmail_messages` |
| "Read that attachment" | `read_gmail_attachment_text` or `extract_saved_attachment` |
| "What files do I have?" | `list_upload_paths` or `search_upload_paths` |
| "Extract text from..." | `extract_document` or `extract_saved_attachment` |
| "Find file in Drive..." | `gdrive_search_files` |
| "Show me my Drive folder" | `gdrive_list_folder` |

---

## Version Information

**Document Version:** 1.0
**Last Updated:** November 8, 2025
**Backend Version:** FastAPI + MCP Integration
**MCP Protocol:** Model Context Protocol

---

## Notes

- All tools handle authentication errors gracefully with clear instructions
- Most tools support batch operations for efficiency
- File paths can be absolute or relative (resolved safely)
- Timestamps use ISO 8601 format with timezone info
- MIME types are auto-detected when not provided
- Google APIs respect user permissions (read-only where applicable)
