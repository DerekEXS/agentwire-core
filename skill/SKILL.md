# AgentWire SKILL — Universal Protocol Guide

> **Language**: English | [中文版 (SKILL_CN.md)](SKILL_CN.md)

## What is AgentWire?

AgentWire is a **protocol bridge** implementing the [A2A (Agent-to-Agent) v1.0.1](https://a2a-protocol.org) specification. It enables heterogeneous AI agents to communicate over a unified JSON-RPC interface, regardless of the host platform (OpenClaw, QwenPaw, Hermes, Claude, or any custom agent framework).

AgentWire is **not** an agent framework. It does **not** generate responses, plan tasks, or hold conversation state. It is a **wire protocol** — a pure communication layer that:

- Receives A2A-format messages from any agent
- Authenticates and routes them
- Persists task state and message history
- Forwards to other agents via standard A2A semantics
- Exposes an Agent Card for discovery (`/.well-known/agent.json`)

Extension points (statechart workflows, custom routing, plugin actions) are **out of scope** for the core. The companion project [agentwire-cue](https://github.com/DerekEXS/agentwire-cue) provides a YAML-driven plugin host on top of AgentWire.

## When should an agent integrate with AgentWire?

Integrate when **any** of the following apply:

- You need to send a task to a remote agent and get a structured response back
- You need a persistent audit trail of who-said-what-to-whom (history)
- You need a stable JSON-RPC endpoint that any third-party agent can discover
- You operate multiple agents on a single host and want them to talk over a uniform wire

Do **not** integrate if:

- You are building a single-process agent with no inter-agent communication
- You are building a low-latency streaming pipeline (AgentWire is request/response, not pure push)

## Architecture at a glance

```
┌────────────────────────────────────────────────┐
│         AgentWire A2A Gateway (CORE)          │
│  - Python aiohttp HTTP server                 │
│  - JSON-RPC 2.0 over HTTP/1.1                 │
│  - Bearer-token authentication                │
│  - JSONL history persistence (per-peer)      │
│  - Sensitive-data redaction (patterns API)   │
│  - A2A v1.0.1 protocol                        │
└────────────────────────────────────────────────┘
        ▲                              ▲
        │ HTTP + Bearer token          │ HTTP + Bearer token
        │                              │
┌───────┴────────┐            ┌───────┴────────┐
│  Any AI Agent  │            │  Any AI Agent  │
│  (TS / Python │            │  (TS / Python │
│   / Rust / Go) │            │   / etc.)      │
└────────────────┘            └────────────────┘
```

AgentWire is **pluggable** on both sides: any agent platform can wrap the JSON-RPC surface. Pre-built platform integrations:

- [OpenClaw](INTEGRATION_OpenClaw.md) — TypeScript
- [QwenPaw](INTEGRATION_QwenPaw.md) — Python
- [Hermes](INTEGRATION_Hermes.md) — generic
- [Claude](INTEGRATION_Claude.md) — Python / TypeScript
- [Generic / custom](INTEGRATION_Generic.md) — any HTTP client

## Minimum viable integration (5 lines)

```bash
# Discover the gateway
curl -s http://localhost:18800/.well-known/agent.json
```

```python
# Send a message
import requests
r = requests.post(
    "http://localhost:18800/a2a/rest/message/send",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"message": {"parts": [{"type": "text", "text": "Hello"}]}},
)
print(r.json())
```

That's it — you can talk to AgentWire.

## Core capabilities

| Capability | API | Notes |
|------------|-----|-------|
| Discovery | `GET /.well-known/agent.json` | Returns Agent Card (v1.4.3+; v1.4.2 has a routing bug — see Known Issues) |
| Send message | `POST /a2a/rest/message/send` | REST wrapper around `message/send` JSON-RPC |
| Health check | `GET /health` | v1.4.3+; v1.4.2 has a routing bug |
| List tasks | `tasks/list` (JSON-RPC) | v1.4.3+ (full JSON-RPC endpoint) |
| Get task | `tasks/get` (JSON-RPC) | v1.4.3+ |
| Cancel task | `tasks/cancel` (JSON-RPC) | v1.4.3+ |
| Message history | `messages/list`, `messages/get`, `messages/peers`, `messages/export` | **v1.4.3 new** |
| Redaction patterns | `GET /redact/patterns` | **v1.4.3 new** — shared with plugin hosts |
| Metrics | `GET /a2a/metrics` | task counts |

## Quick Start (operator view)

```bash
# 1. Install
cd server
pip install -r requirements.txt
cp config.yaml.example config.yaml  # edit if needed
echo "my-token-123" > /tmp/agentwire.token

# 2. Run (loopback-only, with token)
python3 start.py --host 127.0.0.1 --port 18800 --token-file /tmp/agentwire.token

# 3. Test
curl -s http://127.0.0.1:18800/.well-known/agent.json
curl -X POST http://127.0.0.1:18800/a2a/rest/message/send \
  -H "Authorization: Bearer my-token-123" \
  -H "Content-Type: application/json" \
  -d '{"message":{"parts":[{"type":"text","text":"ping"}]}}'
```

## Where to read next

| If you are… | Read… |
|-------------|-------|
| An OpenClaw agent | [INTEGRATION_OpenClaw.md](INTEGRATION_OpenClaw.md) |
| A QwenPaw agent | [INTEGRATION_QwenPaw.md](INTEGRATION_QwenPaw.md) |
| A Hermes agent | [INTEGRATION_Hermes.md](INTEGRATION_Hermes.md) |
| A Claude agent | [INTEGRATION_Claude.md](INTEGRATION_Claude.md) |
| A custom agent in any language | [INTEGRATION_Generic.md](INTEGRATION_Generic.md) |
| Authoring a plugin for the cue host | [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) |
| Looking up a JSON-RPC method signature | [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md) |

## License

MIT License. Copyright (c) 2026 DerekEXS. See [LICENSE](../LICENSE).

## Protocol & References

- **A2A Protocol**: v1.0.1 — <https://a2a-protocol.org/latest/specification/>
- **JSON-RPC 2.0**: <https://www.jsonrpc.org/specification>
- **Repo**: <https://github.com/DerekEXS/agentwire-core>
- **Releases**: <https://github.com/DerekEXS/agentwire-core/releases>

## Known issues in v1.4.2 (fixed in v1.4.3)

- `GET /.well-known/agent.json` and `GET /health` are not routed in v1.4.2 (handler functions exist but `_setup_routes()` does not register them)
- `POST /a2a/jsonrpc` is not routed; only `/a2a/rest/message/send` is exposed
- No message-history endpoints
- No `redact/patterns` endpoint

v1.4.3 closes all of these.
