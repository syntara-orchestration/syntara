# Example MCP Server

## Running
`make mcp-start`

## Registering with Syntara

When running Syntara via `docker compose`, register this MCP server using the service name instead of `localhost`:

- **Local development**: `http://localhost:8765/mcp`
- **Docker compose**: `http://mcp-server:8765/mcp`

## Verify operation

### Get an MCP Session ID

Execute the following:
```commandline
curl -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json,text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{"tools":{},"resources":{},"prompts":{}},"clientInfo":{"name":"test-client","version":"1.0.0"}}}' \
  -v 2>&1 | grep -i "mcp-session-id"
```
The response will look like this:
```commandline
< mcp-session-id: 460e1046d6bb469ab5d11fc9beaef681
```
`MCP-SESSION-ID` will be `460e1046d6bb469ab5d11fc9beaef681`.

### Signal initialisation is complete
```commandline
curl -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json,text/event-stream" \
  -H "Mcp-Session-Id: <MCP-SESSION-ID>" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
```  

### List MCP Tools provided by MCP Server
```commandline
curl -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json,text/event-stream" \
  -H "Mcp-Session-Id: <MCP-SESSION-ID>" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
```
