# AgentWire

> **A2A v1.0.1 communication gateway** — pure wire protocol layer for AI agents.
>
> **Languages**: [English](README.md) (this file) | [简体中文](README_CN.md)

[![A2A Protocol](https://img.shields.io/badge/A2A-v1.0.1-blue)](https://a2a-protocol.org/latest/specification/)
[![JSON-RPC](https://img.shields.io/badge/JSON--RPC-2.0-orange)](https://www.jsonrpc.org/specification)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-18%2B-green)](https://nodejs.org)
[![Status](https://img.shields.io/badge/status-v2.2.0-green)](https://github.com/DerekEXS/agentwire-core/releases/tag/v2.2.0)

---

## What is AgentWire?

AgentWire is a **protocol bridge** implementing the [A2A (Agent-to-Agent) v1.0.1](https://a2a-protocol.org) specification. It lets heterogeneous AI agents talk to each other over a uniform JSON-RPC interface, regardless of host platform (OpenClaw, QwenPaw, Hermes, Claude, or any custom framework).

AgentWire is **not** an agent framework. It does not generate responses, plan tasks, or hold conversation state. It is a **wire protocol layer** that:

- Receives A2A-format messages from any agent
- Authenticates and routes them
- Persists task state and per-peer message history
- Forwards to other agents via standard A2A semantics
- Exposes an Agent Card for service discovery

Workflow orchestration, statecharts, and plugin actions are **out of scope** for the core. The protocol is stable; behavior is pure transport + persistence.

## Features

- **A2A v1.0** — based on official [a2a-sdk](https://pypi.org/project/a2a-sdk/) v1.1.0+
  - Standard Agent Card exposed on both `/.well-known/agent.json` and `/.well-known/agent-card.json`
  - Standard A2A methods (PascalCase): `SendMessage`, `GetTask`, `ListTasks`, `CancelTask`, `SendStreamingMessage`
  - Task lifecycle state machine: `SUBMITTED → WORKING → COMPLETED / FAILED / CANCELED`
- **JSON-RPC 2.0** over HTTP — standard, language-agnostic transport (`/a2a/jsonrpc`).
- **Three-tier agent routing** — explicit `agentId` → rule-based (tags / patterns / priority) → default fallback (v2.0).
- **SQLite TaskStore** — persisted Task lifecycle with indexed queries (v2.0).
- **Bearer-token authentication** with file/env/arg resolution, fail-fast on insecure binds (`hmac.compare_digest`).
- **Loopback-default binds** (`127.0.0.1`); `0.0.0.0` requires explicit `--host` flag and emits a startup warning (v1.4.9+).
- **Built-in TLS** via `--tls-cert` + `--tls-key` (v1.4.9+).
- **CORS allowlist** (explicit origins only, no wildcards).
- **Sensitive-data redaction** — built-in pattern catalog; patterns shared via `/redact/patterns` so client tools reuse the same rules (v1.4.3+).
- **Token file health checks** — UTF-8 BOM auto-strip, CRLF warning, file-permission warning (v1.4.8+).
- **Log redaction** — incoming message text is hashed, never logged in plaintext (v1.5.1+).
- **Legacy compatibility**: v1.x `messages/*` JSON-RPC methods and `/a2a/rest/message/send` endpoint
  remain available on port 18800 for gradual migration; new agents should use the standard A2A
  methods above.
- **Log redaction** — incoming message text is hashed, never logged in plaintext (v1.5.1).
- **Workflow-hook allowlist** — `WORKFLOW_HOOK_CONFIG.allowed_commands` enforces external-binary invocation (v1.5.2).
- **TypeScript OpenClaw plugin** with `agentCard` extension and self-loading `defaultConfig` (v1.5.4).

## Architecture

```
┌────────────────────────────────────────────────┐
│         AgentWire A2A Gateway (CORE)          │
│                                                │
│  Python aiohttp ── HTTP/1.1 ── JSON-RPC 2.0  │
│  ┌────────────────────────────────────────┐  │
│  │  Auth (Bearer token)                   │  │
│  │  Routing (A2A methods + REST)          │  │
│  │  History (per-peer JSONL + redaction)  │  │
│  │  Redact (shared pattern catalog)       │  │
│  └────────────────────────────────────────┘  │
│  HTTP 18800 (default)                          │
└────────────────────────────────────────────────┘
        ▲                              ▲
        │ HTTP + Bearer                │ HTTP + Bearer
        │                              │
┌───────┴────────┐            ┌───────┴────────┐
│  Any AI Agent  │            │  Any AI Agent  │
│  (TS / Python │            │  (TS / Python │
│   / Rust / Go) │            │   / etc.)      │
└────────────────┘            └────────────────┘
```

The TypeScript plugin (`plugin/`) is one possible binding for OpenClaw-based agents. Other agents integrate directly with the JSON-RPC surface.

## Quick Start

### Recommended: Docker Compose (alongside AgentWire-Cue)

The CORE service ships as a container image. Use the Compose stack in
[`agentwire-cue/docker-compose.yml`](https://github.com/DerekEXS/agentwire-cue/blob/main/docker-compose.yml)
to bring up CORE + CUE together:

```bash
git clone https://github.com/DerekEXS/agentwire-cue.git
cd agentwire-cue
mkdir -p secrets
printf '%s\n' 'YOUR_A2A_TOKEN' > secrets/a2a-token.txt
printf '%s\n' 'YOUR_CUE_ADMIN_TOKEN' > secrets/cue-admin-token.txt
chmod 600 secrets/*.txt
docker compose up -d

# Verify health
docker ps
curl -s http://127.0.0.1:18800/.well-known/agent.json
```

CORE listens on `127.0.0.1:18800` by default; CUE on `127.0.0.1:18801` (A2A) +
`127.0.0.1:19000` (admin).

### Standalone (Python directly)

If you prefer to run CORE outside Docker:

```bash
cd server
pip install -r requirements.txt
cp config.yaml.example config.yaml
echo "my-token-123" > /tmp/agentwire.token

python3 start.py \
  --host 127.0.0.1 \
  --port 18800 \
  --token-file /tmp/agentwire.token
```

### Test it

```bash
# Discover
curl -s http://127.0.0.1:18800/.well-known/agent.json

# Health
curl -s http://127.0.0.1:18800/health

# Send a message (standard A2A JSON-RPC)
curl -X POST http://127.0.0.1:18800/a2a/jsonrpc \
  -H "Authorization: Bearer my-token-123" \
  -H "A2A-Version: 1.0" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":"req-1",
    "method":"SendMessage",
    "params":{
      "message":{
        "messageId":"msg-001",
        "role":"ROLE_USER",
        "parts":[{"type":"text","text":"Hello"}]
      },
      "configuration":{"returnImmediately":false}
    }
  }'
```

### Build the TypeScript OpenClaw plugin (optional)

```bash
cd plugin
npm install
npm run build
```

Drop `dist/` into your OpenClaw plugin loader. The manifest is now
OpenClaw 2026.6.6-schema-compatible: `additionalProperties: false`, `kind: "http-server"`,
`uiHints` for the main config fields, and `version: "1.5.5"` synced with the CORE image tag.

## Configuration

Edit `server/config.yaml` (see `config.yaml.example` for full template). Two top-level sections:

### `workflow_hook` (optional)

Triggers an external agent CLI (e.g. OpenClaw) on keyword match:

```yaml
workflow_hook:
  enabled: true
  openclaw_path: "/path/to/openclaw"
  agent_id: "main"
  workflow_path: "/path/to/your/workflow"
  trigger_keywords: ["project:", "scenes:", "video"]
  trigger_min_lines: 5
  timeout: 300
```

### `history` (v1.4.3+)

Per-peer JSONL message history with optional redaction and context injection:

```yaml
history:
  enabled: true
  max_rounds_per_peer: 0        # 0 = unlimited (default)
  context_rounds: 5             # 0 = off
  storage_dir: "~/.local/share/agentwire/history"
  redact_sensitive: true
  round_close:
    mode: heuristic             # heuristic | explicit
    heuristic_idle_seconds: 300
```

## HTTP API

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/.well-known/agent.json` | Optional | Agent Card discovery |
| GET | `/health` | None | Liveness probe |
| GET | `/a2a/metrics` | Bearer (v1.5.2) | Task counters |
| GET | `/redact/patterns` | Required | Shared redaction pattern catalog |
| POST | `/a2a/jsonrpc` | Required | JSON-RPC 2.0 endpoint |
| POST | `/a2a/jsonrpc` | Required | Standard A2A JSON-RPC endpoint (all methods) |

## JSON-RPC Methods

Standard A2A v1.0 (v2.0+):

- `SendMessage` — send a message, get a Task back
- `GetTask` — fetch a Task by ID
- `ListTasks` — list all Tasks (with pagination)
- `CancelTask` — cancel a Task
- `SendStreamingMessage` — SSE-based streaming (v2.0+)
- `GetExtendedAgentCard` — return the extended Agent Card

Legacy-compatible (kept on the v1.5.x server; not used by v2.0+):

- `messages/list`, `messages/get`, `messages/peers`, `messages/export`, `messages/import`

For full schemas, see [`skill/PROTOCOL_QUICK_REF.md`](skill/PROTOCOL_QUICK_REF.md).

## Repository Structure

```
agentwire-core/
├── server/                       # Python A2A service
│   ├── start.py                  # Main entry point
│   ├── proxy.py                  # Loopback reverse proxy (18802 → 18800)
│   ├── history.py                # Per-peer JSONL persistence
│   ├── redact.py                 # Sensitive-pattern catalog
│   ├── config.yaml.example       # Configuration template
│   ├── requirements.txt
│   ├── Dockerfile                # v1.5.0: python:3.13-slim container build
│   └── README.md
│
├── plugin/                       # TypeScript OpenClaw plugin
│   ├── src/
│   │   └── index.ts
│   ├── openclaw.plugin.json      # v1.5.5: OpenClaw 2026.6.6 schema (additionalProperties, kind, uiHints)
│   ├── package.json
│   └── tsconfig.json
│
├── skill/                        # Agent-facing documentation
│   ├── SKILL.md                  # Universal protocol guide
│   ├── SKILL_CN.md               # 中文版
│   ├── PROTOCOL_QUICK_REF.md     # Method signatures
│   ├── INTEGRATION_OpenClaw.md
│   ├── INTEGRATION_QwenPaw.md
│   ├── INTEGRATION_Hermes.md
│   ├── INTEGRATION_Claude.md
│   ├── INTEGRATION_Generic.md
│   └── PLUGIN_DEVELOPMENT.md
│
├── docker-compose.yml            # v1.5.0: standalone CORE compose
├── .gitignore
├── LICENSE
└── README.md                     # This file
```

## Integrating an agent

Pick the integration guide that matches your agent's platform:

- [OpenClaw](skill/INTEGRATION_OpenClaw.md) — TypeScript plugin reuse
- [QwenPaw](skill/INTEGRATION_QwenPaw.md) — Python A2A client
- [Hermes](skill/INTEGRATION_Hermes.md) — generic adapter
- [Claude](skill/INTEGRATION_Claude.md) — Claude Code / Claude API
- [Custom agent](skill/INTEGRATION_Generic.md) — any HTTP client

For a deeper understanding of the protocol, read [SKILL.md](skill/SKILL.md) (or [SKILL_CN.md](skill/SKILL_CN.md) for Chinese).

If you are authoring a YAML statechart plugin for an AgentWire-compatible host, see [PLUGIN_DEVELOPMENT.md](skill/PLUGIN_DEVELOPMENT.md).

## Security

- **Bearer token** required for all non-loopback requests (HMAC constant-time compare).
- **`/a2a/metrics`** requires Bearer auth (v1.5.2).
- **CORS** uses explicit origin allowlist (no wildcards).
- **Loopback default binds** — `127.0.0.1` is the default; `0.0.0.0` requires explicit `--host 0.0.0.0` and logs a startup warning.
- **TLS support** via `--tls-cert` + `--tls-key` (v1.4.9).
- **Redaction** of API keys, tokens, JWTs, private keys, and URL-embedded passwords before any history persistence.
- **Log redaction** — incoming message text is replaced with `len=... sha256[:16]=... peer=...` in logs (v1.5.1).
- **Token file hygiene** — UTF-8 BOM auto-strip, CRLF + chmod warnings at startup (v1.4.8).
- **Internal errors** are not leaked to clients (logged server-side, generic 500 returned).
- **Workflow-hook allowlist** — external binaries invoked by the workflow hook are restricted by `WORKFLOW_HOOK_CONFIG.allowed_commands` (v1.5.2).

## Known Limitations

### WSL2 Networking (AI-CLAW)

When running CORE in Docker with `network_mode: host` on WSL2, external access via Tailscale requires Windows `portproxy`. See [docs/PORTPROXY-FIX.md](docs/PORTPROXY-FIX.md) for troubleshooting.

For agent compatibility notes (role format, parts structure), see [docs/AGENT-COMPATIBILITY.md](docs/AGENT-COMPATIBILITY.md).

## Deployment

> ⚠️ **HTTP-not-HTTPS**: AgentWire CORE uses plain HTTP unless `--tls-cert` + `--tls-key` are supplied. The `Authorization: Bearer <token>` header is therefore transmitted **in cleartext** on the wire unless TLS is enabled.

### Docker (recommended)

The CORE image (`agentwire-core:v2.1.0`) is published alongside CUE in the
CUE repository's `docker-compose.yml`. The Compose stack brings up CORE on
`127.0.0.1:18800` and CUE on `127.0.0.1:18801` + `127.0.0.1:19000`, both with
loopback-only host publishes and shared token secrets.

```bash
git clone https://github.com/DerekEXS/agentwire-cue.git
cd agentwire-cue
mkdir -p secrets
printf '%s\n' 'YOUR_A2A_TOKEN' > secrets/a2a-token.txt
printf '%s\n' 'YOUR_CUE_ADMIN_TOKEN' > secrets/cue-admin-token.txt
chmod 600 secrets/*.txt
docker compose up -d
```

### Standalone

If you want to run CORE outside Docker, see the [Quick Start](#quick-start) above.

### Suitable for

- Loopback-only deployments (single-host agent on `127.0.0.1:18800`)
- Private LAN / Tailscale / WireGuard segments where the network itself is trusted
- TLS-terminated reverse proxy fronts (nginx / Caddy / Traefik / Cloudflare Tunnel)

### NOT suitable for

- Direct public-internet exposure without TLS

### If you must expose AgentWire to an untrusted network

1. **Required**: put a TLS-terminating reverse proxy in front, **or** run CORE with `--tls-cert` + `--tls-key`
2. **Recommended**: bind CORE to loopback only (`--host 127.0.0.1`); the proxy exposes the public port
3. **Strongly recommended**: rotate the bearer token regularly and use a 32+ char random value
4. **Consider**: mTLS between agents if you control both ends (AgentWire does not implement mTLS — that would be a future enhancement)

## Protocol

- **A2A v1.0.1** — <https://a2a-protocol.org/latest/specification/>
- **JSON-RPC 2.0** — <https://www.jsonrpc.org/specification>

## References

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
- [Releases](https://github.com/DerekEXS/agentwire-core/releases)
- [Issues](https://github.com/DerekEXS/agentwire-core/issues)

## License

**MIT License** — Copyright (c) 2026 DerekEXS. See [LICENSE](LICENSE) for the full text.

You are free to use, modify, and distribute this software, with or without modification, provided the copyright notice and permission notice are preserved.
