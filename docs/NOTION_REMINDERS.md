# Using Notion MCP Server for Reminders and Memory

The Notion MCP server provides enhanced tool descriptions to help you store and retrieve information like names, reminders, and notes. This guide shows how the LLM will use these tools to help you remember things.

## Overview

The Notion MCP server provides 5 main tools for managing your reminders and memory:

1. **notion_search** - Find previously saved information
2. **notion_retrieve_page** - Read detailed content from a note
3. **notion_create_page** - Create new reminder notes
4. **notion_append_block_children** - Add to existing notes
5. **notion_update_block** - Update existing content

## Common Use Cases

### 1. Remembering Names

**Creating a names note:**
When you meet someone new and want to remember them, the LLM will:
- Create a page titled "Names to Remember" using `notion_create_page`
- Add the person's name and context (where you met, what they do, etc.)

**Finding names later:**
When you need to recall a name, the LLM will:
- Search for "names to remember" using `notion_search`
- Return all the names you've saved with their context

**Adding more names:**
When you meet additional people, the LLM will:
- Use `notion_search` to find your existing "Names to Remember" page
- Use `notion_append_block_children` to add the new name to that page

**Example interaction:**
```
User: "I just met John Smith at the tech conference. Can you help me remember him?"

LLM will:
1. Search for existing "names to remember" note
2. If found, append "John Smith - met at tech conference"
3. If not found, create new "Names to Remember" page with this entry

User: "What was the name of the person I met at the tech conference?"

LLM will:
1. Search "names to remember"
2. Retrieve the page content
3. Find and return "John Smith - met at tech conference"
```

### 2. Storing Project Ideas

**Creating an ideas collection:**
```
User: "Save this project idea: Build a task manager with AI features"

LLM will:
1. Search for "project ideas" note
2. Create one if it doesn't exist
3. Add the new idea to the page
```

### 3. Reading Lists and Shopping Lists

**Managing lists:**
```
User: "Add 'Atomic Habits' to my reading list"

LLM will:
1. Search for "books to read" or "reading list"
2. Use notion_append_block_children to add the book
3. Confirm the addition

User: "What books are on my reading list?"

LLM will:
1. Search for the reading list
2. Retrieve and display all book titles
```

### 4. Task and Todo Reminders

**Creating reminders:**
```
User: "Remind me to buy milk and eggs"

LLM will:
1. Search for "shopping list" or "things to buy"
2. Create the note if needed
3. Add milk and eggs as items
```

## How It Works

### Tool Descriptions Guide the LLM

Each tool now has descriptions that emphasize reminder and memory use cases:

- **notion_search** explicitly mentions searching for "names to remember", "project ideas", etc.
- **notion_create_page** shows examples like creating "Names to Remember" pages
- **notion_append_block_children** demonstrates adding names to existing notes
- **notion_update_block** shows updating entries with more context

These descriptions help the LLM understand when and how to use each tool for memory-related tasks.

### The Search-First Pattern

The LLM will typically follow this pattern:

1. **Search first**: Look for existing relevant notes
2. **Create if missing**: Make a new note if one doesn't exist
3. **Append for additions**: Add to existing notes rather than creating duplicates
4. **Update for corrections**: Modify existing entries when needed

## Setup Requirements

To use the Notion MCP server, you need:

1. A Notion integration token set in your environment:
   ```bash
   NOTION_TOKEN=notion_secret_xxx
   # or
   NOTION_API_KEY=notion_secret_xxx
   ```

2. (Optional) Default parent page or database:
   ```bash
   NOTION_PAGE_ID=<your-default-page-id>
   # or
   NOTION_DATABASE_ID=<your-default-database-id>
   ```

3. Share the pages/databases with your Notion integration

## Benefits

With these optimized tool descriptions:

- The LLM naturally understands to use Notion for storing information
- Searches are contextual ("names to remember" vs generic "John")
- Notes are organized by topic (names, ideas, tasks, etc.)
- Information is easy to retrieve later
- The system prevents duplicate notes through search-first pattern

## Technical Details

The tool descriptions include:

- **Concrete examples** of common use cases
- **Action-oriented language** ("search for names", "add to your list")
- **Context about when to use each tool**
- **Guidance on the typical workflow** (search → create → append → update)

This guides the LLM to use the tools appropriately without requiring explicit instructions from the user.
