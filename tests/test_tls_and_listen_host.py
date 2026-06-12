import ssl
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import start


def test_arg_parser_uses_core_listen_host_env(monkeypatch):
    monkeypatch.setenv("CORE_LISTEN_HOST", "0.0.0.0")
    parser = start.build_arg_parser()

    args = parser.parse_args([])

    assert args.host == "0.0.0.0"


def test_arg_parser_cli_host_overrides_env(monkeypatch):
    monkeypatch.setenv("CORE_LISTEN_HOST", "0.0.0.0")
    parser = start.build_arg_parser()

    args = parser.parse_args(["--host", "127.0.0.1"])

    assert args.host == "127.0.0.1"


def test_arg_parser_uses_core_listen_port_env(monkeypatch):
    monkeypatch.setenv("CORE_LISTEN_PORT", "18888")
    parser = start.build_arg_parser()

    args = parser.parse_args([])

    assert args.port == 18888


def test_arg_parser_uses_agentwire_token_file_env(monkeypatch):
    monkeypatch.setenv("AGENTWIRE_TOKEN_FILE", "/run/secrets/a2a-token.txt")
    parser = start.build_arg_parser()

    args = parser.parse_args([])

    assert args.token_file == "/run/secrets/a2a-token.txt"


def test_tls_args_must_be_supplied_together():
    with pytest.raises(SystemExit):
        start.build_ssl_context("cert.pem", "")
    with pytest.raises(SystemExit):
        start.build_ssl_context("", "key.pem")


def test_tls_args_absent_returns_none():
    assert start.build_ssl_context("", "") is None


def test_tls_args_create_ssl_context(monkeypatch):
    calls = {}

    class FakeContext:
        def load_cert_chain(self, certfile, keyfile):
            calls["certfile"] = certfile
            calls["keyfile"] = keyfile

    monkeypatch.setattr(ssl, "create_default_context", lambda purpose: FakeContext())

    context = start.build_ssl_context("cert.pem", "key.pem")

    assert context is not None
    assert calls == {"certfile": "cert.pem", "keyfile": "key.pem"}
