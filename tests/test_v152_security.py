import asyncio
import json
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


def test_metrics_endpoint_requires_auth(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="secret")

    request = type("R", (), {"headers": {}, "remote": "127.0.0.1"})()
    response = asyncio.run(gateway._handle_metrics(request))
    assert response.status == 401


def test_metrics_endpoint_returns_200_with_token(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="secret")

    request = type("R", (), {"headers": {"Authorization": "Bearer secret"}, "remote": "127.0.0.1"})()
    response = asyncio.run(gateway._handle_metrics(request))
    assert response.status == 200


def test_token_file_logging_redacts_absolute_path(tmp_path, caplog):
    secret_token = "agentwire-token-fixture-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    token_file = tmp_path / "fixture-token.txt"
    token_file.write_text(secret_token + "\n", encoding="utf-8")
    import logging
    caplog.set_level(logging.INFO, logger="agentwire")
    start.check_token_file_hygiene(str(token_file))
    logs = "\n".join(r.getMessage() for r in caplog.records)
    # v1.5.2: warning must not echo the absolute path (e.g. /tmp/pytest-...)
    # or the token contents; basename is fine.
    assert secret_token not in logs
    for record in caplog.records:
        msg = record.getMessage()
        assert "/pytest-of-" not in msg
        assert "/tmp/" not in msg


def test_workflow_hook_refuses_disallowed_command(tmp_path, monkeypatch):
    start.HISTORY = HistoryManager(str(tmp_path))
    start.HISTORY_CONFIG = {"enabled": True, "context_rounds": 0}
    start.WORKFLOW_HOOK_CONFIG = {
        "enabled": True,
        "openclaw_path": "/bin/echo",
        "agent_id": "main",
        "workflow_path": str(tmp_path),
        "trigger_keywords": ["project:", "scenes:"],
        "trigger_min_lines": 1,
        "timeout": 5,
        "allowed_commands": ["openclaw"],
        "allowed_paths": [str(tmp_path)],
    }
    text = "project: p\nscenes: s\n"
    result = asyncio.run(start.trigger_workflow_if_match(text, context_id="ctx"))
    assert result["triggered"] is False
    assert "not in allowed" in result["reason"]


def test_history_export_page_returns_consistent_envelope(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    start.HISTORY.import_messages("peer", [
        {"role": "inbound", "parts": [{"type": "text", "text": "x"}]}
    ])

    response = start.A2AGateway(auth_token="")._handle_messages_export(1, {
        "peer_uuid": "peer",
        "format": "jsonl",
        "limit": 50,
    })
    body = _json_body(response)

    assert response.status == 200
    body = _json_body(response)["result"]
    for key in ("format", "content", "limit", "offset", "total_count", "has_more"):
        assert key in body


def test_message_log_summary_hashes_context_id():
    digest = start._message_log_summary("hello", peer="ctx-secret-1234567890")
    assert "ctx-secret-1234567890" not in digest
    assert "len=" in digest
    assert "hash=" in digest


def test_demo_tokens_replaced_in_documentation():
    readme = Path(__file__).resolve().parents[1] / "README.md"
    readme_cn = Path(__file__).resolve().parents[1] / "README_CN.md"
    status = Path(__file__).resolve().parents[1] / "STATUS_v1.4.3.md"
    skill = Path(__file__).resolve().parents[1] / "skill"
    paths = [readme, readme_cn, status]
    if skill.exists():
        for md in skill.rglob("*.md"):
            paths.append(md)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789012345" not in text, f"demo token leaked: {path}"


def test_history_server_start_has_no_dead_export_duplicate():
    source = Path(__file__).resolve().parents[1] / "server" / "history.py"
    text = source.read_text(encoding="utf-8")
    assert text.count("def export_page(") == 1


def test_env_max_limit_constant_documented_near_definition():
    source = Path(__file__).resolve().parents[1] / "server" / "start.py"
    text = source.read_text(encoding="utf-8")
    idx_export = text.find("EXPORT_DEFAULT_LIMIT")
    idx_env = text.find("EXPORT_MAX_LIMIT")
    assert idx_export != -1
    assert idx_env != -1


def test_plugin_manifest_schema_includes_bind_host_and_auth_token():
    manifest = Path(__file__).resolve().parents[1] / "plugin" / "openclaw.plugin.json"
    if not manifest.exists():
        pytest.skip("plugin manifest absent")
    text = manifest.read_text(encoding="utf-8")
    assert "bindHost" in text
    assert "authToken" in text
