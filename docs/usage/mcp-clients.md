# Connecting MCP clients

The MCP server runs on `http://localhost:8001/mcp` (Streamable HTTP).

## opencode

Add a remote MCP server to your `opencode.json`:

```json
{
  "mcp": {
    "taskowl": {
      "type": "remote",
      "url": "http://localhost:8001/mcp",
      "enabled": true,
      "oauth": false
    }
  }
}
```

## Other MCP clients

Point your MCP client at the Streamable HTTP endpoint `http://localhost:8001/mcp`.
If authentication is enabled, send the taskowl API key as
`Authorization: Bearer <key>` with each request.