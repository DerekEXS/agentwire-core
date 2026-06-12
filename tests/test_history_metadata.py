import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from history import HistoryManager


def test_records_metadata_on_outbound_and_inbound_and_returns_it(tmp_path):
    history = HistoryManager(str(tmp_path))
    metadata = {
        "workflow_pointer": {
            "workflow_file": "00_初梦工作流.yaml",
            "current_step": "step_5",
            "next_action": "review",
        }
    }

    peer_uuid, round_n = history.record_outbound(
        "ctx-metadata",
        "out-1",
        [{"type": "text", "text": "test metadata v1.4.7"}],
        metadata=metadata,
    )
    history.record_inbound(
        peer_uuid,
        "in-1",
        [{"type": "text", "text": "reply"}],
        metadata={"reply_meta": True},
    )

    messages = history.list_messages(peer_uuid)["messages"]
    assert messages[0]["metadata"] == metadata
    assert messages[1]["metadata"] == {"reply_meta": True}
    assert history.get_round(peer_uuid, round_n)[0]["metadata"] == metadata
    exported = [json.loads(line) for line in history.export(peer_uuid, "jsonl").splitlines()]
    assert exported[0]["metadata"] == metadata


def test_records_metadata_null_when_absent(tmp_path):
    history = HistoryManager(str(tmp_path))

    peer_uuid, round_n = history.record_outbound(
        "ctx-no-metadata",
        "out-1",
        [{"type": "text", "text": "without metadata"}],
    )
    history.record_inbound(peer_uuid, "in-1", [{"type": "text", "text": "reply"}])

    messages = history.get_round(peer_uuid, round_n)
    assert messages[0]["metadata"] is None
    assert messages[1]["metadata"] is None


def test_redacts_sensitive_values_in_metadata(tmp_path):
    history = HistoryManager(str(tmp_path))
    history.set_patterns([
        {"name": "token", "regex": r"secret-token-[A-Za-z0-9]+", "replacement": "<REDACTED_TOKEN>"},
    ])

    peer_uuid, _round_n = history.record_outbound(
        "ctx-redact",
        "out-1",
        [{"type": "text", "text": "body secret-token-ABC123"}],
        metadata={
            "workflow_pointer": {"current_step": "step_1"},
            "auth": {"token": "secret-token-ABC123"},
        },
    )

    message = history.list_messages(peer_uuid)["messages"][0]
    assert message["parts"][0]["text"] == "body <REDACTED_TOKEN>"
    assert message["metadata"]["auth"]["token"] == "<REDACTED_TOKEN>"
