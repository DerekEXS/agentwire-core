import logging
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import start


def test_token_hygiene_warns_for_bom_and_crlf_and_loose_permissions(tmp_path, caplog):
    token_file = tmp_path / "token.txt"
    token_file.write_bytes(b"\xef\xbb\xbfTOKEN\r\n")
    token_file.chmod(0o644)
    caplog.set_level(logging.WARNING, logger="agentwire")

    result = start.check_token_file_hygiene(str(token_file))

    assert result["ok"] is False
    assert "utf8_bom" in result["issues"]
    assert "crlf_line_ending" in result["issues"]
    assert "loose_permissions" in result["issues"]
    messages = "\n".join(record.message for record in caplog.records)
    assert "UTF-8 BOM" in messages
    assert "CRLF" in messages
    assert "chmod 600" in messages


def test_token_hygiene_info_for_clean_file(tmp_path, caplog):
    token_file = tmp_path / "token.txt"
    token_file.write_text("TOKEN\n", encoding="ascii", newline="\n")
    token_file.chmod(0o600)
    caplog.set_level(logging.INFO, logger="agentwire")

    result = start.check_token_file_hygiene(str(token_file))

    assert result == {"ok": True, "issues": []}
    assert any("token file health check passed" in record.message for record in caplog.records)
