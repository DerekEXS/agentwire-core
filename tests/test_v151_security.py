import asyncio
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import start
from history import HistoryManager


@pytest.fixture(autouse=True)
def _reset_core_globals():
    old_history = start.HISTORY
    old_config = start.HISTORY_CONFIG
    old_workflow = start.WORKFLOW_HOOK_CONFIG
    yield
    start.HISTORY = old_history
    start.HISTORY_CONFIG = old_config
    start.WORKFLOW_HOOK_CONFIG = old_workflow


def _json_body(response):
    return json.loads(response.text)


def test_message_send_logs_length_and_hash_not_plaintext(tmp_path, caplog):
    secret_text = "sk-THIS-SHOULD-NOT-APPEAR-IN-LOGS"
    start.HISTORY = HistoryManager(str(tmp_path))
    start.HISTORY_CONFIG = {"enabled": True, "context_rounds": 0}
    start.WORKFLOW_HOOK_CONFIG = None
    gateway = start.A2AGateway(auth_token="")
    caplog.set_level(logging.INFO, logger="agentwire")

    response = asyncio.run(gateway._handle_message_send(1, {
        "message": {"parts": [{"type": "text", "text": secret_text}]}
    }))

    assert response.status == 200
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_text not in logs
    assert "len=" in logs
    assert "hash=" in logs


def test_messages_import_rejects_more_than_100_messages(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="")

    response = gateway._handle_messages_import(1, {
        "peer_uuid": "peer",
        "messages": [{"parts": []} for _ in range(101)],
    })

    assert response.status == 400
    assert "too many messages" in _json_body(response)["error"]["message"]


def test_messages_import_rejects_single_message_over_64kb(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="")

    response = gateway._handle_messages_import(1, {
        "peer_uuid": "peer",
        "messages": [{"parts": [{"type": "text", "text": "x" * 65537}]}],
    })

    assert response.status == 400
    assert "too large" in _json_body(response)["error"]["message"]


def test_messages_export_paginates_and_reports_has_more(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="")
    start.HISTORY.import_messages("peer", [
        {"role": "inbound", "parts": [{"type": "text", "text": str(i)}]}
        for i in range(75)
    ])

    response = gateway._handle_messages_export(1, {
        "peer_uuid": "peer",
        "format": "jsonl",
        "limit": 50,
        "offset": 0,
    })
    body = _json_body(response)["result"]

    assert response.status == 200
    assert body["total_count"] == 75
    assert body["has_more"] is True
    assert len([line for line in body["content"].splitlines() if line.strip()]) == 50


def test_messages_export_rejects_limit_over_200(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="")

    response = gateway._handle_messages_export(1, {
        "peer_uuid": "peer",
        "format": "jsonl",
        "limit": 201,
    })

    assert response.status == 400
    assert "limit" in _json_body(response)["error"]["message"]


def test_typescript_plugin_source_enforces_inbound_auth_and_loopback_bind():
    source = Path(__file__).resolve().parents[1] / "plugin" / "src" / "index.ts"
    text = source.read_text(encoding="utf-8")

    assert "bindHost" in text
    assert "127.0.0.1" in text
    assert "isAuthorized" in text
    assert "Bearer " in text
    assert "res.writeHead(401" in text
    assert "server.listen(config.port!, config.bindHost" in text
