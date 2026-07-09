#!/usr/bin/env python3
"""AgentWire CORE v2.0 — A2A v1.0 Gateway based on a2a-sdk.

Rewrites the v1.x message-store into a proper A2A gateway with:
  - Standard A2A endpoints (message/send, tasks/get, etc.) via a2a-sdk
  - Agent routing (explicit agentId + rule-based)
  - Task lifecycle management (submitted → working → completed/failed)
  - Agent Card discovery (/.well-known/agent.json + /.well-known/agent-card.json)
  - Bearer token auth, loopback default, TLS support
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import logging
import os
import signal
import ssl
import sys
from pathlib import Path

import yaml
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from a2a.server.events import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.common import DefaultServerCallContextBuilder
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes

from .agent_card import build_agent_card
from .agent_router import AgentRouter
from .gateway_executor import GatewayExecutor
from . import __version__
from .task_store import SqliteTaskStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("agentwire")


# ---------------------------------------------------------------------------
# Bearer token auth middleware
# ---------------------------------------------------------------------------

class BearerTokenMiddleware:
    """Starlette middleware that validates Bearer tokens against configured values.

    Supports multiple tokens loaded from files. Tokens are compared with
    hmac.compare_digest for timing-attack resistance.
    """

    def __init__(self, app, tokens: list[str], exclude_paths: list[str] | None = None):
        self.app = app
        self._tokens = tokens
        self._exclude = set(exclude_paths or [])

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self._exclude or path == "/health" or path.startswith("/.well-known"):
            await self.app(scope, receive, send)
            return

        # Extract Bearer token
        auth_header = ""
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                auth_header = value.decode()
                break

        if not auth_header.startswith("Bearer "):
            await self._unauthorized(send, "Missing Bearer token")
            return

        token = auth_header[7:]
        if not any(hmac.compare_digest(token, t) for t in self._tokens):
            await self._unauthorized(send, "Invalid token")
            return

        await self.app(scope, receive, send)

    async def _unauthorized(self, send, detail: str):
        body = JSONResponse({"error": detail}, status_code=401)
        await body(scope={"type": "http"}, receive=None, send=send)


# ---------------------------------------------------------------------------
# Health & root endpoints
# ---------------------------------------------------------------------------

async def health_endpoint(request: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "agentwire-core", "version": __version__})


async def root_endpoint(request: Request) -> Response:
    return JSONResponse({
        "service": "AgentWire Gateway v2.0",
        "endpoints": {
            "agent_card": "/.well-known/agent.json",
            "agent_card_alt": "/.well-known/agent-card.json",
            "jsonrpc": "/a2a/jsonrpc",
            "health": "/health",
        },
    })


# ---------------------------------------------------------------------------
# Token loading
# ---------------------------------------------------------------------------

def load_tokens(token_files: list[str] | None = None) -> list[str]:
    """Load tokens from files, stripping whitespace/BOM."""
    tokens: list[str] = []
    env_token = os.environ.get("A2A_TOKEN", "")
    if env_token:
        tokens.append(env_token.strip().lstrip("﻿"))

    for path in (token_files or []):
        fp = Path(path).expanduser()
        if not fp.exists():
            log.warning("token file not found: %s", fp)
            continue
        try:
            data = fp.read_bytes()
            if data.startswith(b"\xef\xbb\xbf"):
                data = data[3:]
            token = data.decode("utf-8").strip()
            if token:
                tokens.append(token)
                check_token_file_hygiene(fp)
        except Exception as e:
            log.error("failed to read token file %s: %s", fp, e)

    if not tokens:
        log.warning("no auth tokens configured — gateway will reject all authenticated requests")
    else:
        log.info("loaded %d auth token(s)", len(tokens))
    return tokens


def check_token_file_hygiene(path: Path) -> None:
    """Health-check a token file for common issues (BOM, CRLF, permissions)."""
    try:
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            log.warning("token file %s has UTF-8 BOM", path.name)
        if b"\r\n" in data:
            log.warning("token file %s has CRLF line endings", path.name)
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            log.warning("token file %s permissions %o are too broad (should be 600)", path.name, mode)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_gateway_config(config_path: str) -> dict:
    """Load gateway YAML config with sensible defaults."""
    default = {
        "listen_host": "127.0.0.1",
        "listen_port": 18800,
        "default_agent_id": "main",
        "default_peer": "openclaw",
        "cors_origins": [],
        "routing_rules": [],
        "peers": {},
    }
    path = Path(config_path)
    if not path.exists():
        log.info("no gateway config at %s, using defaults", config_path)
        return default
    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return {**default, **cfg}
    except Exception as e:
        log.error("failed to load config: %s", e)
        return default


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AgentWire Gateway v2.0")
    parser.add_argument("--host", default=None, help="Listen host (default: from config or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Listen port (default: from config or 18800)")
    parser.add_argument("--config", default=None, help="Gateway config YAML path")
    parser.add_argument("--token-file", action="append", default=[], dest="token_files",
                        help="Bearer token file (may be repeated)")
    parser.add_argument("--tls-cert", default=None, help="TLS certificate file")
    parser.add_argument("--tls-key", default=None, help="TLS private key file")
    parser.add_argument("--openclaw-url", default=None, help="OpenClaw Gateway URL")
    parser.add_argument("--openclaw-token", default=None, help="OpenClaw Gateway token")
    args = parser.parse_args()

    # Config
    config_path = args.config or os.environ.get(
        "GATEWAY_CONFIG", "/app/server/config.yaml"
    )
    cfg = load_gateway_config(config_path)

    host = args.host or os.environ.get("CORE_LISTEN_HOST", "") or cfg["listen_host"]
    port = args.port or int(os.environ.get("CORE_LISTEN_PORT", "") or 0) or cfg["listen_port"]

    # Tokens
    token_files = args.token_files or []
    if not token_files:
        env_file = os.environ.get("A2A_TOKEN_FILE", "")
        if env_file:
            token_files.append(env_file)
    tokens = load_tokens(token_files)

    # Agent Router
    router = AgentRouter(
        config_path=config_path,
        default_agent_id=cfg.get("default_agent_id", "main"),
        default_peer=cfg.get("default_peer", "openclaw"),
    )

    # Gateway Executor
    executor = GatewayExecutor(
        router=router,
        openclaw_gateway_url=args.openclaw_url,
        openclaw_token=args.openclaw_token,
        config_path=config_path,
    )

    # Task Store
    task_store_path = os.environ.get("TASK_STORE_PATH", "/data/tasks.db")
    task_store = SqliteTaskStore(db_path=task_store_path)

    # Agent Card
    agent_card = build_agent_card(
        name=cfg.get("name", "AgentWire Gateway"),
        version=__version__,
        listen_host=host,
        listen_port=port,
    )

    # Request Handler (the SDK's built-in handler for ALL A2A methods)
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        agent_card=agent_card,
        queue_manager=InMemoryQueueManager(),
    )

    # Routes
    card_routes = create_agent_card_routes(agent_card)
    jsonrpc_routes = create_jsonrpc_routes(
        request_handler=request_handler,
        rpc_url="/a2a/jsonrpc",
        context_builder=DefaultServerCallContextBuilder(),
    )

    # v2.0.1: expose both agent card paths (like CUE v2.0)
    # /.well-known/agent.json = standard A2A path (primary)
    # /.well-known/agent-card.json = compatibility path (from SDK)
    from a2a.server.request_handlers.response_helpers import agent_card_to_dict
    async def _agent_card_alt(request: Request) -> Response:
        return JSONResponse(agent_card_to_dict(agent_card))

    custom_routes = [
        Route("/.well-known/agent.json", _agent_card_alt, methods=["GET"]),
        Route("/health", health_endpoint, methods=["GET"]),
        Route("/", root_endpoint, methods=["GET"]),
    ]

    # CORS
    cors_origins = cfg.get("cors_origins", [])
    if cors_origins:
        log.info("CORS origins: %s", cors_origins)

    # Auth middleware
    token_middleware = Middleware(
        BearerTokenMiddleware,
        tokens=tokens,
        exclude_paths=["/.well-known/agent.json", "/.well-known/agent-card.json", "/health", "/"],
    )

    middlewares = [token_middleware]
    if cors_origins:
        middlewares.append(
            Middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"], allow_headers=["*"])
        )

    # Starlette app
    app = Starlette(
        routes=card_routes + jsonrpc_routes + custom_routes,
        middleware=middlewares,
    )

    # TLS
    ssl_context = None
    if args.tls_cert and args.tls_key:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(args.tls_cert, args.tls_key)
        log.info("TLS enabled: %s", args.tls_cert)

    # Start
    import uvicorn

    log.info("AgentWire Gateway v2.0 starting on %s:%d", host, port)
    log.info("  Agent Card: http://%s:%d/.well-known/agent.json", host, port)
    log.info("  Agent Card (alt): http://%s:%d/.well-known/agent-card.json", host, port)
    log.info("  JSON-RPC:   http://%s:%d/a2a/jsonrpc", host, port)

    uvicorn.run(
        app,
        host=host,
        port=port,
        ssl_certfile=args.tls_cert,
        ssl_keyfile=args.tls_key,
        log_level="info",
    )


if __name__ == "__main__":
    main()
