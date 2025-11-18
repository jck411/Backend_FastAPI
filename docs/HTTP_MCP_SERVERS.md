# HTTP MCP Servers Configuration Guide

This document explains how to configure and use HTTP/SSE-based MCP servers in addition to the standard Python module-based servers.

## Overview

The MCP client supports three transport methods:

1. **Python Module** - Launch MCP server as a Python module (default)
2. **Custom Command** - Launch MCP server with arbitrary command
3. **HTTP/SSE** - Connect to remote HTTP MCP server via Server-Sent Events

HTTP transport is ideal for:
- Remote MCP servers running on different machines
- Containerized MCP services
- Third-party MCP server providers
- Development/testing against remote servers
- MCP servers written in languages other than Python

## Configuration

### Basic HTTP Server Configuration

Add an HTTP server to your `data/mcp_servers.json`:

```json
{
  "servers": [
    {
      "id": "remote-mcp-server",
      "http_url": "http://localhost:8080/mcp",
      "enabled": true
    }
  ]
}
```

### HTTP Server with Tool Prefix

To avoid tool name conflicts, add a prefix:

```json
{
  "servers": [
    {
      "id": "external-api",
      "http_url": "https://api.example.com/mcp",
      "tool_prefix": "external",
      "enabled": true
    }
  ]
}
```

Tools from this server will be prefixed: `external__tool_name`

### HTTP Server with Context Filtering

Assign contexts to HTTP servers for selective tool exposure:

```json
{
  "servers": [
    {
      "id": "email-service",
      "http_url": "https://email.service.com/mcp",
      "contexts": ["email", "communication"],
      "enabled": true,
      "tool_overrides": {
        "send_urgent": {
          "contexts": ["urgent", "email"]
        }
      }
    }
  ]
}
```

### Complete HTTP Server Configuration

```json
{
  "servers": [
    {
      "id": "production-mcp-api",
      "http_url": "https://mcp.example.com/api/v1/mcp",
      "enabled": true,
      "tool_prefix": "prod",
      "contexts": ["external", "api"],
      "disabled_tools": ["deprecated_tool"],
      "tool_overrides": {
        "special_tool": {
          "contexts": ["admin"]
        }
      }
    }
  ]
}
```

## Connection Behavior

### Timeouts

HTTP connections have a **30-second timeout** by default:

```python
# Configured in mcp_client.py
HTTP_CONNECTION_TIMEOUT = 30.0  # seconds
```

If a connection takes longer than 30 seconds, it will fail with a timeout error.

### Reconnection Logic

HTTP servers support automatic reconnection (unlike subprocess-based servers):

- **Max Attempts**: 3 reconnection attempts
- **Delay**: 2 seconds between attempts
- **Reset**: Counter resets after successful connection

```python
# Configuration constants
HTTP_MAX_RECONNECT_ATTEMPTS = 3
HTTP_RECONNECT_DELAY = 2.0  # seconds
```

### Automatic Reconnection

The client will automatically attempt to reconnect when:

```python
# Programmatic reconnection
success = await mcp_client.reconnect()
if success:
    print("Reconnected successfully")
else:
    print("Reconnection failed")
```

## Error Handling

### DNS Resolution Failures

**Error**: `DNS resolution failed for HTTP MCP server (check hostname)`

**Causes**:
- Invalid hostname
- DNS server unreachable
- Network connectivity issues

**Solutions**:
- Verify hostname is correct
- Check network connectivity
- Try using IP address instead of hostname
- Verify DNS server is accessible

### Connection Refused

**Error**: `Connection refused by HTTP MCP server (check if server is running)`

**Causes**:
- Server is not running
- Wrong port number
- Firewall blocking connection
- Server crashed or restarting

**Solutions**:
- Verify server is running: `curl http://localhost:8080/mcp`
- Check correct port is configured
- Review server logs for errors
- Check firewall rules

### Timeout Errors

**Error**: `Connection to HTTP MCP server timed out after 30s`

**Causes**:
- Server is slow to respond
- Network latency issues
- Server is overloaded
- Incorrect URL path

**Solutions**:
- Check server health and performance
- Verify URL path is correct (usually `/mcp`)
- Review network latency
- Check server logs for processing delays

### Authentication Errors

**Error**: `HTTP MCP server requires authentication (401 Unauthorized)`

**Causes**:
- Missing authentication headers
- Invalid credentials
- Expired tokens

**Solutions**:
- Future: Authentication support will be added via `env` configuration
- Contact server administrator for credentials
- Verify authentication method required

**Error**: `HTTP MCP server access forbidden (403 Forbidden)`

**Solutions**:
- Verify your account has proper permissions
- Contact server administrator

### Not Found Errors

**Error**: `HTTP MCP server endpoint not found (404 Not Found)`

**Causes**:
- Incorrect URL path
- Server routing misconfiguration
- API version mismatch

**Solutions**:
- Verify endpoint path (standard is `/mcp`)
- Check server documentation for correct path
- Ensure server is properly configured

### Server Errors

**Error**: `HTTP MCP server internal error (500)`

**Causes**:
- Server-side bug
- Server misconfiguration
- Resource exhaustion

**Solutions**:
- Check server logs
- Contact server administrator
- Report issue to server maintainer

### Invalid SSE Stream Format

**Error**: `Invalid SSE stream format from HTTP MCP server`

**Causes**:
- Server not implementing SSE correctly
- Network proxy interfering with stream
- Server version incompatibility

**Solutions**:
- Verify server implements MCP SSE protocol correctly
- Check for network proxies that might buffer SSE
- Ensure MCP protocol version compatibility

## Testing HTTP Servers

### Using MCP Inspector

Test HTTP servers with the official MCP Inspector:

```bash
# Interactive UI mode
npx @modelcontextprotocol/inspector --http http://localhost:8080/mcp

# CLI mode - list tools
npx @modelcontextprotocol/inspector --cli --http http://localhost:8080/mcp \
  --method tools/list

# CLI mode - call tool
npx @modelcontextprotocol/inspector --cli --http http://localhost:8080/mcp \
  --method tools/call \
  --tool-name test_tool \
  --tool-arg param=value
```

### Using cURL

Test basic connectivity:

```bash
# Test endpoint is reachable
curl -v http://localhost:8080/mcp

# Test SSE connection (should keep connection open)
curl -N -H "Accept: text/event-stream" http://localhost:8080/mcp
```

### Health Check

Verify server is responding:

```bash
# Should return SSE stream
curl -N \
  -H "Accept: text/event-stream" \
  -H "Content-Type: application/json" \
  http://localhost:8080/mcp
```

## Mixed Server Configurations

You can combine HTTP, module, and command-based servers:

```json
{
  "servers": [
    {
      "id": "local-calendar",
      "module": "backend.mcp_servers.calendar_server",
      "enabled": true,
      "contexts": ["calendar"]
    },
    {
      "id": "remote-email",
      "http_url": "https://email-mcp.example.com/mcp",
      "enabled": true,
      "contexts": ["email"]
    },
    {
      "id": "custom-processor",
      "command": ["node", "/path/to/mcp-server.js"],
      "enabled": true,
      "contexts": ["processing"]
    }
  ]
}
```

## Best Practices

### 1. Use Descriptive Server IDs

```json
{
  "id": "production-email-service",  // Good: clear purpose
  "id": "server1"                     // Bad: unclear
}
```

### 2. Configure Tool Prefixes for Third-Party Servers

```json
{
  "id": "external-api",
  "http_url": "https://api.example.com/mcp",
  "tool_prefix": "external"  // Prevents naming conflicts
}
```

### 3. Use Contexts for Organization

```json
{
  "id": "communication-hub",
  "http_url": "https://comm.example.com/mcp",
  "contexts": ["email", "slack", "teams"]
}
```

### 4. Disable Unused Tools

```json
{
  "id": "multi-service-api",
  "http_url": "https://api.example.com/mcp",
  "disabled_tools": ["deprecated_tool", "beta_feature"]
}
```

### 5. Monitor Connection Status

Check active servers programmatically:

```python
from backend.chat.mcp_registry import MCPToolAggregator

# Get active server list
active = aggregator.active_servers()
if "remote-server" not in active:
    logger.warning("Remote server failed to connect")
```

### 6. Handle Connection Failures Gracefully

```python
# Connection failures don't crash aggregator
await aggregator.connect()  # Logs errors, continues

# Check which servers connected
servers = aggregator.describe_servers()
for server in servers:
    if not server["connected"]:
        logger.error(f"Server {server['id']} failed to connect")
```

## Security Considerations

### Current Limitations

- **No Authentication**: HTTP transport currently doesn't support authentication headers
- **No TLS Verification**: Certificate validation follows httpx defaults

### Planned Features

Future versions will support:

```json
{
  "id": "secure-server",
  "http_url": "https://secure.example.com/mcp",
  "env": {
    "AUTH_TOKEN": "${MCP_AUTH_TOKEN}",
    "API_KEY": "${API_KEY}"
  }
}
```

### Recommendations

1. **Use HTTPS**: Always use `https://` URLs for production
2. **Network Security**: Place HTTP MCP servers behind VPN or firewall
3. **Access Control**: Use network-level access control until auth is implemented
4. **Monitor Access**: Log all HTTP MCP server connections

## Troubleshooting

### Server Not Connecting

1. Check server is running:
   ```bash
   curl http://localhost:8080/mcp
   ```

2. Review logs:
   ```bash
   tail -f logs/app/$(date +%Y-%m-%d)/backend.log
   ```

3. Verify configuration:
   ```python
   from backend.chat.mcp_registry import load_server_configs
   configs = load_server_configs(Path("data/mcp_servers.json"))
   for cfg in configs:
       if cfg.http_url:
           print(f"{cfg.id}: {cfg.http_url} (enabled={cfg.enabled})")
   ```

### Tools Not Appearing

1. Check server is in active list:
   ```python
   print(aggregator.active_servers())
   ```

2. List tools from server:
   ```python
   tools = aggregator.get_openai_tools()
   for tool in tools:
       print(tool["function"]["name"])
   ```

3. Check tool filtering:
   ```python
   servers = aggregator.describe_servers()
   for server in servers:
       if server["id"] == "your-server":
           print(f"Disabled tools: {server['disabled_tools']}")
           print(f"Active tools: {server['tools']}")
   ```

### Performance Issues

1. **Check timeout**: Increase if server is legitimately slow
2. **Monitor latency**: HTTP adds network overhead vs local servers
3. **Check server load**: Remote server might be overloaded
4. **Use connection pooling**: Handled automatically by httpx

## Examples

### Local Development Server

```json
{
  "id": "dev-mcp",
  "http_url": "http://localhost:3000/mcp",
  "enabled": true,
  "tool_prefix": "dev"
}
```

### Production API

```json
{
  "id": "prod-api",
  "http_url": "https://mcp.production.example.com/mcp",
  "enabled": true,
  "contexts": ["external", "production"],
  "tool_prefix": "api"
}
```

### Docker Container

```json
{
  "id": "containerized-service",
  "http_url": "http://mcp-service:8080/mcp",
  "enabled": true,
  "contexts": ["container"]
}
```

### Multi-Region Setup

```json
{
  "servers": [
    {
      "id": "us-east-mcp",
      "http_url": "https://us-east.mcp.example.com/mcp",
      "enabled": true,
      "tool_prefix": "useast",
      "contexts": ["us", "east"]
    },
    {
      "id": "eu-west-mcp",
      "http_url": "https://eu-west.mcp.example.com/mcp",
      "enabled": true,
      "tool_prefix": "euwest",
      "contexts": ["eu", "west"]
    }
  ]
}
```

## Related Documentation

- [MCP Tools Reference](./MCP_TOOLS_REFERENCE.md) - Overview of available MCP tools
- [How MCP Tools Work](./HOW_MCP_TOOLS_WORK.md) - Understanding MCP tool mechanics
- [MCP Protocol Specification](https://modelcontextprotocol.io/) - Official MCP documentation

## Version Information

**Document Version:** 1.0
**Last Updated:** November 17, 2025
**Feature Status:** Production Ready
**Python Version:** 3.11+
