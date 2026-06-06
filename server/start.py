#!/usr/bin/env python3
"""AgentWire Python A2A 服务入口 (v1.4.3)

v1.4.3 changes vs v1.4.2:
  - Registered previously-orphaned routes: /.well-known/agent.json,
    /health, /a2a/jsonrpc
  - Added /redact/patterns endpoint (shared catalog)
  - JSON-RPC handlers for messages/list, messages/get, messages/peers,
    messages/export
  - History persistence: per-peer JSONL files with auto-redaction
  - Context-injection: when context_rounds > 0, last N rounds attached
    to outbound message metadata
  - REST /a2a/rest/message/send now also records to history
"""
import argparse
import asyncio
import logging
import os
import signal
import uuid

import yaml
from aiohttp import web

# v1.4.3: split-out modules
from history import HistoryManager
from redact import load_catalog

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('agentwire')

DEFAULT_AGENT_CARD = {
    "protocolVersion": "1.0.1",
    "name": "AgentWire",
    "description": "AgentWire A2A v1.0.1 Service",
    "version": "1.4.3",
    "capabilities": {"streaming": True, "pushNotifications": False, "extendedAgentCard": False},
    "skills": [],
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"]
}


def load_workflow_hook_config():
    default_config = {
        "enabled": False,
        "openclaw_path": "openclaw",
        "agent_id": "main",
        "workflow_path": "",
        "trigger_keywords": ["project:", "scenes:"],
        "trigger_min_lines": 5,
        "timeout": 300,
    }

    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(config_path):
        logger.info("[工作流钩子] 未找到 config.yaml，钩子功能禁用")
        return default_config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        workflow_config = config.get('workflow_hook', {}) if config else {}

        result = {
            "enabled": workflow_config.get('enabled', False),
            "openclaw_path": workflow_config.get('openclaw_path', default_config['openclaw_path']),
            "agent_id": workflow_config.get('agent_id', default_config['agent_id']),
            "workflow_path": workflow_config.get('workflow_path', default_config['workflow_path']),
            "trigger_keywords": workflow_config.get('trigger_keywords', default_config['trigger_keywords']),
            "trigger_min_lines": workflow_config.get('trigger_min_lines', default_config['trigger_min_lines']),
            "timeout": workflow_config.get('timeout', default_config['timeout']),
        }

        if result["enabled"]:
            logger.info(f"[工作流钩子] 已启用，workflow_path: {result['workflow_path']}")
        else:
            logger.info("[工作流钩子] 配置中钩子已禁用")

        return result

    except Exception as e:
        logger.error(f"[工作流钩子] 配置加载失败: {e}，使用默认配置")
        return default_config


def load_history_config() -> dict:
    """Load history section from config.yaml, with safe defaults."""
    default = {
        "enabled": True,
        "max_rounds_per_peer": 0,         # 0 = unlimited
        "context_rounds": 5,             # 0 = off
        "storage_dir": "~/.local/share/agentwire/history",
        "redact_sensitive": True,
        "redact_patterns_path": None,     # None = use built-in catalog
        "round_close": {
            "mode": "heuristic",
            "heuristic_idle_seconds": 300,
        },
    }
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if not os.path.exists(config_path):
        return default
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
        h = cfg.get('history', {}) or {}
        merged = {**default, **h}
        if "round_close" in h:
            merged["round_close"] = {**default["round_close"], **h["round_close"]}
        return merged
    except Exception as e:
        logger.error(f"[history] 配置加载失败: {e}，使用默认配置")
        return default


# Globals set at startup
WORKFLOW_HOOK_CONFIG = None
HISTORY: HistoryManager | None = None
HISTORY_CONFIG: dict = {}
REDACT_CATALOG: dict = {}


class A2AGateway:
    def __init__(self, host="0.0.0.0", port=18800, auth_token="", agent_card=None):
        self.host, self.port, self.auth_token = host, port, auth_token
        self.agent_card = agent_card or DEFAULT_AGENT_CARD
        # v1.4.2 AUDIT-FIX #7: CORS restricted to explicit origins (not wildcard).
        self.cors_origins: list[str] = []
        self.app = web.Application(middlewares=[self._cors_middleware])
        self.runner = None
        self.site = None
        self._running = False
        self.tasks = {}
        self._setup_routes()

    @web.middleware
    async def _cors_middleware(self, req, handler):
        if req.method == 'OPTIONS':
            return web.Response(status=204)
        resp = await handler(req)
        origin = req.headers.get('Origin')
        if origin and origin in self.cors_origins:
            resp.headers['Access-Control-Allow-Origin'] = origin
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            resp.headers['Access-Control-Max-Age'] = '3600'
        return resp

    def _setup_routes(self):
        # v1.4.3: register previously-orphaned routes
        self.app.router.add_get('/.well-known/agent.json', self._handle_agent_card)
        self.app.router.add_get('/health', self._handle_health)
        self.app.router.add_post('/a2a/jsonrpc', self._handle_jsonrpc)
        self.app.router.add_get('/redact/patterns', self._handle_redact_patterns)
        # pre-existing
        self.app.router.add_post('/a2a/rest/message/send', self._handle_rest_send)
        self.app.router.add_get('/a2a/metrics', self._handle_metrics)

    async def _handle_root(self, req):
        return web.json_response({'service': 'AgentWire', 'version': self.agent_card.get('version'), 'protocol': 'A2A v1.0.1', 'status': 'running'})

    async def _handle_health(self, req):
        return web.json_response({'status': 'healthy', 'service': 'agentwire', 'version': self.agent_card.get('version'), 'protocolVersion': '1.0.1'})

    async def _handle_agent_card(self, req):
        return web.json_response(self.agent_card)

    async def _handle_redact_patterns(self, req):
        if self.auth_token:
            auth = req.headers.get('Authorization', '')
            if not auth.startswith('Bearer ') or auth[7:] != self.auth_token:
                return web.json_response({'error': 'Unauthorized'}, status=401)
        return web.json_response(REDACT_CATALOG)

    def _check_auth(self, req) -> bool:
        """Returns True if request is authorized (or no auth required)."""
        if not self.auth_token:
            return self._loopback_request(req)
        auth = req.headers.get('Authorization', '')
        return auth.startswith('Bearer ') and auth[7:] == self.auth_token

    async def _handle_jsonrpc(self, req):
        try:
            if not self._check_auth(req):
                return self._error(None, -32600, 'Unauthorized')
            try:
                data = await req.json()
            except Exception:
                return self._error(None, -32700, 'Parse error')
            method, params, req_id = data.get('method'), data.get('params', {}) or {}, data.get('id')
            logger.info(f"JSON-RPC: {method}")
            if method == 'message/send':
                return await self._handle_message_send(req_id, params)
            elif method == 'tasks/get':
                return self._handle_task_get(req_id, params)
            elif method == 'tasks/list':
                return self._result(req_id, {'tasks': list(self.tasks.values())})
            elif method == 'tasks/cancel':
                tid = params.get('taskId')
                if tid and tid in self.tasks:
                    self.tasks[tid]['status']['state'] = 'canceled'
                return self._result(req_id, {'status': 'canceled'})
            elif method == 'tasks/subscribe':
                return self._result(req_id, {'subscribed': True, 'taskId': params.get('taskId')})
            elif method == 'agent/getCard':
                return self._result(req_id, self.agent_card)
            # v1.4.3: history methods
            elif method == 'messages/list':
                return self._handle_messages_list(req_id, params)
            elif method == 'messages/get':
                return self._handle_messages_get(req_id, params)
            elif method == 'messages/peers':
                return self._handle_messages_peers(req_id, params)
            elif method == 'messages/export':
                return self._handle_messages_export(req_id, params)
            else:
                return self._error(req_id, -32601, f'Method not found: {method}')
        except Exception:
            logger.exception("JSON-RPC internal error")
            return self._error(None, -32603, 'Internal error')

    def _handle_messages_list(self, req_id, params):
        if HISTORY is None:
            return self._result(req_id, {"peers": [] if params.get('peer_uuid') is None else None})
        peer_uuid = params.get('peer_uuid') or params.get('peer_name')  # accept both
        since_round = int(params.get('since_round') or 0)
        limit = min(int(params.get('limit') or 5), 100)
        return self._result(req_id, HISTORY.list_messages(peer_uuid, since_round, limit))

    def _handle_messages_get(self, req_id, params):
        if HISTORY is None:
            return self._error(req_id, -32603, 'history disabled')
        peer_uuid = params.get('peer_uuid') or params.get('peer_name')
        round_n = int(params.get('round') or 0)
        if not peer_uuid or round_n <= 0:
            return self._error(req_id, -32602, 'peer_uuid and round required')
        return self._result(req_id, {"peer_uuid": peer_uuid, "round": round_n, "messages": HISTORY.get_round(peer_uuid, round_n)})

    def _handle_messages_peers(self, req_id, params):
        if HISTORY is None:
            return self._result(req_id, {"peers": []})
        return self._result(req_id, {"peers": HISTORY.list_peers()})

    def _handle_messages_export(self, req_id, params):
        if HISTORY is None:
            return self._error(req_id, -32603, 'history disabled')
        peer_uuid = params.get('peer_uuid') or params.get('peer_name')
        fmt = params.get('format') or 'jsonl'
        if not peer_uuid:
            return self._error(req_id, -32602, 'peer_uuid required')
        try:
            content = HISTORY.export(peer_uuid, fmt)
        except ValueError as e:
            return self._error(req_id, -32602, str(e))
        return self._result(req_id, {"format": fmt, "content": content})

    async def _handle_message_send(self, req_id, params):
        msg = params.get('message', {}) or {}
        parts_in = msg.get('parts', [])
        context_id = params.get('contextId') or params.get('taskId')
        msg_id = msg.get('messageId') or str(uuid.uuid4())
        text = ' '.join(p.get('text', '') for p in parts_in if p.get('type') == 'text')
        logger.info(f"收到消息: {text[:50]}")

        # Workflow hook (unchanged)
        if WORKFLOW_HOOK_CONFIG and WORKFLOW_HOOK_CONFIG["enabled"]:
            try:
                hook_result = await trigger_workflow_if_match(text, context_id)
                if hook_result.get("triggered"):
                    logger.info(f"[工作流钩子] {hook_result.get('reason')}")
                else:
                    logger.debug(f"[工作流钩子] 未触发: {hook_result.get('reason')}")
            except Exception as hook_error:
                logger.error(f"[工作流钩子] 执行异常（不影响主流程）: {hook_error}")

        # v1.4.3: history record
        peer_uuid, round_n = None, None
        if HISTORY is not None and HISTORY_CONFIG.get('enabled', True):
            peer_uuid, round_n = HISTORY.record_outbound(context_id, msg_id, parts_in)

        # Build response
        tid = str(uuid.uuid4())
        reply_text = f'AgentWire 回复: 收到 "{text[:30]}..."'
        reply_parts = [{'type': 'text', 'text': reply_text}]

        # v1.4.3: context injection — attach history metadata to reply
        reply_msg = {
            'messageId': str(uuid.uuid4()),
            'role': 'agent',
            'parts': reply_parts,
        }
        if (HISTORY is not None
                and HISTORY_CONFIG.get('enabled', True)
                and HISTORY_CONFIG.get('context_rounds', 0) > 0
                and peer_uuid):
            ctx_msgs = HISTORY.get_context_for_peer(
                peer_uuid,
                HISTORY_CONFIG.get('context_rounds', 5),
            )
            reply_msg['metadata'] = {
                'agentwire_history': {
                    'peer_uuid': peer_uuid,
                    'round': round_n,
                    'context_rounds': HISTORY_CONFIG.get('context_rounds', 5),
                    'messages': ctx_msgs,
                }
            }
            # Record the inbound (this reply) too
            HISTORY.record_inbound(peer_uuid, reply_msg['messageId'], reply_parts)

        resp = {'kind': 'task', 'id': tid, 'status': {'state': 'completed'}, 'message': reply_msg}
        self.tasks[tid] = resp
        return self._result(req_id, resp)

    def _handle_task_get(self, req_id, params):
        tid = params.get('taskId')
        if not tid:
            return self._error(req_id, -32602, 'Missing taskId')
        task = self.tasks.get(tid)
        if not task:
            return self._error(req_id, -32602, f'Task not found: {tid}')
        return self._result(req_id, task)

    @staticmethod
    def _loopback_request(req) -> bool:
        remote = req.remote or ''
        host = remote.split(',')[1].strip() if ',' in remote else remote.split(':')[0].strip()
        return host in ('127.0.0.1', '::1', 'localhost') or host.startswith('127.')

    async def _handle_rest_send(self, req):
        if not self._check_auth(req):
            return web.json_response(
                {'error': 'Unauthorized'}, status=401,
                headers={'WWW-Authenticate': 'Bearer'},
            )
        try:
            data = await req.json()
            msg = data.get('message', {}) or {}
            parts_in = msg.get('parts', [])
            context_id = data.get('contextId') or data.get('taskId')
            msg_id = msg.get('messageId') or str(uuid.uuid4())
            text = ' '.join(p.get('text', '') for p in parts_in if p.get('type') == 'text')

            # Workflow hook
            if WORKFLOW_HOOK_CONFIG and WORKFLOW_HOOK_CONFIG["enabled"]:
                try:
                    hook_result = await trigger_workflow_if_match(text, context_id)
                    if hook_result.get("triggered"):
                        logger.info(f"[工作流钩子] {hook_result.get('reason')}")
                except Exception as hook_error:
                    logger.error(f"[工作流钩子] 执行异常（不影响主流程）: {hook_error}")

            # v1.4.3: history record
            peer_uuid, round_n = None, None
            if HISTORY is not None and HISTORY_CONFIG.get('enabled', True):
                peer_uuid, round_n = HISTORY.record_outbound(context_id, msg_id, parts_in)

            tid = str(uuid.uuid4())
            reply_text = f'AgentWire: 收到 "{text[:50]}..."'
            reply_parts = [{'type': 'text', 'text': reply_text}]
            reply_msg = {
                'messageId': str(uuid.uuid4()),
                'role': 'agent',
                'parts': reply_parts,
            }
            if (HISTORY is not None
                    and HISTORY_CONFIG.get('enabled', True)
                    and HISTORY_CONFIG.get('context_rounds', 0) > 0
                    and peer_uuid):
                ctx_msgs = HISTORY.get_context_for_peer(
                    peer_uuid,
                    HISTORY_CONFIG.get('context_rounds', 5),
                )
                reply_msg['metadata'] = {
                    'agentwire_history': {
                        'peer_uuid': peer_uuid,
                        'round': round_n,
                        'context_rounds': HISTORY_CONFIG.get('context_rounds', 5),
                        'messages': ctx_msgs,
                    }
                }
                HISTORY.record_inbound(peer_uuid, reply_msg['messageId'], reply_parts)

            resp = {'kind': 'task', 'id': tid, 'status': {'state': 'completed'}, 'message': reply_msg}
            return web.json_response(resp)
        except Exception:
            logger.exception("REST message/send internal error")
            return web.json_response({'error': 'Internal error'}, status=500)

    async def _handle_metrics(self, req):
        return web.json_response({
            'tasks_total': len(self.tasks),
            'tasks_completed': sum(1 for t in self.tasks.values() if t.get('status', {}).get('state') == 'completed'),
        })

    def _result(self, req_id, result):
        return web.json_response({'jsonrpc': '2.0', 'id': req_id, 'result': result})

    def _error(self, req_id, code, msg):
        return web.json_response(
            {'jsonrpc': '2.0', 'id': req_id, 'error': {'code': code, 'message': msg}},
            status=400 if code in (-32700, -32600, -32602) else 500,
        )

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        self._running = True
        logger.info(f"AgentWire 启动: http://{self.host}:{self.port}")
        logger.info(f"Agent Card: http://{self.host}:{self.port}/.well-known/agent.json")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
        self._running = False
        logger.info("AgentWire 已停止")


# ===== 工作流钩子 (unchanged from v1.4.2) =====
async def trigger_workflow_if_match(message_text: str, context_id: str = None) -> dict:
    cfg = WORKFLOW_HOOK_CONFIG
    if not cfg["enabled"]:
        return {"triggered": False, "reason": "钩子已禁用"}

    keyword_count = sum(1 for kw in cfg["trigger_keywords"] if kw.lower() in message_text.lower())
    if keyword_count < 2:
        return {"triggered": False, "reason": f"关键词匹配不足（{keyword_count}/2）"}

    line_count = len(message_text.split('\n'))
    if line_count < cfg["trigger_min_lines"]:
        return {"triggered": False, "reason": f"行数不足（{line_count}/{cfg['trigger_min_lines']}）"}

    import datetime
    trigger_message = (
        f"[系统指令] 收到视频制作脚本请求。\n\n"
        f"请立即执行以下操作：\n"
        f"1. 读取工作流路径：{cfg['workflow_path']}\n"
        f"2. 按照该路径下的工作流定义，处理以下脚本\n"
        f"3. 严格遵循工作流中的每个步骤，完成视频制作全流程\n"
        f"4. 完成后回复处理结果\n\n"
        f"===== 脚本内容开始 =====\n"
        f"{message_text}\n"
        f"===== 脚本内容结束 =====\n\n"
        f"上下文ID：{context_id or '无'}\n"
        f"时间戳：{datetime.datetime.now().isoformat()}"
    )
    asyncio.create_task(_run_openclaw_agent_async(trigger_message, keyword_count, line_count))
    return {"triggered": True, "reason": f"已异步触发（匹配关键词{keyword_count}个，行数{line_count}）"}


async def _run_openclaw_agent_async(message: str, keyword_count: int = 0, line_count: int = 0):
    cfg = WORKFLOW_HOOK_CONFIG
    try:
        proc = await asyncio.create_subprocess_exec(
            cfg["openclaw_path"], "agent",
            "--message", message,
            "--agent", cfg["agent_id"],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=cfg["timeout"])
        if proc.returncode == 0:
            logger.info(f"[工作流钩子] CLI 执行成功，returncode={proc.returncode}")
        else:
            logger.warning(f"[工作流钩子] CLI 执行失败，returncode={proc.returncode}")
            if stderr:
                logger.warning(f"[工作流钩子] stderr: {stderr.decode()[:200]}")
    except asyncio.TimeoutError:
        logger.error(f"[工作流钩子] CLI 执行超时（{cfg['timeout']}秒）")
    except FileNotFoundError:
        logger.error(f"[工作流钩子] openclaw 命令未找到: {cfg['openclaw_path']}")
    except Exception as e:
        logger.error(f"[工作流钩子] 执行异常: {e}")


async def main():
    global WORKFLOW_HOOK_CONFIG, HISTORY, HISTORY_CONFIG, REDACT_CATALOG

    parser = argparse.ArgumentParser(description='AgentWire A2A v1.0.1 Service')
    parser.add_argument('--host', default='127.0.0.1',
                        help='bind host (default 127.0.0.1; use 0.0.0.0 only with auth)')
    parser.add_argument('--port', '-p', type=int, default=18800)
    parser.add_argument('--token', '-t', default='')
    parser.add_argument('--token-file', default='',
                        help='read token from file (UTF-8 BOM auto-stripped)')
    parser.add_argument('--cors-origin', action='append', default=[],
                        help='CORS allowlist (repeatable). No wildcards.')
    parser.add_argument('--redact-patterns', default='',
                        help='path to JSON file with redaction patterns '
                             '(default: built-in catalog)')
    args = parser.parse_args()

    if args.host not in ('127.0.0.1', '::1', 'localhost') and not args.host.startswith('127.'):
        if not (args.token or args.token_file or os.getenv('AGENTWIRE_TOKEN')):
            logger.error(
                f"FAIL-FAST: --host {args.host} (non-loopback) requires --token, "
                "--token-file, or AGENTWIRE_TOKEN env var."
            )
            sys.exit(1)

    auth_token = args.token
    if not auth_token and args.token_file:
        try:
            with open(args.token_file, 'r', encoding='utf-8-sig') as f:
                auth_token = f.read().strip()
        except OSError as e:
            logger.error(f"--token-file {args.token_file}: {e}")
            sys.exit(1)
    if not auth_token:
        auth_token = os.getenv('AGENTWIRE_TOKEN', '')

    # v1.4.3: redact catalog (shared via /redact/patterns)
    REDACT_CATALOG = load_catalog(args.redact_patterns or None)

    # v1.4.3: history manager
    HISTORY_CONFIG = load_history_config()
    if HISTORY_CONFIG.get('enabled', True):
        HISTORY = HistoryManager(
            storage_dir=HISTORY_CONFIG.get('storage_dir', '~/.local/share/agentwire/history'),
            max_rounds_per_peer=HISTORY_CONFIG.get('max_rounds_per_peer', 0),
        )
        if HISTORY_CONFIG.get('redact_sensitive', True):
            HISTORY.set_patterns(REDACT_CATALOG['patterns'])
            logger.info(
                f"[history] 已启用: {HISTORY_CONFIG.get('storage_dir')}, "
                f"max_rounds={HISTORY_CONFIG.get('max_rounds_per_peer', 0)}, "
                f"context_rounds={HISTORY_CONFIG.get('context_rounds', 5)}, "
                f"redact_patterns={len(REDACT_CATALOG['patterns'])}"
            )
    else:
        HISTORY = None
        logger.info("[history] 已禁用")

    WORKFLOW_HOOK_CONFIG = load_workflow_hook_config()

    gateway = A2AGateway(host=args.host, port=args.port, auth_token=auth_token)
    gateway.cors_origins = list(args.cors_origin)

    await gateway.start()
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    try:
        await stop_event.wait()
    finally:
        await gateway.stop()


if __name__ == '__main__':
    asyncio.run(main())
