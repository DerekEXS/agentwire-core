# AgentWire

> **A2A v1.0.1 communication gateway** — pure wire protocol layer for AI agents.
>
> **Languages**: [English](README.md) (this file) | [简体中文](README_CN.md)

[![A2A Protocol](https://img.shields.io/badge/A2A-v1.0.1-blue)](https://a2a-protocol.org/latest/specification/)
[![JSON-RPC](https://img.shields.io/badge/JSON--RPC-2.0-orange)](https://www.jsonrpc.org/specification)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-18%2B-green)](https://nodejs.org)

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

- **A2A v1.0.1** — full support for `/.well-known/agent.json`, `message/send`, `tasks/*`, agent cards.
- **JSON-RPC 2.0** over HTTP — standard, language-agnostic transport.
- **Bearer-token authentication** with file/env/arg resolution, fail-fast on insecure binds.
- **CORS allowlist** (explicit origins only, no wildcards).
- **Per-peer message history** — auto-saved to JSONL, rotatable, with optional FIFO cap.
- **Context auto-injection** — last N rounds attached to message metadata so agents can resume context.
- **Sensitive-data redaction** — built-in pattern catalog; patterns shared via `/redact/patterns` so client tools reuse the same rules.
- **Metrics endpoint** for ops monitoring.
- **Optional workflow hook** to trigger external agents (OpenClaw CLI, etc.) on keyword match.
- **TypeScript OpenClaw plugin** that reuses OpenClaw's HTTP server.

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

### Run the Python A2A service

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

# Send a message
curl -X POST http://127.0.0.1:18800/a2a/rest/message/send \
  -H "Authorization: Bearer my-token-123" \
  -H "Content-Type: application/json" \
  -d '{"message":{"parts":[{"type":"text","text":"Hello"}]}}'
```

### Build the TypeScript OpenClaw plugin (optional)

```bash
cd plugin
npm install
npm run build
```

Drop `dist/` into your OpenClaw plugin loader.

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
| GET | `/a2a/metrics` | Required | Task counters |
| GET | `/redact/patterns` | Required | Shared redaction pattern catalog |
| POST | `/a2a/jsonrpc` | Required | JSON-RPC 2.0 endpoint |
| POST | `/a2a/rest/message/send` | Required | REST wrapper around `message/send` |

## JSON-RPC Methods

Standard A2A v1.0.1:

- `message/send` — send a message, get a task back
- `tasks/get` — fetch a task by ID
- `tasks/list` — list all tasks in memory
- `tasks/cancel` — cancel a task
- `tasks/subscribe` — reserve a subscription (no-op stub)
- `agent/getCard` — return the Agent Card

History (v1.4.3 new):

- `messages/list` — recent messages for one or all peers
- `messages/get` — single round (outbound + inbound) for a peer
- `messages/peers` — list known peers with metadata
- `messages/export` — dump a peer's history as JSONL or Markdown

For full schemas, see [`skill/PROTOCOL_QUICK_REF.md`](skill/PROTOCOL_QUICK_REF.md).

## Repository Structure

```
agentwire-core/
├── server/                       # Python A2A service
│   ├── start.py                  # Main entry point
│   ├── proxy.py                  # Loopback reverse proxy (18802 → 18800)
│   ├── history.py                # Per-peer JSONL persistence (v1.4.3)
│   ├── redact.py                 # Sensitive-pattern catalog (v1.4.3)
│   ├── config.yaml.example       # Configuration template
│   ├── requirements.txt
│   └── README.md
│
├── plugin/                       # TypeScript OpenClaw plugin
│   ├── src/
│   │   └── index.ts
│   ├── openclaw.plugin.json
│   ├── package.json
│   └── tsconfig.json
│
├── skill/                        # v1.4.3 new: agent-facing documentation
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

- **Bearer token** required for all non-loopback requests.
- **CORS** uses explicit origin allowlist (no wildcards).
- **Fail-fast** on non-loopback bind with empty token.
- **Redaction** of API keys, tokens, JWTs, private keys, and URL-embedded passwords before any history persistence.
- **Internal errors** are not leaked to clients (logged server-side, generic 500 returned).

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
