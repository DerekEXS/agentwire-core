# Integration: QwenPaw

> How to integrate AgentWire with [QwenPaw](https://qwenpaw.io) agents.

## About QwenPaw

QwenPaw is a Python-based agent framework developed by Alibaba. It is similar in spirit to OpenClaw but targets Python-native agents and emphasizes multi-model LLM orchestration. AgentWire works with QwenPaw through its Python A2A client, no special plugin required.

## Architecture

```
┌──────────────────────────────────┐
│      QwenPaw Agent Process       │
│  (Python, your skill code)      │
│                                  │
│  ┌───────────────────────────┐ │
│  │  agentwire Python client  │ │  ← you import this
│  │  (A2A JSON-RPC over HTTP) │ │
│  └───────────────────────────┘ │
└────────────┬─────────────────────┘
             │ HTTP + Bearer token
             ▼
┌──────────────────────────────────┐
│   AgentWire Python A2A Service  │
│   (18800)                        │
└──────────────────────────────────┘
```

## Install

```bash
pip install aiohttp
```

That's it — `aiohttp` is the only A2A dependency. (You can also use `requests` if you prefer sync; the A2A surface is plain HTTP+JSON.)

## Minimal client (5 lines)

```python
import aiohttp, asyncio, os

async def send(text: str) -> dict:
    async with aiohttp.ClientSession() as s:
        r = await s.post(
            "http://127.0.0.1:18800/a2a/jsonrpc",
            headers={
                "Authorization": f"Bearer {os.environ['AGENTWIRE_TOKEN']}",
                "A2A-Version": "1.0",
            },
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": "msg-001",
                        "role": "ROLE_USER",
                        "parts": [{"type": "text", "text": text}],
                    },
                    "configuration": {"returnImmediately": False},
                },
            },
        )
        return await r.json()

asyncio.run(send("hello from QwenPaw"))
```

## QwenPaw skill example

A minimal QwenPaw skill that forwards a user's message to AgentWire and returns the response:

```python
# qwenpaw_skill/agentwire_client.py
import os, aiohttp
from qwenpaw import skill, message  # QwenPaw SDK

AGENTWIRE_URL = os.getenv("AGENTWIRE_URL", "http://127.0.0.1:18800")
AGENTWIRE_TOKEN = os.environ["AGENTWIRE_TOKEN"]
HEADERS = {
    "Authorization": f"Bearer {AGENTWIRE_TOKEN}",
    "A2A-Version": "1.0",
    "Content-Type": "application/json",
}

@skill(name="agentwire_send")
async def agentwire_send(text: str) -> str:
    """Forward `text` to AgentWire and return the reply text."""
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{AGENTWIRE_URL}/a2a/jsonrpc",
            headers=HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
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
            data = await r.json()
    # v2.0: response shape uses task.status.message
    task = data.get("result", {}).get("task", {})
    msg = task.get("status", {}).get("message", {})
    parts = msg.get("parts", []) or data.get("result", {}).get("message", {}).get("parts", [])
    return " ".join(p.get("text", "") for p in parts if p.get("type") == "text")
```

```python
# qwenpaw_skill/handler.py
from .agentwire_client import agentwire_send

@message.handler
async def handle(msg):
    if msg.text.startswith("/aw "):
        reply = await agentwire_send(msg.text[4:])
        return msg.reply(reply)
    return None
```

## Reading recent tasks (v2.0+)

If you want your QwenPaw agent to know its recent task activity:

```python
async def recent_tasks(page_size: int = 5) -> list[dict]:
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"{AGENTWIRE_URL}/a2a/jsonrpc",
            headers={
                "Authorization": f"Bearer {AGENTWIRE_TOKEN}",
                "A2A-Version": "1.0",
            },
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "ListTasks",
                "params": {"pageSize": page_size},
            },
        ) as r:
            data = await r.json()
    return data["result"]["tasks"]
```

## Companion project: `agentwire-cue`

If you want full YAML-driven statechart workflows on top of AgentWire, use [agentwire-cue](https://github.com/DerekEXS/agentwire-cue). It runs as a QwenPaw-compatible Python process and consumes AgentWire's A2A service.

## See also

- [SKILL.md](SKILL.md)
- [INTEGRATION_Generic.md](INTEGRATION_Generic.md)
- [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md)
