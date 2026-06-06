# Integration: Hermes

> How to integrate AgentWire with [Hermes](https://hermes.io) agents.

## About Hermes

Hermes is a generic agent framework. It exposes agents via gRPC and HTTP, with a plugin model for custom transports. AgentWire integrates via a thin HTTP-side wrapper that translates Hermes messages to A2A format.

## Architecture

```
┌──────────────────────────────────┐
│       Hermes Agent Process       │
│                                  │
│  ┌───────────────────────────┐ │
│  │  Hermes A2A adapter       │ │  ← you write this (≤ 50 lines)
│  │  (translates A2A↔Hermes)  │ │
│  └───────────────────────────┘ │
└────────────┬─────────────────────┘
             │ HTTP + Bearer token
             ▼
┌──────────────────────────────────┐
│   AgentWire Python A2A Service  │
│   (18800)                        │
└──────────────────────────────────┘
```

## Adapter skeleton (Python)

```python
# hermes_adapters/agentwire.py
import aiohttp, os
from hermes import Agent, message_handler

AGENTWIRE = os.getenv("AGENTWIRE_URL", "http://127.0.0.1:18800")
TOKEN = os.environ["AGENTWIRE_TOKEN"]

class AgentWireAdapter(Agent):
    name = "agentwire"
    description = "Forward Hermes messages to AgentWire A2A gateway."

    @message_handler
    async def handle(self, msg):
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{AGENTWIRE}/a2a/rest/message/send",
                headers={"Authorization": f"Bearer {TOKEN}"},
                json={"message": {"parts": [{"type": "text", "text": msg.text}]}},
            ) as r:
                data = await r.json()
        parts = data.get("message", {}).get("parts", [])
        return msg.reply(" ".join(p.get("text", "") for p in parts if p.get("type") == "text"))
```

## Adapter skeleton (Rust)

```rust
// src/bin/agentwire_hermes.rs
use hermes::prelude::*;
use reqwest::Client;
use std::env;

#[tokio::main]
async fn main() {
    let token = env::var("AGENTWIRE_TOKEN").unwrap();
    let url = env::var("AGENTWIRE_URL").unwrap_or_else(|_| "http://127.0.0.1:18800".to_string());
    let client = Client::new();
    let agent = Agent::new("agentwire")
        .on_message(move |msg| {
            let url = url.clone();
            let client = client.clone();
            let token = token.clone();
            async move {
                let body = serde_json::json!({
                    "message": {"parts": [{"type": "text", "text": msg.text}]}
                });
                let resp: serde_json::Value = client
                    .post(format!("{}/a2a/rest/message/send", url))
                    .header("Authorization", format!("Bearer {}", token))
                    .json(&body)
                    .send().await?
                    .json().await?;
                Ok(msg.reply(extract_text(&resp)))
            }.boxed()
        });
    agent.run().await;
}
```

## Multi-agent relay

Hermes often runs multiple specialized agents in one process. Pattern:

1. Hermes A2A adapter subscribes to AgentWire `message/send` events
2. Routes based on message prefix (`/aw:foo` → foo agent, etc.)
3. Responses routed back via AgentWire `tasks/subscribe`

## See also

- [SKILL.md](SKILL.md)
- [INTEGRATION_Generic.md](INTEGRATION_Generic.md)
- [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md)
