#!/usr/bin/env python3
"""
OpenClaw A2A Gateway Adapter
============================
Bridges A2A v1.0 JSON-RPC protocol to OpenClaw's HTTP tool API.

Endpoints (port 18802):
  GET  /.well-known/agent-card.json   - A2A agent card
  POST /a2a/jsonrpc                   - A2A JSON-RPC (SendMessage/GetTask/ListTasks/CancelTask)
  POST /rpc/agent                     - alias for /a2a/jsonrpc (compatibility with CORE/peers)
  GET  /health                        - health probe

A2A methods implemented:
  - SendMessage  -> extracts text, calls OpenClaw /tools/invoke with 'message' tool
  - GetTask      -> returns task from local in-memory + JSONL store
  - ListTasks    -> returns recent tasks
  - CancelTask   -> marks task cancelled

Auth: Bearer token (<a2a-token>, matches peers.openclaw token)

This is the "OpenClaw-side A2A adapter" referenced in:
  /home/AIKali/.openclaw/workspace/skills/agentwire/SKILL.md
  /home/AIKali/.openclaw/workspace/skills/agentwire/APPENDIX_OpenClaw.md
"""

import json
import os
import sys
import time
import uuid
import threading
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

# -----------------------------------------------------------------------------
# Configuration (env-overridable)
# -----------------------------------------------------------------------------
A2A_TOKEN = os.environ.get("A2A_TOKEN", "<a2a-token>")
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://127.0.0.1:18789")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "<gateway-auth-token>")
BIND_HOST = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.environ.get("BIND_PORT", "18802"))
LOG_FILE = os.environ.get("LOG_FILE", "/home/AIKali/.openclaw/a2a-gateway/a2a-gateway.log")
TASK_STORE_FILE = os.environ.get("TASK_STORE_FILE", "/home/AIKali/.openclaw/a2a-gateway/tasks.jsonl")
PROTOCOL_VERSION = "1.0"
AGENT_NAME = "OpenClaw"

# A2A agent card definition (which OpenClaw agents can be invoked)
AGENT_IDS = ["main", "vidhound", "vidforge", "codeanchor", "netdawn", "soulwhisper"]
DEFAULT_AGENT = "main"

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("a2a-gateway")

# -----------------------------------------------------------------------------
# Task store (thread-safe, persistent JSONL)
# -----------------------------------------------------------------------------
_task_lock = threading.Lock()
_tasks: Dict[str, Dict[str, Any]] = {}


def _load_tasks() -> None:
    if not os.path.exists(TASK_STORE_FILE):
        return
    try:
        with open(TASK_STORE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    _tasks[rec["id"]] = rec
                except Exception:
                    pass
        log.info("Loaded %d tasks from %s", len(_tasks), TASK_STORE_FILE)
    except Exception as e:
        log.error("Failed to load task store: %s", e)


def _persist_task(task: Dict[str, Any]) -> None:
    """Append task to JSONL store."""
    try:
        with _task_lock:
            with open(TASK_STORE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(task, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error("Failed to persist task: %s", e)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _new_task(message: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())
    context_id = message.get("contextId") or str(uuid.uuid4())
    text = _extract_text(message)
    return {
        "id": task_id,
        "contextId": context_id,
        "status": {
            "state": "TASK_STATE_SUBMITTED",
            "message": {
                "messageId": message.get("messageId", str(uuid.uuid4())),
                "contextId": context_id,
                "taskId": task_id,
                "role": "ROLE_USER",
                "parts": [{"type": "text", "text": text}],
            },
            "timestamp": _now_iso(),
        },
        "history": [
            {
                "messageId": message.get("messageId", str(uuid.uuid4())),
                "contextId": context_id,
                "role": "ROLE_USER",
                "parts": [{"type": "text", "text": text}],
            }
        ],
        "artifacts": [],
        "metadata": {
            "agent_id": agent_id,
            "received_at": _now_iso(),
            "openclaw_dispatched": False,
        },
    }


def _extract_text(message: Dict[str, Any]) -> str:
    parts = message.get("parts") or []
    chunks: List[str] = []
    for p in parts:
        if isinstance(p, dict):
            t = p.get("text")
            if isinstance(t, str):
                chunks.append(t)
            elif p.get("type") == "text" and isinstance(p.get("text"), str):
                chunks.append(p["text"])
        elif isinstance(p, str):
            chunks.append(p)
    if not chunks:
        return ""
    return "\n".join(chunks)


def _resolve_agent(message: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Determine target agent from message metadata, params, or default."""
    md = message.get("metadata") or {}
    candidates: List[str] = []
    for key in ("agent_id", "agentId", "peer", "to"):
        v = md.get(key) or params.get(key)
        if isinstance(v, str) and v:
            candidates.append(v)
    for c in candidates:
        if c in AGENT_IDS:
            return c
        # Treat "main" / "openclaw" / "default" as main
        if c.lower() in ("main", "openclaw", "default"):
            return "main"
    return DEFAULT_AGENT


# -----------------------------------------------------------------------------
# OpenClaw dispatch (best-effort, fire-and-forget)
# -----------------------------------------------------------------------------
def _dispatch_to_openclaw(task: Dict[str, Any], agent_id: str, text: str) -> None:
    """Call OpenClaw /tools/invoke with the message tool. Updates task state."""
    session_key = f"agent:{agent_id}:main"
    body = {
        "tool": "message",
        "args": {
            "action": "send",
            "sessionKey": session_key,
            "text": text,
        },
    }
    req = urllib.request.Request(
        f"{OPENCLAW_URL}/tools/invoke",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENCLAW_TOKEN}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw)
            if payload.get("ok"):
                task["status"]["state"] = "TASK_STATE_WORKING"
                task["metadata"]["openclaw_dispatched"] = True
                task["metadata"]["openclaw_response"] = str(payload.get("result"))[:500]
                log.info("Dispatched task %s to %s OK", task["id"], agent_id)
            else:
                err = payload.get("error") or {}
                task["status"]["state"] = "TASK_STATE_FAILED"
                task["metadata"]["openclaw_error"] = err.get("message", "unknown")
                log.warning("OpenClaw rejected task %s: %s", task["id"], err)
    except urllib.error.HTTPError as e:
        task["status"]["state"] = "TASK_STATE_FAILED"
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        task["metadata"]["openclaw_error"] = f"HTTP {e.code}: {body_text}"
        log.warning("OpenClaw HTTP error for task %s: %s %s", task["id"], e.code, body_text[:200])
    except Exception as e:
        task["status"]["state"] = "TASK_STATE_FAILED"
        task["metadata"]["openclaw_error"] = f"{type(e).__name__}: {e}"
        log.exception("OpenClaw dispatch exception for task %s", task["id"])


# -----------------------------------------------------------------------------
# JSON-RPC helpers
# -----------------------------------------------------------------------------
def _rpc_ok(id_: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _rpc_err(id_: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def _validate_request(payload: Dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return "Request must be a JSON object"
    if payload.get("jsonrpc") != "2.0":
        return "jsonrpc field must be '2.0'"
    if "method" not in payload or not isinstance(payload["method"], str):
        return "method field required (string)"
    return None


# -----------------------------------------------------------------------------
# Method handlers
# -----------------------------------------------------------------------------
def handle_send_message(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    message = params.get("message")
    if not isinstance(message, dict):
        return _rpc_err(req_id, -32602, "Invalid params: 'message' object required")
    agent_id = _resolve_agent(message, params)
    text = _extract_text(message)
    if not text:
        return _rpc_err(req_id, -32602, "Invalid params: no text in message.parts")

    task = _new_task(message, agent_id)
    _tasks[task["id"]] = task
    _persist_task(task)

    # Fire-and-forget dispatch to OpenClaw (don't block the JSON-RPC response)
    def _bg() -> None:
        try:
            _dispatch_to_openclaw(task, agent_id, text)
            # Persist updated state
            _persist_task(task)
        except Exception as e:
            log.exception("Background dispatch failed: %s", e)

    threading.Thread(target=_bg, daemon=True).start()

    return _rpc_ok(req_id, {"task": task})


def handle_get_task(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    task_id = params.get("id") or params.get("taskId")
    if not isinstance(task_id, str):
        return _rpc_err(req_id, -32602, "Invalid params: 'id' required")
    task = _tasks.get(task_id)
    if not task:
        return _rpc_err(req_id, -32001, f"Task not found: {task_id}")
    return _rpc_ok(req_id, {"task": task})


def handle_list_tasks(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    limit = int(params.get("limit", 20))
    limit = max(1, min(100, limit))
    items = sorted(_tasks.values(), key=lambda t: t.get("metadata", {}).get("received_at", ""), reverse=True)
    return _rpc_ok(req_id, {"tasks": items[:limit], "count": len(items)})


def handle_cancel_task(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    task_id = params.get("id") or params.get("taskId")
    if not isinstance(task_id, str):
        return _rpc_err(req_id, -32602, "Invalid params: 'id' required")
    task = _tasks.get(task_id)
    if not task:
        return _rpc_err(req_id, -32001, f"Task not found: {task_id}")
    task["status"]["state"] = "TASK_STATE_CANCELLED"
    task["status"]["timestamp"] = _now_iso()
    _persist_task(task)
    return _rpc_ok(req_id, {"task": task})


METHODS = {
    "SendMessage": handle_send_message,
    "sendMessage": handle_send_message,
    "message/send": handle_send_message,
    "GetTask": handle_get_task,
    "getTask": handle_get_task,
    "tasks/get": handle_get_task,
    "ListTasks": handle_list_tasks,
    "listTasks": handle_list_tasks,
    "tasks/list": handle_list_tasks,
    "CancelTask": handle_cancel_task,
    "cancelTask": handle_cancel_task,
    "tasks/cancel": handle_cancel_task,
}


# -----------------------------------------------------------------------------
# HTTP handler
# -----------------------------------------------------------------------------
class A2AHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        log.info("%s - %s", self.address_string(), fmt % args)

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            self._send_json(401, {"error": "unauthorized", "message": "Bearer token required"})
            return False
        token = auth[7:].strip()
        if token != A2A_TOKEN:
            self._send_json(401, {"error": "unauthorized", "message": "Invalid token"})
            return False
        return True

    def _send_json(self, status: int, body: Any) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, A2A-Version")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, A2A-Version")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "openclaw-a2a-gateway", "version": PROTOCOL_VERSION})
            return
        if self.path == "/.well-known/agent-card.json" or self.path == "/.well-known/agent.json":
            card = {
                "protocolVersion": PROTOCOL_VERSION,
                "name": AGENT_NAME,
                "description": "OpenClaw A2A Gateway — bridges A2A v1.0 to OpenClaw multi-agent runtime",
                "url": f"http://127.0.0.1:{BIND_PORT}",
                "version": "1.0.0",
                "capabilities": {
                    "streaming": False,
                    "pushNotifications": False,
                    "extendedAgentCard": False,
                },
                "defaultInputModes": ["text"],
                "defaultOutputModes": ["text"],
                "skills": [
                    {"id": a, "name": a, "description": f"OpenClaw agent: {a}"} for a in AGENT_IDS
                ],
                "agents": [{"id": a, "name": a} for a in AGENT_IDS],
            }
            self._send_json(200, card)
            return
        self._send_json(404, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:
        if self.path not in ("/a2a/jsonrpc", "/rpc/agent"):
            self._send_json(404, {"error": "not_found", "path": self.path})
            return
        if not self._check_auth():
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            self._send_json(400, {"error": "empty_body"})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json(200, _rpc_err(None, -32700, f"Parse error: {e}"))
            return
        err = _validate_request(payload)
        if err:
            self._send_json(200, _rpc_err(payload.get("id"), -32600, err))
            return
        method = payload["method"]
        req_id = payload.get("id")
        params = payload.get("params") or {}
        handler = METHODS.get(method)
        if not handler:
            self._send_json(200, _rpc_err(req_id, -32601, f"Method not found: {method}"))
            return
        try:
            result = handler(req_id, params)
            self._send_json(200, result)
        except Exception as e:
            log.exception("Handler %s crashed", method)
            self._send_json(200, _rpc_err(req_id, -32603, f"Internal error: {type(e).__name__}: {e}"))


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
def main() -> int:
    _load_tasks()
    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), A2AHandler)
    log.info("OpenClaw A2A Gateway listening on %s:%d (proto=%s, openclaw=%s)",
             BIND_HOST, BIND_PORT, PROTOCOL_VERSION, OPENCLAW_URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
