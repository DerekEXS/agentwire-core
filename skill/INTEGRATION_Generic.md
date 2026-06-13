# Integration: Generic / Custom Agents

> How to integrate AgentWire from any language or framework (v1.5.2).
> Use this if your agent is not on OpenClaw, QwenPaw, Hermes, or Claude.

## What you need to do

AgentWire speaks plain HTTP + JSON-RPC 2.0. You need:

1. **HTTP client** (any language can do this)
2. **Bearer token** in `Authorization` header
3. **JSON body** in the A2A `message/send` shape

That is the entire integration. There is no SDK to install and no framework to extend.

## curl (reference implementation)

```bash
# Send a message
curl -X POST http://127.0.0.1:18800/a2a/rest/message/send \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "contextId": "ctx-001",
    "message": {
      "messageId": "msg-001",
      "role": "user",
      "parts": [
        {"type": "text", "text": "Hello from a generic client"}
      ]
    }
  }'
```

```bash
# JSON-RPC equivalent
curl -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "message/send",
    "params": {
      "contextId": "ctx-001",
      "message": {
        "parts": [{"type": "text", "text": "Hello"}]
      }
    }
  }'
```

```bash
# Read history
curl -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "messages/list",
    "params": {"peer_name": "初梦", "limit": 5}
  }'
```

## Python (sync, `requests`)

```python
import os, requests

URL = os.getenv("AGENTWIRE_URL", "http://127.0.0.1:18800")
TOKEN = os.environ["AGENTWIRE_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def send(text: str) -> dict:
    r = requests.post(
        f"{URL}/a2a/rest/message/send",
        headers=HEADERS,
        json={"message": {"parts": [{"type": "text", "text": text}]}},
    )
    r.raise_for_status()
    return r.json()

def list_messages(peer_name: str, limit: int = 5) -> list:
    r = requests.post(
        f"{URL}/a2a/jsonrpc",
        headers=HEADERS,
        json={
            "jsonrpc": "2.0", "id": 1, "method": "messages/list",
            "params": {"peer_name": peer_name, "limit": limit},
        },
    )
    r.raise_for_status()
    return r.json()["result"]["messages"]
```

## Python (async, `aiohttp`)

```python
import os, aiohttp

URL = os.getenv("AGENTWIRE_URL", "http://127.0.0.1:18800")
TOKEN = os.environ["AGENTWIRE_TOKEN"]

async def send(text: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{URL}/a2a/rest/message/send",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"message": {"parts": [{"type": "text", "text": text}]}},
        ) as r:
            return await r.json()
```

## TypeScript / JavaScript (Node)

```typescript
import { readFileSync } from 'fs';

const URL_ = process.env.AGENTWIRE_URL ?? 'http://127.0.0.1:18800';
const TOKEN = process.env.AGENTWIRE_TOKEN ?? '';

export async function send(text: string): Promise<unknown> {
  const r = await fetch(`${URL_}/a2a/rest/message/send`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message: { parts: [{ type: 'text', text }] },
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
        "message": map[string]any{
            "parts": []map[string]string{{"type": "text", "text": text}},
        },
    })
    req, _ := http.NewRequest("POST", c.URL+"/a2a/rest/message/send", bytes.NewReader(body))
    req.Header.Set("Authorization", "Bearer "+c.Token)
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
        let body = json!({"message": {"parts": [{"type": "text", "text": text}]}});
        self.http
            .post(format!("{}/a2a/rest/message/send", self.url))
            .bearer_auth(&self.token)
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
