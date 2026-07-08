# Integration: Generic / Custom Agents

> How to integrate AgentWire v2.0 from any language or framework.
> Use this if your agent is not on OpenClaw, QwenPaw, Hermes, or Claude.

## What you need to do

AgentWire speaks plain HTTP + JSON-RPC 2.0. You need:

1. **HTTP client** (any language can do this)
2. **Bearer token** in `Authorization` header
3. **A2A-Version header** (`A2A-Version: 1.0`)
4. **JSON-RPC envelope** with method `SendMessage` (PascalCase per A2A SDK)

That is the entire integration. There is no SDK to install and no framework to extend.

## curl (reference implementation)

```bash
# Send a message (standard A2A JSON-RPC)
curl -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
  -H "A2A-Version: 1.0" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-001",
        "role": "ROLE_USER",
        "parts": [
          {"type": "text", "text": "Hello from a generic client"}
        ]
      },
      "configuration": {"returnImmediately": false}
    }
  }'
```

```bash
# Get Task status
curl -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
  -H "A2A-Version: 1.0" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-2",
    "method": "GetTask",
    "params": {"id": "task-uuid"}
  }'
```

```bash
# List recent tasks
curl -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
  -H "A2A-Version: 1.0" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-3",
    "method": "ListTasks",
    "params": {"pageSize": 5}
  }'
```

## Python (sync, `requests`)

```python
import os, requests

URL = os.getenv("AGENTWIRE_URL", "http://127.0.0.1:18800")
TOKEN = os.environ["AGENTWIRE_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "A2A-Version": "1.0",
    "Content-Type": "application/json",
}

def send(text: str, context_id: str | None = None) -> dict:
    params: dict = {
        "message": {
            "messageId": f"msg-{id(text)}",
            "role": "ROLE_USER",
            "parts": [{"type": "text", "text": text}],
        },
        "configuration": {"returnImmediately": False},
    }
    if context_id:
        params["message"]["contextId"] = context_id
    r = requests.post(
        f"{URL}/a2a/jsonrpc",
        headers=HEADERS,
        json={
            "jsonrpc": "2.0", "id": "1", "method": "SendMessage",
            "params": params,
        },
    )
    r.raise_for_status()
    return r.json()

def list_tasks(page_size: int = 5) -> dict:
    r = requests.post(
        f"{URL}/a2a/jsonrpc",
        headers=HEADERS,
        json={
            "jsonrpc": "2.0", "id": "1", "method": "ListTasks",
            "params": {"pageSize": page_size},
        },
    )
    r.raise_for_status()
    return r.json()
```

## Python (async, `aiohttp`)

```python
import os, aiohttp

URL = os.getenv("AGENTWIRE_URL", "http://127.0.0.1:18800")
TOKEN = os.environ["AGENTWIRE_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "A2A-Version": "1.0",
    "Content-Type": "application/json",
}

async def send(text: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{URL}/a2a/jsonrpc",
            headers=HEADERS,
            json={
                "jsonrpc": "2.0", "id": "1", "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": "msg-001",
                        "role": "ROLE_USER",
                        "parts": [{"type": "text", "text": text}],
                    },
                    "configuration": {"returnImmediately": False},
                },
            },
        ) as r:
            return await r.json()
```

## TypeScript / JavaScript (Node)

```typescript
const URL_ = process.env.AGENTWIRE_URL ?? 'http://127.0.0.1:18800';
const TOKEN = process.env.AGENTWIRE_TOKEN ?? '';

export async function send(text: string): Promise<unknown> {
  const r = await fetch(`${URL_}/a2a/jsonrpc`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'A2A-Version': '1.0',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 'req-1',
      method: 'SendMessage',
      params: {
        message: {
          messageId: 'msg-' + Date.now(),
          role: 'ROLE_USER',
          parts: [{ type: 'text', text }],
        },
        configuration: { returnImmediately: false },
      },
    }),
  });
  if (!r.ok) throw new Error(`AgentWire ${r.status}`);
  return r.json();
}
```

## Go

```go
package client

import (
    "bytes"
    "encoding/json"
    "fmt"
    "net/http"
    "os"
)

type Client struct {
    URL   string
    Token string
}

func New() *Client {
    return &Client{
        URL:   getenv("AGENTWIRE_URL", "http://127.0.0.1:18800"),
        Token: os.Getenv("AGENTWIRE_TOKEN"),
    }
}

func (c *Client) Send(text string) (map[string]any, error) {
    body, _ := json.Marshal(map[string]any{
        "jsonrpc": "2.0",
        "id":      "req-1",
        "method":  "SendMessage",
        "params": map[string]any{
            "message": map[string]any{
                "messageId": "msg-001",
                "role":      "ROLE_USER",
                "parts":     []map[string]string{{"type": "text", "text": text}},
            },
            "configuration": map[string]any{"returnImmediately": false},
        },
    })
    req, _ := http.NewRequest("POST", c.URL+"/a2a/jsonrpc", bytes.NewReader(body))
    req.Header.Set("Authorization", "Bearer "+c.Token)
    req.Header.Set("A2A-Version", "1.0")
    req.Header.Set("Content-Type", "application/json")
    resp, err := http.DefaultClient.Do(req)
    if err != nil { return nil, err }
    defer resp.Body.Close()
    var out map[string]any
    json.NewDecoder(resp.Body).Decode(&out)
    if resp.StatusCode != 200 {
        return nil, fmt.Errorf("status %d", resp.StatusCode)
    }
    return out, nil
}

func getenv(k, def string) string {
    if v := os.Getenv(k); v != "" { return v }
    return def
}
```

## Rust

```rust
use reqwest::Client;
use serde_json::json;
use std::env;

pub struct AgentWire {
    url: String,
    token: String,
    http: Client,
}

impl AgentWire {
    pub fn new() -> Self {
        Self {
            url: env::var("AGENTWIRE_URL").unwrap_or_else(|_| "http://127.0.0.1:18800".into()),
            token: env::var("AGENTWIRE_TOKEN").expect("AGENTWIRE_TOKEN"),
            http: Client::new(),
        }
    }

    pub async fn send(&self, text: &str) -> serde_json::Value {
        let body = json!({
            "jsonrpc": "2.0",
            "id":      "req-1",
            "method":  "SendMessage",
            "params": {
                "message": {
                    "messageId": "msg-001",
                    "role":      "ROLE_USER",
                    "parts":     [{"type": "text", "text": text}],
                },
                "configuration": {"returnImmediately": false},
            },
        });
        self.http
            .post(format!("{}/a2a/jsonrpc", self.url))
            .bearer_auth(&self.token)
            .header("A2A-Version", "1.0")
            .json(&body)
            .send().await.unwrap()
            .json().await.unwrap()
    }
}
```

## Discovery

Always discover the gateway's capabilities before assuming:

```bash
curl -s http://127.0.0.1:18800/.well-known/agent.json
```

Returns Agent Card. Use it to confirm `protocolVersion` matches your client.

## Token security

- **Never** put the bearer token in code, logs, or LLM prompts.
- Read from environment variable: `AGENTWIRE_TOKEN`.
- File-based with `chmod 600`: `--token-file /etc/agentwire/token` (server-side; the client never needs the file path).
- On Windows, use `setx AGENTWIRE_TOKEN ...` or a secrets manager.

## See also

- [SKILL.md](SKILL.md)
- [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md) — full method list
- [INTEGRATION_Claude.md](INTEGRATION_Claude.md) — Claude-specific notes
- [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) — if you want to author a statechart plugin instead of a one-off client
