# AgentWire SKILL — Universal Protocol Guide

> **Language**: English | [中文版 (SKILL_CN.md)](SKILL_CN.md)
> **Current version**: CORE v1.5.5 / CUE v1.6.0

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
│  - Bearer-token auth (hmac.compare_digest)    │
│  - JSONL history persistence (per-peer)      │
│  - Sensitive-data redaction (patterns API)   │
│  - TLS support (--tls-cert / --tls-key)      │
│  - Docker-compose ready                        │
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
curl -s http://127.0.0.1:18800/.well-known/agent.json
```

```python
# Send a message
import requests
r = requests.post(
    "http://127.0.0.1:18800/a2a/rest/message/send",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"message": {"parts": [{"type": "text", "text": "Hello"}]}},
)
print(r.json())
```

That's it — you can talk to AgentWire.

## Core capabilities

| Capability | API | Notes |
|------------|-----|-------|
| Discovery | `GET /.well-known/agent.json` | Public; returns Agent Card |
| Send message | `POST /a2a/rest/message/send` | REST wrapper around `message/send` JSON-RPC |
| Send message (JSON-RPC) | `POST /a2a/jsonrpc` `message/send` | Full JSON-RPC 2.0 envelope |
| Health check | `GET /health` | Public; no auth needed |
| List tasks | `tasks/list` (JSON-RPC) | Bearer auth required |
| Get task | `tasks/get` (JSON-RPC) | Bearer auth required |
| Cancel task | `tasks/cancel` (JSON-RPC) | Bearer auth required |
| Message history | `messages/list`, `messages/get`, `messages/peers` | **v1.4.3**; Bearer auth |
| Export history | `messages/export` | **v1.4.3**; paginated since v1.5.1 (limit/offset/has_more, max 200) |
| Import messages | `messages/import` | **v1.4.8**; Bearer auth; max 100 msgs/request, 64KB/part |
| Redaction patterns | `GET /redact/patterns` | Bearer auth; shared with plugin hosts |
| Metrics | `GET /a2a/metrics` | **v1.5.2**: Bearer auth required (was public in ≤v1.5.1) |

## Quick Start

### Recommended: Docker Compose

```bash
cd agentwire_cue
mkdir -p secrets
printf '%s\n' 'YOUR_A2A_TOKEN' > secrets/a2a-token.txt
printf '%s\n' 'YOUR_ADMIN_TOKEN' > secrets/cue-admin-token.txt
chmod 600 secrets/*.txt
docker compose up -d
curl -s http://127.0.0.1:18800/.well-known/agent.json
```

### Alternative: native Python

```bash
cd server
pip install -r requirements.txt
echo "YOUR_A2A_TOKEN" > /tmp/agentwire.token
chmod 600 /tmp/agentwire.token
python3 start.py --host 127.0.0.1 --port 18800 --token-file /tmp/agentwire.token
```

## Security defaults (v1.5.x)

- **Default bind**: `127.0.0.1` (loopback only). Use `--host 0.0.0.0` explicitly for LAN/VPN exposure, which logs a startup warning and requires `--token` or `--token-file`.
- **TLS**: Use `--tls-cert` and `--tls-key` to enable HTTPS (v1.4.9+).
- **Token hygiene**: Startup checks for UTF-8 BOM, CRLF line endings, and overly broad file permissions (v1.4.8).
- **Log redaction**: Message text is **never** logged — only `len=` and `sha256[:16]` with a hashed peer identifier (v1.5.1+).
- **Import/export limits**: `messages/import` caps at 100 messages/request and 64KB/part (hard caps 500/256KB via env). `messages/export` is paginated (default 50 lines, max 200).
- **Metrics auth**: `/a2a/metrics` requires Bearer auth since v1.5.2.
- **Workflow hook**: Disabled by default; `allowed_commands` allow-list restricts which binaries can be spawned when `workflow_hook.enabled: true`.

## Publishing

AgentWire uses the `silk-thread` pseudonym for all commits. When SSH to GitHub is intercepted by a local proxy (mihomo TUN), publishes fall back to the [Composio](https://composio.dev) `GITHUB_COMMIT_MULTIPLE_FILES` / `GITHUB_CREATE_A_RELEASE` toolchain. Both paths produce the same public release.

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

MIT License. Copyright (c) 2026 DerekEXS.

## Protocol & References

- **A2A Protocol**: v1.0.1 — <https://a2a-protocol.org/latest/specification/>
- **JSON-RPC 2.0**: <https://www.jsonrpc.org/specification>
- **Repo**: <https://github.com/DerekEXS/agentwire-core>
- **Releases**: <https://github.com/DerekEXS/agentwire-core/releases>

## Changelog highlights

| Version | Key changes |
|---------|-------------|
| v1.4.3 | History persistence, message APIs, redaction catalog |
| v1.4.8 | `messages/import`, token health diagnostics |
| v1.4.9 | TLS support, `CORE_LISTEN_HOST` env |
| v1.5.0 | Docker + compose, `CORE_LISTEN_PORT` / `AGENTWIRE_TOKEN_FILE` env |
| v1.5.1 | Log redaction (`len= hash=`), import/export size limits & pagination, plugin inbound auth + loopback bind |
| v1.5.2 | `/a2a/metrics` auth, token path redaction, workflow `allowed_commands`, compose loopback publish, demo tokens replaced |
| v1.5.3 | All SKILL files updated to current feature state |
| v1.5.4 | Version string unification + plugin self-loading manifest fix |
| v1.5.5 | OpenClaw 2026.6.6 schema compat (`additionalProperties`, `kind: "http-server"`, `uiHints`), README refresh |
