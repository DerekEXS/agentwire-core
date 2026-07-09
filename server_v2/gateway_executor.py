"""CORE v2.0 Gateway Executor — implements a2a-sdk AgentExecutor interface.

Receives messages via the standard A2A request flow, routes to target
agents, dispatches via OpenClaw Gateway RPC or direct A2A HTTP, and
publishes Task/Message events back through the event queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import aiohttp
import yaml

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from .agent_router import AgentRouter

log = logging.getLogger("agentwire.executor")


def _now_timestamp():
    from google.protobuf.timestamp_pb2 import Timestamp
    import time
    ts = Timestamp()
    ts.FromNanoseconds(int(time.time() * 1_000_000_000))
    return ts


class GatewayExecutor(AgentExecutor):
    """A2A Gateway AgentExecutor — routes and dispatches messages.

    Implements the a2a-sdk AgentExecutor interface. Each inbound
    message flows through: route → dispatch → collect → publish.
    """

    def __init__(
        self,
        router: AgentRouter | None = None,
        openclaw_gateway_url: str | None = None,
        openclaw_token: str | None = None,
        config_path: str | None = None,
    ):
        self._router = router or AgentRouter(config_path=config_path)
        self._openclaw_url = openclaw_gateway_url or os.environ.get(
            "OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789"
        )
        self._openclaw_token = openclaw_token or os.environ.get("OPENCLAW_TOKEN", "")
        self._peers: dict[str, dict] = {}
        if config_path:
            self._load_peer_config(config_path)

    def _load_peer_config(self, config_path: str) -> None:
        """Load peer configurations from YAML."""
        path = Path(config_path)
        if not path.exists():
            return
        try:
            with open(path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            peers = cfg.get("peers", {})
            for name, info in peers.items():
                if isinstance(info, dict):
                    # Load token from token_file path if specified
                    token_file = info.get("token_file")
                    if token_file:
                        try:
                            with open(token_file, "r") as tf:
                                info["resolved_token"] = tf.read().strip()
                        except OSError:
                            pass
                    self._peers[name] = info
            log.info("loaded %d peer configurations", len(self._peers))
        except Exception as e:
            log.error("failed to load peer config: %s", e)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute gateway logic for an inbound message.

        1. Extract message text and metadata
        2. Route to target agent
        3. Dispatch message to agent
        4. Collect response and publish events
        """
        task_id = context.task_id or uuid.uuid4().hex[:12]
        context_id = context.context_id or ""

        user_text = context.get_user_input()
        metadata = context.metadata
        message = context.message

        log.info("gateway execute: task=%s context=%s text_len=%d", task_id, context_id, len(user_text))

        # Publish initial Task
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.TASK_STATE_WORKING,
                timestamp=_now_timestamp(),
            ),
        )
        await event_queue.enqueue_event(task)

        # Route
        result = self._router.route(text=user_text, metadata=metadata)
        log.info("routed to agent=%s peer=%s (rule=%s)", result.agent_id, result.peer, result.rule_name)

        # Dispatch to target agent
        try:
            response_text = await self._dispatch_to_agent(
                agent_id=result.agent_id,
                peer=result.peer,
                text=user_text,
                metadata=metadata,
                context_id=context_id,
                task_id=task_id,
            )
        except Exception as e:
            log.exception("dispatch failed for task %s: %s", task_id, e)
            await event_queue.enqueue_event(TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_FAILED,
                    message=Message(
                        message_id=uuid.uuid4().hex[:12],
                        role=Role.ROLE_AGENT,
                        parts=[Part(text=f"Dispatch failed: {e}")],
                    ),
                    timestamp=_now_timestamp(),
                ),
            ))
            return

        # Publish completion (task mode: message embedded in status update)
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.TASK_STATE_COMPLETED,
                message=Message(
                    message_id=uuid.uuid4().hex[:12],
                    context_id=context_id,
                    task_id=task_id,
                    role=Role.ROLE_AGENT,
                    parts=[Part(text=response_text)],
                ),
                timestamp=_now_timestamp(),
            ),
        ))

    async def _dispatch_to_agent(
        self,
        agent_id: str,
        peer: str,
        text: str,
        metadata: dict | None,
        context_id: str,
        task_id: str,
    ) -> str:
        """Dispatch message to target agent.

        For local OpenClaw agents, uses Gateway RPC (WebSocket).
        For remote A2A peers, uses standard A2A HTTP message/send.
        """
        # Try OpenClaw Gateway RPC first for local agents
        if peer == "openclaw" or peer == self._peers.get("openclaw", {}).get("url", ""):
            return await self._dispatch_via_openclaw(agent_id, text, metadata, context_id, task_id)

        # Try direct A2A to known peer
        peer_info = self._peers.get(peer, {})
        peer_url = peer_info.get("url", "")
        if peer_url:
            return await self._dispatch_via_a2a(peer_url, agent_id, text, metadata, context_id, task_id)

        # For unknown peers, return routing info as response (passthrough for CUE)
        log.warning("no dispatch target for peer=%s agent=%s — returning passthrough", peer, agent_id)
        return (
            f"[Gateway routed to agent={agent_id} peer={peer}]\n"
            f"Message: {text[:500]}\n"
            f"Task: {task_id}\n"
            f"Context: {context_id}"
        )

    async def _dispatch_via_openclaw(
        self,
        agent_id: str,
        text: str,
        metadata: dict | None,
        context_id: str,
        task_id: str,
    ) -> str:
        """Dispatch to an OpenClaw agent via Gateway RPC.

        Uses the OpenClaw gateway's HTTP API to send a message
        and wait for the agent's response.
        """
        payload = {
            "agentId": agent_id,
            "message": text,
            "sessionKey": context_id or task_id,
            "deliver": False,
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                if self._openclaw_token:
                    headers["Authorization"] = f"Bearer {self._openclaw_token}"

                async with session.post(
                    f"{self._openclaw_url}/rpc/agent",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("text", data.get("response", json.dumps(data)))
                    log.warning("OpenClaw dispatch HTTP %d", resp.status)
                    body = await resp.text()
                    return f"OpenClaw agent '{agent_id}' returned HTTP {resp.status}: {body[:500]}"
        except asyncio.TimeoutError:
            return f"OpenClaw agent '{agent_id}' timed out after 300s"
        except aiohttp.ClientError as e:
            return f"OpenClaw agent '{agent_id}' connection error: {e}"

    async def _dispatch_via_a2a(
        self,
        peer_url: str,
        agent_id: str,
        text: str,
        metadata: dict | None,
        context_id: str,
        task_id: str,
    ) -> str:
        """Dispatch to a remote A2A peer via standard SendMessage."""
        # v2.0.2: use per-peer token from resolved config
        peer_info = self._peers.get(peer, {})  # peer is the config key, not agent_id
        peer_token = peer_info.get("resolved_token", self._openclaw_token)

        # Use metadata to pass agentId since A2A standard doesn't have agentId in Message
        send_metadata = dict(metadata or {})
        send_metadata["agentId"] = agent_id

        payload = {
            "jsonrpc": "2.0",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": f"gw-{task_id}",
                    "contextId": context_id,
                    "role": "user",
                    "parts": [{"type": "text", "text": text}],
                    "metadata": send_metadata,
                },
            },
            "id": task_id,
        }

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {peer_token}",
                    "A2A-Version": "1.0",
                }
                async with session.post(
                    f"{peer_url}/a2a/jsonrpc",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("result", {})
                        if "task" in result:
                            task = result["task"]
                            status = task.get("status", {})
                            msg = status.get("message", {})
                            parts = msg.get("parts", [])
                            texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
                            return "\n".join(texts) or json.dumps(result)
                        if "message" in result:
                            parts = result["message"].get("parts", [])
                            texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
                            return "\n".join(texts) or json.dumps(result)
                        return json.dumps(result)
                    return f"Peer {peer_url} returned HTTP {resp.status}"
        except asyncio.TimeoutError:
            return f"Peer {peer_url} timed out after 300s"
        except aiohttp.ClientError as e:
            return f"Peer {peer_url} connection error: {e}"

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel an ongoing task."""
        task_id = context.task_id
        context_id = context.context_id
        if not task_id:
            return
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id or "",
            status=TaskStatus(
                state=TaskState.TASK_STATE_CANCELED,
                timestamp=_now_timestamp(),
            ),
        ))
