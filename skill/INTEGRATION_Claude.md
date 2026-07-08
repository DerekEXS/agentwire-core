# Integration: Claude

> How to integrate AgentWire with [Claude](https://anthropic.com/claude) (Claude Code / Claude API / Claude Agent SDK).

## Two integration paths

| Path | When to use |
|------|-------------|
| **A. Claude Code as a peer agent** | You run Claude Code locally, and want it to talk to other agents via AgentWire |
| **B. Claude API as a service backend** | You expose an Anthropic API-driven agent that registers itself as an A2A peer |

This document covers **Path A**. For Path B, treat Claude as a generic HTTP client and follow [INTEGRATION_Generic.md](INTEGRATION_Generic.md).

## Path A: Claude Code as a peer agent

Claude Code is Anthropic's CLI agent. It can run arbitrary scripts and tools. To make it A2A-aware, drop an `agentwire` skill into `~/.claude/skills/agentwire/`:

### 1. Install the skill

```bash
mkdir -p ~/.claude/skills/agentwire
# Copy INTEGRATION_Claude.md and SKILL.md from agentwire-core/skill/
# into ~/.claude/skills/agentwire/
```

### 2. Configure credentials

In `~/.claude/agentwire.env`:

```bash
AGENTWIRE_URL=http://127.0.0.1:18800
AGENTWIRE_TOKEN=my-token-123
```

### 3. Send a message from a Claude Code session

When Claude Code is asked "send a message to the AgentWire gateway", it can run:

```bash
source ~/.claude/agentwire.env
curl -s -X POST "$AGENTWIRE_URL/a2a/jsonrpc" \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
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
        "parts":[{"type":"text","text":"Hello from Claude"}]
      },
      "configuration":{"returnImmediately":false}
    }
  }'
```

### 4. List recent tasks

```bash
source ~/.claude/agentwire.env
curl -s -X POST "$AGENTWIRE_URL/a2a/jsonrpc" \
  -H "Authorization: Bearer $AGENTWIRE_TOKEN" \
  -H "A2A-Version: 1.0" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"ListTasks","params":{"pageSize":10}}'
```

## Using `silk-thread` (this agent) as the bridge

If you have an `silk-thread`-named agent (e.g. an OpenClaw agent whose role is "通讯技术专家"), it can act as a long-lived bridge between AgentWire and Claude Code:

```
Claude Code session
   ↓ (Claude uses Bash tool to call agentwire client)
AgentWire gateway (CORE)
   ↓ HTTP
silk-thread agent (OpenClaw)
   ↓ (routes to other agents as needed)
Other peers (QwenPaw / Hermes / OpenClaw agents)
```

The `silk-thread` agent can persist context across Claude Code sessions by calling `ListTasks` at the start of each session.

## Python helper (if you prefer over bash)

```python
# ~/.claude/skills/agentwire/client.py
import os, json, urllib.request

def send(text: str) -> dict:
    url = os.environ["AGENTWIRE_URL"] + "/a2a/jsonrpc"
    payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "msg-001",
                "role": "ROLE_USER",
                "parts": [{"type": "text", "text": text}],
            },
            "configuration": {"returnImmediately": False},
        },
    }
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['AGENTWIRE_TOKEN']}",
            "A2A-Version": "1.0",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode(),
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
```

Use from Claude Code's Bash tool:

```bash
source ~/.claude/agentwire.env
python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/skills/agentwire'); from client import send; import json; print(json.dumps(send('hello'), indent=2))"
```

## Caveats

- The Bash tool blocks the session for the duration of the HTTP call. For long-running tasks, use background mode.
- `AGENTWIRE_TOKEN` in the env is visible to any tool the LLM calls — do not put the literal token in any prompt that flows through the LLM. The helper script reads it from env so it never appears in the LLM context.

## See also

- [SKILL.md](SKILL.md)
- [INTEGRATION_Generic.md](INTEGRATION_Generic.md)
- [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md)
