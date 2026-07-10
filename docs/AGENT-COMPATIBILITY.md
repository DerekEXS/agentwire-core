# Agent Compatibility Guide

> **v2.1.0+** — This document describes the compatibility layer built into AgentWire CORE v2.1.0+.

## A2A Protocol Format

AgentWire CORE implements the A2A protocol using protobuf messages. The standard format for a `SendMessage` request:

```json
{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "params": {
    "message": {
      "role": "ROLE_AGENT",        // or ROLE_USER; must be integer or exact string
      "parts": [{"text": "..."}],  // Part fields: text, raw, url, data, metadata, filename, mediaType
      "message_id": "optional"     // auto-generated if absent
    }
  },
  "id": "1"
}
```

## Known Compatibility Issues

### 1. Role Format

**Problem:** Some agents send `role` as a lowercase string (`"agent"`, `"user"`) or an incorrect string (`"ROLE_AGENT"` works but `"agent"` does not).

**Fix (v2.1.0+):** CORE normalizes role strings:
- `"ROLE_AGENT"` / `"agent"` → `2` (ROLE_AGENT)
- `"ROLE_USER"` / `"user"` → `1` (ROLE_USER)
- `"ROLE_UNSPECIFIED"` / `"unspecified"` → `0`

**Before v2.1.0:** Only exact `"ROLE_AGENT"` / `"ROLE_USER"` strings were accepted.

### 2. Parts without `kind` field

**Problem:** The A2A protobuf `Part` type does NOT have a `kind` discriminator field. Part union types are encoded as direct field names (`text`, `raw`, `url`, `data`).

**Do NOT send:**
```json
{"parts": [{"kind": "text", "text": "hello"}]}  // 'kind' is not a valid Part field
```

**DO send:**
```json
{"parts": [{"text": "hello"}]}                   // direct field, no kind wrapper
```

CORE v2.1.0 passes parts through unchanged — it does NOT add `kind` fields.

### 3. Missing `message_id`

**Problem:** `SendMessageRequest.message.message_id` is required by the protobuf schema.

**Fix (v2.1.0+):** CORE auto-generates a UUID `message_id` if none is provided.

**Before v2.1.0:** Requests without `message_id` were rejected with `-32602 Invalid params`.

## Agent Integration Checklist

When integrating a new agent with AgentWire CORE:

- [ ] `role` is either an integer (0/1/2) or an exact string (`"ROLE_AGENT"`, `"ROLE_USER"`)
- [ ] `parts` use direct field names (`text`, `raw`, `url`, `data`), NOT `kind` wrappers
- [ ] `message_id` is provided, or rely on auto-generation (v2.1.0+)
- [ ] `jsonrpc` is exactly `"2.0"`
- [ ] `Content-Type: application/json` header is set
- [ ] `Authorization: Bearer <token>` header is set (unless auth is disabled)

## Method Names

| Method | Notes |
|--------|-------|
| `SendMessage` | PascalCase, standard A2A. Use `ROLE_AGENT` for agent-to-agent messages. |
| `GetTask` | Query task status by ID |
| `ListTasks` | Paginated task list |
| `CancelTask` | Cancel a running task |
| `SendStreamingMessage` | SSE streaming variant |

## Testing

```bash
# Test with correct format
curl -X POST http://localhost:18800/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"jsonrpc":"2.0","method":"SendMessage","id":"test","params":{"message":{"role":"ROLE_AGENT","parts":[{"text":"hello"}]}}}'

# Should return 200 with JSON-RPC result (or valid error like task not found)
```
