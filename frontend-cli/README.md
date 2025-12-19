# Shell Chat CLI

A rich terminal client for Backend_FastAPI that provides the same chat capabilities as the web frontends.

## Features

- **Streaming responses** via Server-Sent Events (SSE)
- **Session persistence** - conversations are cached locally
- **Preset management** - switch between different configurations
- **MCP tool control** - enable/disable MCP servers on the fly
- **Rich markdown rendering** in the terminal

## Usage

```bash
# Connect to localhost:8000 (default)
shell-chat

# Connect to a remote server
shell-chat --server http://pi:8000

# Apply a preset on startup
shell-chat --preset coding
```

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/clear` | Clear session (start new conversation) |
| `/model` | Show current model |
| `/model <id>` | Set model (e.g., `/model anthropic/claude-3-opus`) |
| `/presets` | List available presets |
| `/preset <name>` | Apply a preset |
| `/tools` | List MCP servers and status |
| `/tools <name> on` | Enable an MCP server |
| `/tools <name> off` | Disable an MCP server |
| `/system` | Show system prompt |
| `/quit` | Exit shell-chat |

## Shortcuts

- `Ctrl+C` - Cancel current request
- `Ctrl+D` - Exit shell-chat

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SHELLCHAT_SERVER` | Default server URL (alternative to `--server` flag) |

## Client Settings

The CLI uses the unified client settings API at `/api/clients/cli/`. Settings are stored on the backend in:

```
src/backend/data/clients/cli/
├── llm.json      # LLM configuration
└── presets.json  # Preset configurations
```
