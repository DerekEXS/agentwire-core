# AgentWire A2A v1.0.1 — Protocol Quick Reference (v1.5.2)

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

Token resolution order on the server (highest priority first):

1. `--token` CLI argument
2. `--token-file` file (UTF-8 with BOM auto-strip, defaults to `AGENTWIRE_TOKEN_FILE` env)
3. `AGENTWIRE_TOKEN` environment variable
4. Empty = loopback-only (server fails-fast on non-loopback + empty token)

Loopback (127.0.0.1, ::1) requests are allowed without a token.

Startup token-health diagnostics (v1.4.8) warn on UTF-8 BOM, CRLF line endings, and overly broad file permissions — without blocking startup.

## HTTP Endpoints

| Method | Path | Auth | Auth Since | Purpose |
|--------|------|------|------------|---------|
| GET | `/.well-known/agent.json` | None | — | Agent Card discovery |
| GET | `/health` | None | — | Liveness probe |
| GET | `/a2a/metrics` | Bearer | v1.5.2 | Task counters |
| POST | `/a2a/jsonrpc` | Bearer | v1.0 | JSON-RPC 2.0 endpoint |
| POST | `/a2a/rest/message/send` | Bearer | v1.0 | REST wrapper |
| GET | `/redact/patterns` | Bearer | v1.4.3 | Shared redaction regex catalog |

## JSON-RPC Methods

### `message/send`

**Request**:
```json
{
  "jsonrpc": "2.0", "id": "req-1", "method": "message/send",
  "params": {
    "contextId": "ctx-abc",
    "message": {
      "messageId": "msg-001", "role": "user",
      "parts": [{"type": "text", "text": "Hello, agent"}]
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0", "id": "req-1",
  "result": {
    "kind": "task", "id": "task-uuid", "contextId": "ctx-abc",
    "status": {"state": "completed"},
    "message": {
      "messageId": "msg-uuid", "role": "agent",
      "parts": [{"type": "text", "text": "AgentWire 回复: 消息已接收"}]
    }
  }
}
```

> v1.5.1: Reply no longer echoes the sender's text; message content is never logged in plaintext.

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

### `tasks/subscribe` (reserved)

```json
{"jsonrpc": "2.0", "id": "req-5", "method": "tasks/subscribe", "params": {"taskId": "task-uuid"}}
```

### `agent/getCard`

```json
{"jsonrpc": "2.0", "id": "req-6", "method": "agent/getCard", "params": {}}
```

### `messages/list`

List recent messages for one or all peers.

```json
{
  "jsonrpc": "2.0", "id": "req-10", "method": "messages/list",
  "params": {
    "peer_uuid": "a3f29e1c-...",
    "since_round": 38,
    "limit": 5
  }
}
```

**Response**: same envelope with `peer_uuid`, `peer_name`, `first_round`, `last_round`, `total_rounds`, and a `messages` array.

### `messages/get`

```json
{"jsonrpc": "2.0", "id": "req-11", "method": "messages/get", "params": {"peer_uuid": "...", "round": 38}}
```

### `messages/peers`

```json
{"jsonrpc": "2.0", "id": "req-12", "method": "messages/peers", "params": {}}
```

**Response**:
```json
{"result": {"peers": [
  {"uuid": "a3f29e1c", "name": "初梦", "last_round": 42, "total_rounds": 42, "last_ts": "..."}
]}}
```

### `messages/export`

Export a peer's history. Pagination added in v1.5.1.

```json
{
  "jsonrpc": "2.0", "id": "req-13", "method": "messages/export",
  "params": {
    "peer_uuid": "...",
    "format": "jsonl",
    "limit": 50,
    "offset": 0
  }
}
```

**Response**:
```json
{
  "result": {
    "format": "jsonl", "content": "{...}\n{...}\n",
    "limit": 50, "offset": 0,
    "total_count": 142, "has_more": true
  }
}
```

- `limit`: 1..200 (default 50, via `EXPORT_MAX_LIMIT` env)
- `offset`: 0-based
- `has_more`: true when there are more messages beyond this page

### `messages/import` (v1.4.8)

Append externally-sourced messages into a peer history. Server assigns round numbers, timestamps, and message ids.

```json
{
  "jsonrpc": "2.0", "id": "req-14", "method": "messages/import",
  "params": {
    "peer_uuid": "pawly-demo-uuid",
    "messages": [
      {
        "role": "inbound",
        "parts": [{"type": "text", "text": "urgent: review needed"}],
        "metadata": {"source": "import-script"}
      }
    ]
  }
}
```

**Response**:
```json
{
  "result": {
    "imported": 1, "peer_uuid": "pawly-demo-uuid",
    "first_round": 1, "last_round": 1
  }
}
```

**Limits** (v1.5.1):
- Max messages per request: 100 (hard cap 500 via `IMPORT_MAX_MESSAGES`)
- Max text part size: 64KB (hard cap 256KB via `IMPORT_MAX_MESSAGE_SIZE`)
- Exceeding returns JSON-RPC `-32602 Invalid params`

## REST `POST /a2a/rest/message/send`

```http
POST /a2a/rest/message/send HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{"message": {"parts": [{"type": "text", "text": "Hello"}]}, "contextId": "ctx-1"}
```

Response is the same `result` object from JSON-RPC, returned directly.

## History configuration

```yaml
# server/config.yaml
history:
  enabled: true
  max_rounds_per_peer: 0      # 0 = unlimited, >0 = FIFO cap
  context_rounds: 5           # inject last N rounds as metadata; 0 = off
  storage_dir: ~/.local/share/agentwire/history
  redact_sensitive: true
  round_close:
    mode: heuristic
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

- `text` — `{"type": "text", "text": "..."}`
- `file` — `{"type": "file", "file": {"name": "...", "mimeType": "...", "uri": "..."}}`
- `data` — `{"type": "data", "data": {...}}`

## Agent Card fields

```json
{
  "protocolVersion": "1.0.1",
  "name": "AgentWire", "version": "1.5.2",
  "description": "AgentWire A2A v1.0.1 Service",
  "capabilities": {"streaming": true, "pushNotifications": false, "extendedAgentCard": false},
  "skills": [],
  "defaultInputModes": ["text"], "defaultOutputModes": ["text"]
}
```

## See also

- [SKILL.md](SKILL.md) — full guide
- [INTEGRATION_Generic.md](INTEGRATION_Generic.md) — generic client examples
- A2A v1.0.1 spec: <https://a2a-protocol.org/latest/specification/>
- JSON-RPC 2.0 spec: <https://www.jsonrpc.org/specification>

---

## End-to-end curl walkthrough

Copy-pasteable flow from **zero** to a working A2A session.

### Setup

```bash
# Docker compose (recommended)
cd agentwire_cue
mkdir -p secrets
printf '%s\n' 'demo-token-xyz' > secrets/a2a-token.txt
printf '%s\n' 'demo-admin-token' > secrets/cue-admin-token.txt
chmod 600 secrets/*.txt
docker compose up -d
```

### Step 1: discover

```bash
curl -s http://127.0.0.1:18800/.well-known/agent.json | jq
```

### Step 2: send a message

```bash
curl -s -X POST http://127.0.0.1:18800/a2a/rest/message/send \
  -H "Authorization: Bearer demo-token-xyz" \
  -H "Content-Type: application/json" \
  -d '{"contextId":"demo-ctx-001","message":{"parts":[{"type":"text","text":"Hello, world!"}]}}' | jq
```

### Step 3: check metrics (requires auth since v1.5.2)

```bash
curl -s -H "Authorization: Bearer demo-token-xyz" \
  http://127.0.0.1:18800/a2a/metrics | jq
```

### Step 4: import external history

```bash
curl -s -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer demo-token-xyz" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":"1","method":"messages/import",
    "params":{
      "peer_uuid":"pawly-demo-uuid",
      "messages":[{"role":"inbound","parts":[{"type":"text","text":"urgent: video script has typo"}],"metadata":{"source":"import"}}]
    }
  }' | jq
```

### Step 5: list all peers

```bash
curl -s -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer demo-token-xyz" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"2","method":"messages/peers","params":{}}' | jq
```

### Step 6: pull paginated history

```bash
curl -s -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer demo-token-xyz" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"3","method":"messages/list","params":{"limit":5}}' | jq
```

### Step 7: export paginated

```bash
curl -s -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer demo-token-xyz" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"4","method":"messages/export","params":{"peer_uuid":"pawly-demo-uuid","format":"markdown","limit":50,"offset":0}}' | jq -r .result.content
```

### Teardown

```bash
docker compose down
```
