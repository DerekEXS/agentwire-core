import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from history import HistoryManager


def test_import_messages_creates_new_peer_with_sequential_rounds_and_metadata(tmp_path):
    history = HistoryManager(str(tmp_path))

    result = history.import_messages(
        "peer-import-new",
        [
            {"role": "user", "parts": [{"type": "text", "text": "hello 1"}], "metadata": {"source": "import"}},
            {"role": "agent", "parts": [{"type": "text", "text": "hello 2"}]},
            {"role": "user", "parts": [{"type": "text", "text": "hello 3"}], "metadata": {"n": 3}},
        ],
    )

    assert result == {
        "imported": 3,
        "peer_uuid": "peer-import-new",
        "first_round": 1,
        "last_round": 3,
    }
    messages = history.list_messages("peer-import-new", limit=10)["messages"]
    assert [m["round"] for m in messages] == [1, 2, 3]
    assert [m["role"] for m in messages] == ["user", "agent", "user"]
    assert messages[0]["metadata"] == {"source": "import"}
    assert messages[1]["metadata"] is None
    assert messages[2]["metadata"] == {"n": 3}


def test_import_messages_appends_after_existing_rounds(tmp_path):
    history = HistoryManager(str(tmp_path))
    peer_uuid, _ = history.record_outbound("ctx-existing", "out-1", [{"type": "text", "text": "existing"}])

    result = history.import_messages(
        peer_uuid,
        [
            {"role": "user", "parts": [{"type": "text", "text": "imported 1"}]},
            {"role": "user", "parts": [{"type": "text", "text": "imported 2"}]},
        ],
    )

    assert result["first_round"] == 2
    assert result["last_round"] == 3
    messages = history.list_messages(peer_uuid, limit=10)["messages"]
    assert [m["round"] for m in messages] == [1, 2, 3]


def test_import_messages_redacts_parts_and_metadata(tmp_path):
    history = HistoryManager(str(tmp_path))
    history.set_patterns([
        {"name": "token", "regex": r"secret-token-[A-Za-z0-9]+", "replacement": "<REDACTED_TOKEN>"},
    ])

    history.import_messages(
        "peer-redact",
        [{
            "role": "user",
            "parts": [{"type": "text", "text": "body secret-token-ABC123"}],
            "metadata": {"token": "secret-token-ABC123"},
        }],
    )

    message = history.list_messages("peer-redact")["messages"][0]
    assert message["parts"][0]["text"] == "body <REDACTED_TOKEN>"
    assert message["metadata"]["token"] == "<REDACTED_TOKEN>"
