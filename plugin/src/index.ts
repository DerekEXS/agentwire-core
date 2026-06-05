/**
 * AgentWire OpenClaw Plugin
 * 内部代理请求到 Python A2A 服务
 */

interface Config {
  pythonHost?: string;
  pythonPort?: number;
  port?: number;
  authToken?: string;
  // v1.4.2 AUDIT-FIX #3 (P3): explicit CORS allowlist. No wildcard.
  // Empty = no CORS headers (most secure). Configure in openclaw.plugin.json
  // via "corsOrigins" (string[]) — caller must enumerate origins.
  corsOrigins?: string[];
}

const DEFAULT_AGENT_CARD = {
  protocolVersion: '1.0.1',
  name: 'AgentWire',
  description: 'AgentWire A2A v1.0.1 Service',
  version: '1.0.0',
  capabilities: { streaming: true, pushNotifications: false, extendedAgentCard: false },
  skills: [],
  defaultInputModes: ['text'],
  defaultOutputModes: ['text'],
};

let config: Config = { pythonHost: '127.0.0.1', pythonPort: 18800, port: 18800, corsOrigins: [] };
let server: any = null;

function proxyPost(targetHost: string, targetPort: number, targetPath: string, body: string, headers: Record<string, string>) {
  return new Promise<{ statusCode: number; body: string }>((resolve, reject) => {
    const http = require('http');
    const req = http.request({ hostname: targetHost, port: targetPort, path: targetPath, method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body), ...headers }, timeout: 3000 }, (res: any) => {
      let data = '';
      res.on('data', (c: string) => data += c);
      res.on('end', () => resolve({ statusCode: res.statusCode || 500, body: data }));
    });
    req.on('error', (err: any) => {
      if (err && err.code === 'ECONNREFUSED') {
        return resolve({ statusCode: 503, body: JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32603, message: 'A2A backend unavailable: connection refused' } }) });
      }
      reject(err);
    });
    req.on('timeout', () => { req.destroy(); resolve({ statusCode: 504, body: JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32603, message: 'A2A backend timeout' } }) }); });
    req.write(body);
    req.end();
  });
}

async function handleRequest(req: any, res: any) {
  const url = new URL(req.url || '/', `http://localhost:${config.port}`);
  // v1.4.2 AUDIT-FIX #3 (P3): CORS restricted to explicit allowlist.
  // No wildcard. If config.corsOrigins is unset/empty, NO CORS headers sent
  // (browser will block cross-origin). Caller must enumerate origins.
  const origin = req.headers['origin'];
  if (origin && config.corsOrigins && config.corsOrigins.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  }
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  try {
    if (url.pathname === '/health' || url.pathname === '/a2a/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'healthy', service: 'agentwire-plugin', version: '1.0.0', protocolVersion: '1.0.1' }));
    } else if (url.pathname === '/.well-known/agent.json' || url.pathname === '/.well-known/agent-card.json') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ...DEFAULT_AGENT_CARD, ...config.agentCard }));
    } else if (url.pathname === '/a2a/jsonrpc') {
      let body = '';
      for await (const chunk of req) body += chunk;
      const headers: Record<string, string> = {};
      if (config.authToken) headers['Authorization'] = `Bearer ${config.authToken}`;
      const result = await proxyPost(config.pythonHost!, config.pythonPort!, '/a2a/jsonrpc', body, headers);
      res.writeHead(result.statusCode, { 'Content-Type': 'application/json' });
      res.end(result.body);
    } else if (url.pathname === '/a2a/metrics') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ service: 'agentwire-plugin', uptime: process.uptime() }));
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Not Found' }));
    }
  } catch (e) {
    console.error('[AgentWire Plugin] Error:', e);
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Internal Server Error' }));
  }
}

export function activate(cfg?: Config) {
  config = { ...config, ...cfg };
  console.log('[AgentWire Plugin] 启动中...');
  const http = require('http');
  server = http.createServer(handleRequest);
  server.on('error', (err: any) => {
    if (err && err.code === 'EADDRINUSE') {
      // 端口已被占用 (openclaw gateway 自己的 A2A 服务或其他进程).
      // 优雅降级: 当 A2A 服务的 skip 模式运行 (no-op proxy).
      console.warn(
        `[AgentWire Plugin] 端口 ${config.port} 已被占用 (${err.message || 'EADDRINUSE'}). ` +
        'A2A 服务由其他进程提供, 插件以 skip 模式运行. ' +
        '如需插件自己 listen, 修改 openclaw.plugin.json 的 port 字段.'
      );
      server = null;
    } else {
      console.error(`[AgentWire Plugin] 启动错误: ${err && err.message ? err.message : err}`);
    }
  });
  server.listen(config.port!, () => {
    console.log(`[AgentWire Plugin] 已启动: http://localhost:${config.port}`);
  });
}

export async function deactivate() {
  if (server) { await new Promise(r => server.close(r)); server = null; }
  // port busy → server null, nothing to clean up
}
