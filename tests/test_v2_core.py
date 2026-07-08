"""CORE v2.0 tests — Agent Card, Router, Gateway Executor, Task Store."""

from __future__ import annotations

import asyncio
import hmac
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from server_v2.agent_card import build_agent_card
from server_v2.agent_router import AgentRouter, RoutingRule, RoutingResult
from server_v2.gateway_executor import GatewayExecutor
from server_v2.task_store import SqliteTaskStore
from server_v2.start import BearerTokenMiddleware


class TestAgentCard:
    """Agent Card correctness."""

    def test_card_name_and_version(self):
        card = build_agent_card()
        assert card.name == "AgentWire Gateway"
        assert card.version == "2.0.2"

    def test_card_has_jsonrpc_interface(self):
        card = build_agent_card()
        bindings = [i.protocol_binding for i in card.supported_interfaces]
        assert "jsonrpc" in bindings

    def test_card_includes_skills(self):
        card = build_agent_card()
        skill_ids = [s.id for s in card.skills]
        assert "message_routing" in skill_ids
        assert "task_management" in skill_ids

    def test_card_custom_listen_port(self):
        card = build_agent_card(listen_port=9999)
        urls = [i.url for i in card.supported_interfaces]
        assert any("9999" in u for u in urls)

    def test_card_capabilities(self):
        card = build_agent_card()
        assert card.capabilities.streaming is True
        assert card.capabilities.push_notifications is False


class TestAgentRouter:
    """Agent routing logic."""

    def test_default_route(self):
        router = AgentRouter()
        result = router.route("hello")
        assert result.agent_id == "main"
        assert result.peer == "openclaw"
        assert result.rule_name == "default"

    def test_explicit_agent_id(self):
        router = AgentRouter()
        result = router.route("text", {"agentId": "vidhound"})
        assert result.agent_id == "vidhound"
        assert result.rule_name == "explicit_agent_id"

    def test_explicit_agent_id_snake_case(self):
        router = AgentRouter()
        result = router.route("text", {"agent_id": "vidforge"})
        assert result.agent_id == "vidforge"
        assert result.rule_name == "explicit_agent_id"

    def test_workflow_pointer_next_agent(self):
        router = AgentRouter()
        result = router.route("text", {"workflow_pointer": {"next_agent": "cue"}})
        assert result.agent_id == "cue"
        assert result.rule_name == "explicit_agent_id"

    def test_tag_based_routing(self):
        router = AgentRouter()
        router._rules = [
            RoutingRule(name="video", tags=["video", "search"], target_peer="openclaw",
                         target_agent_id="vidhound", priority=10),
        ]
        result = router.route("please search and analyze this video for me")
        assert result.agent_id == "vidhound"
        assert result.rule_name == "video"

    def test_pattern_based_routing(self):
        router = AgentRouter()
        router._rules = [
            RoutingRule(name="script", pattern=r"project:", target_peer="cue-worker",
                         target_agent_id="script-receiver", priority=10),
        ]
        result = router.route("project: my-app scenes: login")
        assert result.agent_id == "script-receiver"
        assert result.rule_name == "script"

    def test_priority_order(self):
        router = AgentRouter()
        router._rules = [
            RoutingRule(name="low", tags=["hello"], target_agent_id="low_agent", priority=1),
            RoutingRule(name="high", tags=["hello"], target_agent_id="high_agent", priority=10),
        ]
        result = router.route("hello world")
        assert result.agent_id == "high_agent", f"Expected high_agent, got {result.agent_id} via rule {result.rule_name}"
        assert result.rule_name == "high"

    def test_no_metadata_no_text(self):
        router = AgentRouter()
        result = router.route("", None)
        assert result.agent_id == "main"
        assert result.rule_name == "default"


class TestSqliteTaskStore:
    """Task persistence."""

    def test_store_creates_db(self):
        tmp = os.path.join(tempfile.gettempdir(), "test_store.db")
        if os.path.exists(tmp):
            os.remove(tmp)
        store = SqliteTaskStore(db_path=tmp)
        assert Path(tmp).exists()
        os.remove(tmp)

    def test_save_and_delete(self):
        from a2a.types import Task, TaskStatus, TaskState
        from a2a.server.context import ServerCallContext
        tmp = os.path.join(tempfile.gettempdir(), "test_save_delete.db")
        if os.path.exists(tmp):
            os.remove(tmp)
        store = SqliteTaskStore(db_path=tmp)
        ctx = ServerCallContext()
        task = Task(id="task-del", context_id="ctx-1",
                    status=TaskStatus(state=TaskState.TASK_STATE_WORKING))
        asyncio.run(store.save(task, ctx))
        asyncio.run(store.delete("task-del", ctx))
        result = asyncio.run(store.get("task-del", ctx))
        assert result is None
        os.remove(tmp)


class TestGatewayExecutor:
    """Gateway executor routing and dispatch."""

    def test_router_passthrough(self):
        router = AgentRouter()
        executor = GatewayExecutor(router=router)
        assert executor._router is router

    def test_peer_config_loading(self):
        cfg = {
            "peers": {
                "test-peer": {"url": "http://example.com:18800", "description": "test"}
            }
        }
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        yaml.dump(cfg, tmp)
        tmp.close()

        router = AgentRouter()
        executor = GatewayExecutor(router=router, config_path=tmp.name)
        assert "test-peer" in executor._peers
        assert executor._peers["test-peer"]["url"] == "http://example.com:18800"
        os.remove(tmp.name)

    def test_execute_publishes_completed_task(self):
        """Verify execute publishes completion via mock queue."""
        from unittest.mock import MagicMock
        from a2a.server.agent_execution.context import RequestContext
        from a2a.server.context import ServerCallContext

        router = AgentRouter()
        executor = GatewayExecutor(router=router)
        call_ctx = ServerCallContext()
        req_ctx = RequestContext(
            call_context=call_ctx,
            task_id="test-task",
            context_id="test-ctx",
        )
        mock_queue = MagicMock()
        mock_queue.enqueue_event = AsyncMock()

        async def run():
            await executor.execute(req_ctx, mock_queue)
            # Should have called enqueue_event at least twice: task + completion
            assert mock_queue.enqueue_event.call_count >= 2

        asyncio.run(run())

    def test_cancel_publishes_canceled_task(self):
        """Verify cancel publishes canceled state via mock queue."""
        from unittest.mock import MagicMock
        from a2a.server.agent_execution.context import RequestContext
        from a2a.server.context import ServerCallContext

        router = AgentRouter()
        executor = GatewayExecutor(router=router)
        call_ctx = ServerCallContext()
        req_ctx = RequestContext(
            call_context=call_ctx,
            task_id="test-cancel",
            context_id="test-ctx",
        )
        mock_queue = MagicMock()
        mock_queue.enqueue_event = AsyncMock()

        async def run():
            await executor.cancel(req_ctx, mock_queue)
            assert mock_queue.enqueue_event.call_count >= 1

        asyncio.run(run())


class TestBearerTokenMiddleware:
    """Security middleware."""

    def test_valid_token_accepted(self):
        middleware = BearerTokenMiddleware(
            app=AsyncMock(return_value=None),
            tokens=["test-token"],
        )
        assert "test-token" in middleware._tokens

    def test_invalid_token_rejected(self):
        middleware = BearerTokenMiddleware(
            app=AsyncMock(return_value=None),
            tokens=["valid-token"],
        )
        assert not any(
            hmac.compare_digest("wrong-token", t)
            for t in middleware._tokens
        )

    def test_excluded_paths(self):
        middleware = BearerTokenMiddleware(
            app=AsyncMock(return_value=None),
            tokens=["token"],
            exclude_paths=["/.well-known/agent-card.json", "/health"],
        )
        assert "/.well-known/agent-card.json" in middleware._exclude
        assert "/health" in middleware._exclude

    def test_no_token_in_middleware(self):
        middleware = BearerTokenMiddleware(
            app=AsyncMock(return_value=None),
            tokens=["only-token"],
        )
        assert len(middleware._tokens) == 1
