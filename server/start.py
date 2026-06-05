#!/usr/bin/env python3
"""AgentWire Python A2A 服务入口"""
import argparse, asyncio, logging, os, signal, uuid
from aiohttp import web

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('agentwire')

DEFAULT_AGENT_CARD = {
    "protocolVersion": "1.0.1",
    "name": "AgentWire",
    "description": "AgentWire A2A v1.0.1 Service",
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": False, "extendedAgentCard": False},
    "skills": [],
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"]
}

# ===== 工作流钩子配置加载函数 [2026-06-02] =====
def load_workflow_hook_config():
    """
    从 config.yaml 加载工作流钩子配置。
    如果配置文件不存在或加载失败，返回默认配置（钩子禁用）。
    """
    import yaml

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
            "openclaw_path": workflow_config.get('openclaw_path', 'openclaw'),
            "agent_id": workflow_config.get('agent_id', 'main'),
            "workflow_path": workflow_config.get('workflow_path', ''),
            "trigger_keywords": workflow_config.get('trigger_keywords', default_config['trigger_keywords']),
            "trigger_min_lines": workflow_config.get('trigger_min_lines', 5),
            "timeout": workflow_config.get('timeout', 300),
        }

        if result["enabled"]:
            logger.info(f"[工作流钩子] 已启用，workflow_path: {result['workflow_path']}")
        else:
            logger.info("[工作流钩子] 配置中钩子已禁用")

        return result

    except Exception as e:
        logger.error(f"[工作流钩子] 配置加载失败: {e}，使用默认配置")
        return default_config

# 全局钩子配置
WORKFLOW_HOOK_CONFIG = None
# ===== 钩子配置结束 =====

class A2AGateway:
    def __init__(self, host="0.0.0.0", port=18800, auth_token="", agent_card=None):
        self.host, self.port, self.auth_token = host, port, auth_token
        self.agent_card = agent_card or DEFAULT_AGENT_CARD
        # v1.4.2 AUDIT-FIX #7: CORS restricted to explicit origins (not wildcard).
        # Empty allowlist = no CORS headers sent (browser will block cross-origin).
        self.cors_origins: list[str] = []
        self.app = web.Application(middlewares=[self._cors_middleware])
        self.runner = None
        self.site = None
        self._running = False
        self.tasks = {}
        self._setup_routes()

    @web.middleware
    async def _cors_middleware(self, req, handler):
        """v1.4.2 AUDIT-FIX #7: explicit CORS allowlist. No wildcard.
        Caller must configure self.cors_origins = ['https://app.example.com', ...]
        """
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
        self.app.router.add_post('/a2a/rest/message/send', self._handle_rest_send)
        self.app.router.add_get('/a2a/metrics', self._handle_metrics)

    async def _handle_root(self, req): return web.json_response({'service': 'AgentWire', 'version': '1.0.0', 'protocol': 'A2A v1.0.1', 'status': 'running'})
    async def _handle_health(self, req): return web.json_response({'status': 'healthy', 'service': 'agentwire', 'version': '1.0.0', 'protocolVersion': '1.0.1'})
    async def _handle_agent_card(self, req): return web.json_response(self.agent_card)

    async def _handle_jsonrpc(self, req):
        try:
            if self.auth_token:
                auth = req.headers.get('Authorization', '')
                if not auth.startswith('Bearer ') or auth[7:] != self.auth_token:
                    return self._error(None, -32600, 'Unauthorized')
            try: data = await req.json()
            except: return self._error(None, -32700, 'Parse error')
            method, params, req_id = data.get('method'), data.get('params', {}), data.get('id')
            logger.info(f"JSON-RPC: {method}")
            if method == 'message/send': return await self._handle_message_send(req_id, params)
            elif method == 'tasks/get': return await self._handle_task_get(req_id, params)
            elif method == 'tasks/list': return self._result(req_id, {'tasks': list(self.tasks.values())})
            elif method == 'tasks/cancel':
                tid = params.get('taskId')
                if tid and tid in self.tasks: self.tasks[tid]['status']['state'] = 'canceled'
                return self._result(req_id, {'status': 'canceled'})
            elif method == 'tasks/subscribe': return self._result(req_id, {'subscribed': True, 'taskId': params.get('taskId')})
            elif method == 'agent/getCard': return self._result(req_id, self.agent_card)
            else: return self._error(req_id, -32601, f'Method not found: {method}')
        except Exception as e:
            # v1.4.2 AUDIT-FIX #8: don't leak internal error to caller.
            # Log full error server-side, return generic message.
            logger.exception("JSON-RPC internal error")
            return self._error(None, -32603, 'Internal error')

    async def _handle_message_send(self, req_id, params):
        parts = params.get('message', {}).get('parts', [])
        text = ' '.join(p.get('text', '') for p in parts if p.get('type') == 'text')
        logger.info(f"收到消息: {text[:50]}")

        # ===== 工作流钩子 [2026-06-02] =====
        if WORKFLOW_HOOK_CONFIG and WORKFLOW_HOOK_CONFIG["enabled"]:
            context_id = params.get('contextId') or params.get('taskId')
            try:
                hook_result = await trigger_workflow_if_match(text, context_id)
                if hook_result.get("triggered"):
                    logger.info(f"[工作流钩子] {hook_result.get('reason')}")
                else:
                    logger.debug(f"[工作流钩子] 未触发: {hook_result.get('reason')}")
            except Exception as hook_error:
                logger.error(f"[工作流钩子] 执行异常（不影响主流程）: {hook_error}")
        # ===== 钩子结束 =====

        tid = str(uuid.uuid4())
        resp = {'kind': 'task', 'id': tid, 'status': {'state': 'completed'}, 'message': {'messageId': str(uuid.uuid4()), 'role': 'agent', 'parts': [{'type': 'text', 'text': f'AgentWire 回复: 收到 "{text[:30]}..."'}]}}
        self.tasks[tid] = resp
        return self._result(req_id, resp)

    async def _handle_task_get(self, req_id, params):
        tid = params.get('taskId')
        if not tid: return self._error(req_id, -32602, 'Missing taskId')
        task = self.tasks.get(tid)
        if not task: return self._error(req_id, -32602, f'Task not found: {tid}')
        return self._result(req_id, task)

    @staticmethod
    def _loopback_request(req) -> bool:
        """v1.4.2 AUDIT-FIX #1: check if request originates from loopback.
        Only loopback IPs (127.0.0.0/8, ::1) are considered safe for
        no-auth access (e.g. local CUE host connecting to AGENTWIRE).
        """
        remote = req.remote or ''
        # aiohttp gives "(ipv4, host, port)" or similar; extract host
        host = remote.split(',')[1].strip() if ',' in remote else remote.split(':')[0].strip()
        return host in ('127.0.0.1', '::1', 'localhost') or host.startswith('127.')

    async def _handle_rest_send(self, req):
        # v1.4.2 AUDIT-FIX #1: REST endpoint now requires Bearer auth
        # (previously JSON-RPC had auth but REST skipped it, allowing
        # unauthenticated message/send to anyone reachable on the network)
        if self.auth_token:
            auth = req.headers.get('Authorization', '')
            if not auth.startswith('Bearer ') or auth[7:] != self.auth_token:
                return web.json_response(
                    {'error': 'Unauthorized'}, status=401,
                    headers={'WWW-Authenticate': 'Bearer'},
                )
        elif not self._loopback_request(req):
            # Empty token + non-loopback request: reject (fail-safe)
            logger.warning(
                f"Rejecting REST message/send from non-loopback {req.remote}: "
                "no auth_token configured. Set --token or --token-file to allow."
            )
            return web.json_response(
                {'error': 'Unauthorized: auth required for non-loopback requests'},
                status=401,
            )
        try:
            data = await req.json()
            parts = data.get('message', {}).get('parts', [])
            text = ' '.join(p.get('text', '') for p in parts if p.get('type') == 'text')

            # ===== 工作流钩子 [2026-06-02] =====
            if WORKFLOW_HOOK_CONFIG and WORKFLOW_HOOK_CONFIG["enabled"]:
                context_id = data.get('contextId') or data.get('taskId')
                try:
                    hook_result = await trigger_workflow_if_match(text, context_id)
                    if hook_result.get("triggered"):
                        logger.info(f"[工作流钩子] {hook_result.get('reason')}")
                    else:
                        logger.debug(f"[工作流钩子] 未触发: {hook_result.get('reason')}")
                except Exception as hook_error:
                    logger.error(f"[工作流钩子] 执行异常（不影响主流程）: {hook_error}")
            # ===== 钩子结束 =====

            tid = str(uuid.uuid4())
            return web.json_response({'kind': 'task', 'id': tid, 'status': {'state': 'completed'}, 'message': {'messageId': str(uuid.uuid4()), 'role': 'agent', 'parts': [{'type': 'text', 'text': f'AgentWire: 收到 "{text[:50]}..."'}]}})
        except Exception:
            # v1.4.2 AUDIT-FIX #8: don't leak internal error to caller
            logger.exception("REST message/send internal error")
            return web.json_response({'error': 'Internal error'}, status=500)

    async def _handle_metrics(self, req): return web.json_response({'tasks_total': len(self.tasks), 'tasks_completed': sum(1 for t in self.tasks.values() if t.get('status', {}).get('state') == 'completed')})

    def _result(self, req_id, result): return web.json_response({'jsonrpc': '2.0', 'id': req_id, 'result': result})
    def _error(self, req_id, code, msg): return web.json_response({'jsonrpc': '2.0', 'id': req_id, 'error': {'code': code, 'message': msg}}, status=400 if code in (-32700, -32600, -32602) else 500)

    async def start(self):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        self._running = True
        logger.info(f"AgentWire 启动: http://{self.host}:{self.port}")
        logger.info(f"Agent Card: http://{self.host}:{self.port}/.well-known/agent.json")

    async def stop(self):
        if self.runner: await self.runner.cleanup()
        self._running = False
        logger.info("AgentWire 已停止")

# ===== 工作流钩子函数 [2026-06-02] =====
async def trigger_workflow_if_match(message_text: str, context_id: str = None) -> dict:
    """
    检查消息是否为工作流脚本，如果是则异步触发 Agent 执行工作流。
    采用"发射后不管"模式：启动子进程后立即返回，不等待结果。

    触发条件：
    1. 消息包含 trigger_keywords 中至少 2 个关键词
    2. 消息行数 >= trigger_min_lines

    Args:
        message_text: A2A消息的文本内容
        context_id: A2A会话上下文ID（可选）

    Returns:
        dict: 包含 triggered(是否触发)、reason(原因)
    """
    cfg = WORKFLOW_HOOK_CONFIG

    if not cfg["enabled"]:
        return {"triggered": False, "reason": "钩子已禁用"}

    keyword_count = sum(
        1 for kw in cfg["trigger_keywords"]
        if kw.lower() in message_text.lower()
    )
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

    # 异步启动子进程（发射后不管模式）
    asyncio.create_task(_run_openclaw_agent_async(trigger_message, keyword_count, line_count))

    return {
        "triggered": True,
        "reason": f"已异步触发（匹配关键词{keyword_count}个，行数{line_count}）"
    }


async def _run_openclaw_agent_async(message: str, keyword_count: int = 0, line_count: int = 0):
    """
    异步执行 openclaw agent CLI，子进程结果写入日志。
    此函数由 asyncio.create_task 启动，不阻塞主事件循环。
    """
    cfg = WORKFLOW_HOOK_CONFIG
    try:
        proc = await asyncio.create_subprocess_exec(
            cfg["openclaw_path"], "agent",
            "--message", message,
            "--agent", cfg["agent_id"],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=cfg["timeout"])

        if proc.returncode == 0:
            logger.info(f"[工作流钩子] CLI 执行成功，returncode={proc.returncode}")
            logger.debug(f"[工作流钩子] stdout: {stdout.decode()[:200]}")
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
# ===== 钩子函数结束 =====

async def main():
    global WORKFLOW_HOOK_CONFIG

    parser = argparse.ArgumentParser(description='AgentWire A2A v1.0.1 Service')
    # v1.4.2 AUDIT-FIX #4: default host is 127.0.0.1 (loopback only) for safe
    # local dev. Pass --host 0.0.0.0 explicitly only when behind a trusted
    # reverse proxy or on a private network. With empty token + non-loopback
    # host, the server will fail-fast at startup.
    parser.add_argument('--host', default='127.0.0.1',
                        help='bind host (default 127.0.0.1; use 0.0.0.0 only with auth)')
    parser.add_argument('--port', '-p', type=int, default=18800)
    parser.add_argument('--token', '-t', default='')
    parser.add_argument('--token-file', default='',
                        help='read token from file (UTF-8 BOM auto-stripped)')
    parser.add_argument('--cors-origin', action='append', default=[],
                        help='CORS allowlist (repeatable). No wildcards. '
                             'Empty = no CORS headers (most secure).')
    args = parser.parse_args()
    # v1.4.2 AUDIT-FIX #4: fail-fast on non-loopback + empty token
    if args.host not in ('127.0.0.1', '::1', 'localhost') and not args.host.startswith('127.'):
        if not (args.token or args.token_file or os.getenv('AGENTWIRE_TOKEN')):
            logger.error(
                f"FAIL-FAST: --host {args.host} (non-loopback) requires --token, "
                "--token-file, or AGENTWIRE_TOKEN env var. Refusing to start with "
                "empty auth (would expose to whole network)."
            )
            sys.exit(1)
    # Token resolution priority: --token > --token-file > AGENTWIRE_TOKEN env > empty
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
    gateway = A2AGateway(host=args.host, port=args.port, auth_token=auth_token)
    gateway.cors_origins = list(args.cors_origin)

    # 加载工作流钩子配置
    WORKFLOW_HOOK_CONFIG = load_workflow_hook_config()

    await gateway.start()
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()
    def signal_handler(): stop_event.set()
    for sig in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(sig, signal_handler)
    try: await stop_event.wait()
    finally: await gateway.stop()

if __name__ == '__main__': asyncio.run(main())
