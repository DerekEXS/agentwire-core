import asyncio
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import start
from history import HistoryManager


class _FakeRequest:
    remote = "127.0.0.1"

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


def test_message_send_persists_message_metadata(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    start.HISTORY_CONFIG = {"enabled": True, "context_rounds": 0}
    start.WORKFLOW_HOOK_CONFIG = None
    gateway = start.A2AGateway(auth_token="")
    metadata = {
        "workflow_pointer": {
            "workflow_file": "00_初梦工作流.yaml",
            "current_step": "step_5",
            "next_action": "review",
        }
    }

    response = asyncio.run(gateway._handle_message_send(1, {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "test metadata v1.4.7"}],
            "metadata": metadata,
        }
    }))

    assert response.status == 200
    peer = start.HISTORY.list_peers()[0]
    messages = start.HISTORY.list_messages(peer["uuid"])["messages"]
    assert messages[0]["metadata"] == metadata


def test_rest_message_send_persists_message_metadata(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    start.HISTORY_CONFIG = {"enabled": True, "context_rounds": 0}
    start.WORKFLOW_HOOK_CONFIG = None
    gateway = start.A2AGateway(auth_token="")
    metadata = {"workflow_pointer": {"current_step": "step_5"}}

    response = asyncio.run(gateway._handle_rest_send(_FakeRequest({
        "message": {
            "parts": [{"type": "text", "text": "rest metadata"}],
            "metadata": metadata,
        }
    })))

    assert response.status == 200
    peer = start.HISTORY.list_peers()[0]
    messages = start.HISTORY.list_messages(peer["uuid"])["messages"]
    assert messages[0]["metadata"] == metadata
