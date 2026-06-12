import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import start
from history import HistoryManager


def test_messages_import_jsonrpc_persists_batch(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="")

    response = gateway._handle_messages_import(1, {
        "peer_uuid": "peer-jsonrpc-import",
        "messages": [
            {"role": "user", "parts": [{"type": "text", "text": "hello"}], "metadata": {"source": "import"}},
            {"role": "agent", "parts": [{"type": "text", "text": "reply"}]},
        ],
    })

    assert response.status == 200
    messages = start.HISTORY.list_messages("peer-jsonrpc-import", limit=10)["messages"]
    assert len(messages) == 2
    assert messages[0]["metadata"] == {"source": "import"}


def test_messages_import_jsonrpc_requires_peer_uuid_and_messages(tmp_path):
    start.HISTORY = HistoryManager(str(tmp_path))
    gateway = start.A2AGateway(auth_token="")

    missing_peer = gateway._handle_messages_import(1, {"messages": []})
    missing_messages = gateway._handle_messages_import(1, {"peer_uuid": "p"})

    assert missing_peer.status == 400
    assert missing_messages.status == 400
