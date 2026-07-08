# Integration: OpenClaw

> How to integrate AgentWire with [OpenClaw](https://openclaw.io) agents.

## Overview

AgentWire ships a **TypeScript plugin** in `plugin/` that embeds AgentWire's A2A gateway inside an OpenClaw agent process. The plugin reuses OpenClaw's HTTP server, registers the A2A endpoints as extensions, and forwards inbound A2A messages into the OpenClaw agent's message bus.

## Architecture

```
┌─────────────────────────────────────┐
│         OpenClaw Agent Process     │
│ ┌─────────────────────────────────┐ │
│ │ AgentWire TypeScript Plugin     │ │
│ │  - HTTP server extension        │ │
│ │  - A2A message routing          │ │
│ │  - Bearer-token middleware      │ │
│ └─────────────────────────────────┘ │
│ ┌─────────────────────────────────┐ │
│ │  OpenClaw Agent Runtime         │ │
│ │  (LLM, tools, memory, etc.)     │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
       ▲
       │ HTTP (port 18800)
       │
   Other A2A agents
```

The plugin lives in this repo at `plugin/`.

## Build & install

```bash
cd plugin
npm install
npm run build
```

This produces `dist/index.js` which OpenClaw loads at startup.

## Configuration

Edit `plugin/openclaw.plugin.json`:

```json
{
  "id": "agentwire",
  "name": "AgentWire",
  "version": "1.0.0",
  "activation": { "onStartup": true },
  "extensions": {
    "httpServers": [{ "port": 18800, "description": "A2A HTTP/JSON-RPC 端点" }]
  },
  "defaultConfig": {
    "pythonHost": "127.0.0.1",   // AgentWire Python service (if you also run it)
    "pythonPort": 18801,
    "port": 18800,
    "protocolVersion": "1.0.1",
    "corsOrigins": []             // explicit allowlist; empty = no CORS headers
  }
}
```

### Security (v1.5.1+)

- **Default bind**: `bindHost: "127.0.0.1"` — only use `"0.0.0.0"` behind firewall/VPN with `authToken` set.
- **Inbound auth**: `/a2a/jsonrpc` requires Bearer auth when `authToken` is configured; unauthenticated LAN exposure returns 401.
- **CORS**: `corsOrigins` is an explicit allowlist, no wildcards.

```json
"corsOrigins": ["https://app.example.com", "http://localhost:3000"]
```

Empty = browser cross-origin XHR will be blocked (most secure default for pure-server-to-server setups).

## Sending A2A messages from OpenClaw

Use the standard A2A protocol surface. The plugin exposes the same endpoints the standalone Python service does, so any A2A client (curl, Python `requests`, etc.) works:

```typescript
import axios from 'axios';

const response = await axios.post(
  'http://localhost:18800/a2a/jsonrpc',
  {
    jsonrpc: '2.0',
    id: 'req-1',
    method: 'SendMessage',
    params: {
      message: {
        messageId: crypto.randomUUID(),
        role: 'ROLE_USER',
        parts: [{ type: 'text', text: 'Hello from OpenClaw' }],
      },
      configuration: { returnImmediately: false },
    },
  },
  {
    headers: {
      Authorization: `Bearer ${process.env.AGENTWIRE_TOKEN}`,
      'A2A-Version': '1.0',
    },
  }
);

console.log(response.data);
```

## Receiving A2A messages

Inbound A2A messages are delivered to the OpenClaw agent's message bus as `a2a.message` events. Subscribe in your OpenClaw skill:

```typescript
agent.on('a2a.message', async (msg) => {
  const text = msg.parts.find(p => p.type === 'text')?.text;
  console.log(`[A2A] ${msg.role}: ${text}`);
  // ... respond via standard A2A message/send
});
```

## Cross-platform notes

- OpenClaw's built-in HTTP server is reused — the plugin does not start its own server.
- Streaming (A2A capability `streaming: true`) is supported via Server-Sent Events on the same port.
- For CUE plugin host users: OpenClaw + the AgentWire plugin is functionally equivalent to running the standalone Python service + CUE.

## See also

- [SKILL.md](SKILL.md) — general protocol
- [INTEGRATION_Generic.md](INTEGRATION_Generic.md) — language-agnostic
- [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md) — endpoint reference
