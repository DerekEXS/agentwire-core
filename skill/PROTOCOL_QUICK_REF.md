# AgentWire A2A v1.0.1 — Protocol Quick Reference

> Compact reference for AgentWire's JSON-RPC and HTTP surface.
> For full context, see [SKILL.md](SKILL.md).

## A2A Protocol Version

- **AgentWire implements**: A2A **v1.0.1** (per <https://a2a-protocol.org/latest/specification/>)
- **JSON-RPC transport**: 2.0
- **Content type**: `application/json`
- **Default port**: `18800`

## Authentication

All non-loopback requests **MUST** carry a Bearer token in the `Authorization` header.

```
Authorization: Bearer <token>
```

Token resolution order on the server:

1. `--token` CLI argument
2. `--token-file` file (UTF-8 with BOM auto-strip)
3. `AGENTWIRE_TOKEN` environment variable
4. Empty = loopback-only (server fails-fast on non-loopback + empty token)

Loopback (127.0.0.1, ::1) requests are allowed without a token (handy for local CUE host).

## HTTP Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/.well-known/agent.json` | Optional | Agent Card discovery (v1.4.3+; v1.4.2 routing bug) |
| GET | `/health` | None | Liveness probe (v1.4.3+) |
| GET | `/a2a/metrics` | Required | Task counters |
| POST | `/a2a/jsonrpc` | Required | JSON-RPC 2.0 endpoint (v1.4.3+; v1.4.2 routing bug) |
| POST | `/a2a/rest/message/send` | Required | REST wrapper around `message/send` |
| GET | `/redact/patterns` | Required | Shared redaction regex catalog (v1.4.3+) |

## JSON-RPC Methods

### `message/send`

Send a message to the gateway. The gateway stores the task and returns a task ID.

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "method": "message/send",
  "params": {
    "contextId": "ctx-abc",
    "message": {
      "messageId": "msg-001",
      "role": "user",
      "parts": [
        {"type": "text", "text": "Hello, agent"}
      ]
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-1",
  "result": {
    "kind": "task",
    "id": "task-uuid",
    "contextId": "ctx-abc",
    "status": {"state": "completed"},
    "message": {
      "messageId": "msg-uuid",
      "role": "agent",
      "parts": [{"type": "text", "text": "..."}]
    }
  }
}
```

### `tasks/get`

```json
{"jsonrpc": "2.0", "id": "req-2", "method": "tasks/get", "params": {"taskId": "task-uuid"}}
```

### `tasks/list`

```json
{"jsonrpc": "2.0", "id": "req-3", "method": "tasks/list", "params": {}}
```

### `tasks/cancel`

```json
{"jsonrpc": "2.0", "id": "req-4", "method": "tasks/cancel", "params": {"taskId": "task-uuid"}}
```

### `tasks/subscribe` (v1.4.3+, reserved)

```json
{"jsonrpc": "2.0", "id": "req-5", "method": "tasks/subscribe", "params": {"taskId": "task-uuid"}}
```

### `agent/getCard` (v1.4.3+)

```json
{"jsonrpc": "2.0", "id": "req-6", "method": "agent/getCard", "params": {}}
```

### `messages/list` (v1.4.3 new)

List recent messages for one or all peers.

```json
{
  "jsonrpc": "2.0",
  "id": "req-10",
  "method": "messages/list",
  "params": {
    "peer_uuid": "a3f29e1c-...",  // optional, omit for all peers
    "since_round": 38,             // optional
    "limit": 5                     // default 5, max 100
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-10",
  "result": {
    "peer_uuid": "a3f29e1c-...",
    "peer_name": "初梦",
    "first_round": 1,
    "last_round": 42,
    "total_rounds": 42,
    "messages": [
      {"round": 38, "ts": "...", "role": "outbound", "msg_id": "...", "parts": [...]},
      {"round": 38, "ts": "...", "role": "inbound",  "msg_id": "...", "parts": [...]}
    ]
  }
}
```

### `messages/get` (v1.4.3 new)

```json
{"jsonrpc": "2.0", "id": "req-11", "method": "messages/get", "params": {"peer_uuid": "...", "round": 38}}
```

### `messages/peers` (v1.4.3 new)

```json
{"jsonrpc": "2.0", "id": "req-12", "method": "messages/peers", "params": {}}
```

**Response**:
```json
{
  "result": {
    "peers": [
      {"uuid": "a3f29e1c", "name": "初梦", "last_round": 42, "total_rounds": 42, "last_ts": "..."},
      {"uuid": "f8d2a0b1", "name": "Pawly", "last_round": 17, "total_rounds": 17, "last_ts": "..."}
    ]
  }
}
```

### `messages/export` (v1.4.3 new)

```json
{"jsonrpc": "2.0", "id": "req-13", "method": "messages/export", "params": {"peer_uuid": "...", "format": "markdown"}}
```

**Response** (string payload):
```json
{"result": {"format": "markdown", "content": "# Conversation with 初梦\n\n[Round 1] ..."}}
```

## REST `POST /a2a/rest/message/send`

Equivalent to `message/send` JSON-RPC, but without JSON-RPC envelope:

```http
POST /a2a/rest/message/send HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{"message": {"parts": [{"type": "text", "text": "Hello"}]}, "contextId": "ctx-1"}
```

Response is the same `result` object from JSON-RPC, returned directly.

## History configuration (v1.4.3)

```yaml
# server/config.yaml
history:
  enabled: true               # total switch
  max_rounds_per_peer: 0      # 0 = unlimited (default), >0 = FIFO cap
  context_rounds: 5           # inject last N rounds as metadata; 0 = off
  storage_dir: ~/.local/share/agentwire/history
  redact_sensitive: true      # apply patterns from /redact/patterns
  round_close:
    mode: heuristic           # heuristic | explicit
    heuristic_idle_seconds: 300
```

## Standard JSON-RPC error codes

| Code | Meaning |
|------|---------|
| -32700 | Parse error (invalid JSON) |
| -32600 | Invalid request / Unauthorized |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |

## A2A Part types

A2A v1.0.1 supports these `parts[].type` values:

- `text` — `{"type": "text", "text": "..."}`
- `file` — `{"type": "file", "file": {"name": "...", "mimeType": "...", "uri": "..."}}`
- `data` — `{"type": "data", "data": {...}}` (JSON-LD friendly)

## Agent Card fields (v1.4.3+)

```json
{
  "protocolVersion": "1.0.1",
  "name": "AgentWire",
  "description": "...",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "extendedAgentCard": false
  },
  "skills": [],
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"]
}
```

## See also

- [SKILL.md](SKILL.md) — full guide
- [INTEGRATION_Generic.md](INTEGRATION_Generic.md) — generic client examples
- A2A v1.0.1 spec: <https://a2a-protocol.org/latest/specification/>
- JSON-RPC 2.0 spec: <https://www.jsonrpc.org/specification>
