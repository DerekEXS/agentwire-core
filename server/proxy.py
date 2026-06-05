"""AgentWire A2A reverse proxy — listens on a port, forwards JSON-RPC to AGENTWIRE.

Use case: when tools expect a specific proxy port (e.g. legacy openclaw
plugin's expected port), they can point to this proxy which forwards to
the real AGENTWIRE Python on 18800.

v1.4.2: replaces the old agentwire TypeScript plugin (id=agentwire)
which did the same thing but conflicted with AGENTWIRE Python on 18800.

v1.4.2 AUDIT #5: SECURITY WARNING. This proxy is transparent and has NO
own auth. Caller is responsible for:
1. Binding to loopback (default --listen-host 127.0.0.1)
2. Putting AGENTWIRE behind a firewall
3. The TARGET AGENTWIRE handles auth (Bearer token via Authorization
   header) forwarded as-is by this proxy.

Usage:
  python3 agentwire_proxy.py --listen-port 18802 --target-port 18800
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Awaitable, Callable

import aiohttp
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("agentwire_proxy")


async def health_handler(request: web.Request) -> web.Response:
    """GET /health: 200 if upstream is reachable, 503 otherwise."""
    target = request.app["target_url"]
    try:
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{target}/.well-known/agent.json") as resp:
                if resp.status == 200:
                    return web.json_response({"status": "healthy", "upstream": target}, status=200)
                return web.json_response({"status": "degraded", "upstream_status": resp.status}, status=503)
    except Exception as e:
        return web.json_response({"status": "downstream_unreachable", "error": str(e)}, status=503)


async def proxy_handler(request: web.Request) -> web.StreamResponse:
    """Forward all other requests to upstream AGENTWIRE (transparent proxy)."""
    target = request.app["target_url"]
    target_url = f"{target}{request.path_qs}"
    # Forward headers (strip hop-by-hop)
    skip_headers = {"host", "connection", "content-length", "transfer-encoding"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in skip_headers}
    body = await request.read()
    log.debug("PROXY %s %s -> %s", request.method, request.path, target_url)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.request(
            request.method, target_url,
            headers=headers, data=body, allow_redirects=False,
        ) as resp:
            response_body = await resp.read()
            response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in skip_headers}
            return web.Response(
                status=resp.status,
                body=response_body,
                headers=response_headers,
            )


def make_app(target_url: str) -> web.Application:
    app = web.Application()
    app["target_url"] = target_url.rstrip("/")
    app.router.add_get("/health", health_handler)
    # Catch-all: any other path -> proxy
    app.router.add_route("*", "/{path:.*}", proxy_handler)
    return app


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-port", type=int, default=18802,
                        help="port to listen on (default 18802)")
    parser.add_argument("--listen-host", default="127.0.0.1",
                        help="bind host (default 127.0.0.1)")
    parser.add_argument("--target-url", default="http://127.0.0.1:18800",
                        help="upstream AGENTWIRE URL (default http://127.0.0.1:18800)")
    args = parser.parse_args()
    app = make_app(args.target_url)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.listen_host, args.listen_port)
    await site.start()
    log.info("AgentWire proxy listening on %s:%d -> %s",
             args.listen_host, args.listen_port, args.target_url)
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
