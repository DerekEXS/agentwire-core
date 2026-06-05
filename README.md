# AgentWire — A2A v1.0.1 Gateway

AgentWire is a **protocol bridge** between the A2A (Agent-to-Agent) protocol and the OpenClaw chat system, plus a standalone Python A2A service.

## Repository Structure

```
agentwire-core/
├── server/         # Python A2A JSON-RPC v1.0.1 service
│   ├── start.py    # Main entry point
│   ├── proxy.py    # Reverse proxy (18802 → 18800)
│   ├── config.yaml # Server configuration
│   └── ...
└── plugin/         # TypeScript OpenClaw plugin
    ├── src/        # Plugin source
    ├── openclaw.plugin.json
    └── ...
```

## Quick Start

```bash
cd agentwire-core/server
pip install -r requirements.txt
python3 start.py --port 18800 --token-file /path/to/token.txt
```

## Companion Repository

- **[agentwire-cue](https://github.com/DerekEXS/agentwire-cue)** — YAML-driven plugin host that consumes AGENTWIRE's A2A service.

## Protocol

- **A2A v1.0.1** — full support for `/.well-known/agent.json`, `message/send`, `tasks/get`, streaming.

## License

See LICENSE file.
