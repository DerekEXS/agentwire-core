# AgentWire

> **A2A v1.0.1 通讯网关** —— 面向 AI agent 的纯线协议层
>
> **语言**: 简体中文 (本文) | [English](README.md)

[![A2A Protocol](https://img.shields.io/badge/A2A-v1.0.1-blue)](https://a2a-protocol.org/latest/specification/)
[![JSON-RPC](https://img.shields.io/badge/JSON--RPC-2.0-orange)](https://www.jsonrpc.org/specification)
[![许可证](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-18%2B-green)](https://nodejs.org)
[![状态](https://img.shields.io/badge/status-v1.5.5-green)](https://github.com/DerekEXS/agentwire-core/releases/tag/v1.5.5)

---

## AgentWire 是什么?

AgentWire 是实现 [A2A (Agent-to-Agent) v1.0.1](https://a2a-protocol.org) 规范的**协议网关**。它让异构 AI agent 通过统一的 JSON-RPC 接口互相通信,无论宿主平台是 OpenClaw、QwenPaw、Hermes、Claude 还是任何自定义框架。

AgentWire **不是** agent 框架。它**不**生成回复、不规划任务、不维护会话状态。它是**线协议层**,负责:

- 接收任何 agent 的 A2A 格式消息
- 鉴权与路由
- 持久化任务状态与按 peer 的消息历史
- 通过标准 A2A 语义转发给其他 agent
- 暴露 Agent Card 用于服务发现

工作流编排、状态机、插件动作**不属于 core 范围**。协议是稳定的;行为是纯粹的传输 + 持久化。

## 特性

- **A2A v1.0.1** —— 完整支持 `/.well-known/agent.json`、`message/send`、`tasks/*`、Agent Card
- **HTTP 上的 JSON-RPC 2.0** —— 标准、语言无关的传输
- **Bearer-token 鉴权** —— 支持文件/环境变量/参数三种来源,非安全 bind 直接失败 (HMAC 常量时间比较)
- **默认 loopback 绑定** (`127.0.0.1`);绑 `0.0.0.0` 需显式 `--host 0.0.0.0` 并打 startup warning (v1.4.9)
- **内置 TLS** —— `--tls-cert` + `--tls-key` 双参数启用 (v1.4.9)
- **CORS 白名单** —— 仅显式 origin,无通配符
- **按 peer 消息历史** —— 自动存为 JSONL,可轮转,可设 FIFO 上限
- **上下文自动注入** —— 最近 N 轮对话作为元数据附加,agent 可恢复上下文
- **`messages/import` JSON-RPC 端点** —— 历史恢复场景 (v1.4.8);每请求 100 条/单 part 64KB 上限 (v1.5.1)
- **`messages/export` 分页** —— `limit` (1..200) / `offset` / `total_count` / `has_more` (v1.5.1)
- **敏感数据脱敏** —— 内置 patterns,通过 `/redact/patterns` 共享给客户端工具复用
- **`/a2a/metrics` 需 Bearer auth** —— 与 `/a2a/jsonrpc` 同款 HMAC compare (v1.5.2)
- **Token 文件健康检测** —— UTF-8 BOM 自动剥离、CRLF 告警、文件权限告警 (v1.4.8)
- **日志脱敏** —— 入站消息文本仅 hash,不打印明文 (v1.5.1)
- **Workflow-hook allowlist** —— `WORKFLOW_HOOK_CONFIG.allowed_commands` 限制外部二进制调用 (v1.5.2)
- **TypeScript OpenClaw 插件** —— 带 `agentCard` 扩展与自加载 `defaultConfig`,`openclaw.plugin.json` 已适配 OpenClaw 2026.6.6 schema (v1.5.4 / v1.5.5)

## 架构

```
┌────────────────────────────────────────────────┐
│         AgentWire A2A Gateway (CORE)          │
│                                                │
│  Python aiohttp ── HTTP/1.1 ── JSON-RPC 2.0  │
│  ┌────────────────────────────────────────┐  │
│  │  鉴权 (Bearer token)                   │  │
│  │  路由 (A2A 方法 + REST)                │  │
│  │  历史 (按 peer JSONL + 脱敏)          │  │
│  │  脱敏 (共享 pattern 目录)              │  │
│  └────────────────────────────────────────┘  │
│  HTTP 18800 (默认)                             │
└────────────────────────────────────────────────┘
        ▲                              ▲
        │ HTTP + Bearer                │ HTTP + Bearer
        │                              │
┌───────┴────────┐            ┌───────┴────────┐
│  任意 AI Agent  │            │  任意 AI Agent  │
│  (TS / Python │            │  (TS / Python │
│   / Rust / Go) │            │   / etc.)      │
└────────────────┘            └────────────────┘
```

`plugin/` 下的 TypeScript 插件是给 OpenClaw 类 agent 用的一种绑定方式。其他 agent 可直接对接 JSON-RPC 接口。

## 快速开始

### 推荐: Docker Compose (与 AgentWire-Cue 一起)

CORE 以容器镜像形式分发。直接用 [agentwire-cue 仓库的 compose](https://github.com/DerekEXS/agentwire-cue/blob/main/docker-compose.yml) 拉起 CORE + CUE:

```bash
git clone https://github.com/DerekEXS/agentwire-cue.git
cd agentwire-cue
mkdir -p secrets
printf '%s\n' 'YOUR_A2A_TOKEN' > secrets/a2a-token.txt
printf '%s\n' 'YOUR_CUE_ADMIN_TOKEN' > secrets/cue-admin-token.txt
chmod 600 secrets/*.txt
docker compose up -d

# 健康检查
docker ps
curl -s http://127.0.0.1:18800/.well-known/agent.json
```

CORE 监听 `127.0.0.1:18800`;CUE 监听 `127.0.0.1:18801` (A2A) + `127.0.0.1:19000` (admin)。

### 独立运行 (Python 直接起)

若不想用 Docker:

```bash
cd server
pip install -r requirements.txt
cp config.yaml.example config.yaml
echo "my-token-123" > /tmp/agentwire.token

python3 start.py \
  --host 127.0.0.1 \
  --port 18800 \
  --token-file /tmp/agentwire.token
```

### 测试

```bash
# 发现
curl -s http://127.0.0.1:18800/.well-known/agent.json

# 健康检查
curl -s http://127.0.0.1:18800/health

# 发消息
curl -X POST http://127.0.0.1:18800/a2a/rest/message/send \
  -H "Authorization: Bearer my-token-123" \
  -H "Content-Type: application/json" \
  -d '{"message":{"parts":[{"type":"text","text":"你好"}]}}'
```

### 构建 TypeScript OpenClaw 插件(可选)

```bash
cd plugin
npm install
npm run build
```

把 `dist/` 放到你的 OpenClaw 插件加载器里。Manifest 已适配 OpenClaw 2026.6.6 schema:`additionalProperties: false`、`kind: "http-server"`、`uiHints` 全字段标注、`version: "1.5.5"` 与 CORE 镜像 tag 对齐。

## 配置

编辑 `server/config.yaml` (完整模板见 `config.yaml.example`)。两个顶层段:

### `workflow_hook` (可选)

关键词匹配时触发外部 agent CLI (如 OpenClaw):

```yaml
workflow_hook:
  enabled: true
  openclaw_path: "/path/to/openclaw"
  agent_id: "main"
  workflow_path: "/path/to/your/workflow"
  trigger_keywords: ["project:", "scenes:", "video"]
  trigger_min_lines: 5
  timeout: 300
```

### `history` (v1.4.3+)

按 peer 的 JSONL 消息历史,可选脱敏与上下文注入:

```yaml
history:
  enabled: true
  max_rounds_per_peer: 0        # 0 = 无限(默认)
  context_rounds: 5             # 0 = 关闭
  storage_dir: "~/.local/share/agentwire/history"
  redact_sensitive: true
  round_close:
    mode: heuristic             # heuristic | explicit
    heuristic_idle_seconds: 300
```

## HTTP API

| 方法 | 路径 | 鉴权 | 用途 |
|------|------|------|------|
| GET | `/.well-known/agent.json` | 可选 | Agent Card 发现 |
| GET | `/health` | 无 | 存活探针 |
| GET | `/a2a/metrics` | Bearer (v1.5.2) | 任务计数 |
| GET | `/redact/patterns` | 必需 | 共享脱敏 pattern 目录 |
| POST | `/a2a/jsonrpc` | 必需 | JSON-RPC 2.0 端点 |
| POST | `/a2a/rest/message/send` | 必需 | `message/send` 的 REST 包装 |

## JSON-RPC 方法

标准 A2A v1.0.1:

- `message/send` —— 发消息,返回 task
- `tasks/get` —— 按 ID 取 task
- `tasks/list` —— 列内存中所有 task
- `tasks/cancel` —— 取消 task
- `tasks/subscribe` —— 订阅占位(空实现)
- `agent/getCard` —— 返回 Agent Card

历史:

- `messages/list` —— 查一个或所有 peer 的最近消息
- `messages/get` —— 查单个 peer 单轮(outbound + inbound)
- `messages/peers` —— 列已知 peer 与元数据
- `messages/export` —— 导出某 peer 历史为 JSONL 或 Markdown
  - 分页:`limit` (1..200,默认 100)、`offset`,返回 `total_count` + `has_more` (v1.5.1)
- `messages/import` (v1.4.8) —— 把外部消息追加到某 peer 历史
  - 上限:每请求 100 条、单 part 64KB、硬上限 256KB (v1.5.1)

完整 schema 见 [`skill/PROTOCOL_QUICK_REF.md`](skill/PROTOCOL_QUICK_REF.md)。

## 仓库结构

```
agentwire-core/
├── server/                       # Python A2A 服务
│   ├── start.py                  # 主入口
│   ├── proxy.py                  # Loopback 反向代理(18802 → 18800)
│   ├── history.py                # 按 peer JSONL 持久化
│   ├── redact.py                 # 敏感 pattern 目录
│   ├── config.yaml.example       # 配置模板
│   ├── requirements.txt
│   ├── Dockerfile                # v1.5.0: python:3.13-slim 容器构建
│   └── README.md
│
├── plugin/                       # TypeScript OpenClaw 插件
│   ├── src/
│   │   └── index.ts
│   ├── openclaw.plugin.json      # v1.5.5: OpenClaw 2026.6.6 schema (additionalProperties、kind、uiHints)
│   ├── package.json
│   └── tsconfig.json
│
├── skill/                        # agent 文档
│   ├── SKILL.md                  # 通用协议指南
│   ├── SKILL_CN.md               # 中文版
│   ├── PROTOCOL_QUICK_REF.md     # 方法签名速查
│   ├── INTEGRATION_OpenClaw.md
│   ├── INTEGRATION_QwenPaw.md
│   ├── INTEGRATION_Hermes.md
│   ├── INTEGRATION_Claude.md
│   ├── INTEGRATION_Generic.md
│   └── PLUGIN_DEVELOPMENT.md
│
├── docker-compose.yml            # v1.5.0: 独立 CORE compose
├── .gitignore
├── LICENSE
└── README.md                     # 本文件
```

## 集成指南

按你的 agent 平台选对应集成文档:

- [OpenClaw](skill/INTEGRATION_OpenClaw.md) —— TypeScript 插件复用
- [QwenPaw](skill/INTEGRATION_QwenPaw.md) —— Python A2A 客户端
- [Hermes](skill/INTEGRATION_Hermes.md) —— 通用适配器
- [Claude](skill/INTEGRATION_Claude.md) —— Claude Code / Claude API
- [自定义 agent](skill/INTEGRATION_Generic.md) —— 任何 HTTP 客户端

要更深入理解协议,读 [SKILL.md](skill/SKILL.md) (中文看 [SKILL_CN.md](skill/SKILL_CN.md))。

如果你要为 AgentWire 兼容的 host 编写 YAML statechart 插件,见 [PLUGIN_DEVELOPMENT.md](skill/PLUGIN_DEVELOPMENT.md)。

## 安全性

- 所有非 loopback 请求**必须**带 Bearer token (HMAC 常量时间比较)
- **`/a2a/metrics`** 需 Bearer auth (v1.5.2)
- CORS 用**显式** origin 白名单(无通配符)
- **默认 loopback 绑定** —— `127.0.0.1` 默认;`0.0.0.0` 需显式 `--host 0.0.0.0` 并打 startup warning
- **内置 TLS** —— `--tls-cert` + `--tls-key` 双参数启用 (v1.4.9)
- **自动脱敏** API key、token、JWT、私钥、URL 内嵌密码(任何历史持久化前)
- **日志脱敏** —— 入站消息文本仅保留 `len=... sha256[:16]=... peer=...` (v1.5.1)
- **Token 文件健康检测** —— UTF-8 BOM 自动剥离、CRLF + chmod 告警 (v1.4.8)
- **内部错误不外泄** —— 服务端日志完整,客户端只收通用 500
- **Workflow-hook allowlist** —— `WORKFLOW_HOOK_CONFIG.allowed_commands` 限制外部二进制调用 (v1.5.2)

## 部署说明

> ⚠️ **明文 HTTP**: AgentWire CORE 默认明文 HTTP(非 HTTPS),`Authorization: Bearer <token>` 在网络上**明文传输**。可通过 `--tls-cert` + `--tls-key` 启用 TLS (v1.4.9)。

### Docker(推荐)

CORE 镜像 `agentwire-core:v1.5.5` 与 CUE 一同在 [agentwire-cue 仓的 docker-compose.yml](https://github.com/DerekEXS/agentwire-cue/blob/main/docker-compose.yml) 发布。Compose 把 CORE 跑在 `127.0.0.1:18800`、CUE 跑在 `127.0.0.1:18801` + `127.0.0.1:19000`,都仅 host loopback 发布并共享 token secret。

```bash
git clone https://github.com/DerekEXS/agentwire-cue.git
cd agentwire-cue
mkdir -p secrets
printf '%s\n' 'YOUR_A2A_TOKEN' > secrets/a2a-token.txt
printf '%s\n' 'YOUR_CUE_ADMIN_TOKEN' > secrets/cue-admin-token.txt
chmod 600 secrets/*.txt
docker compose up -d
```

### 独立运行

参考上面的 [快速开始](#快速开始)。

### 适用于

- 仅 loopback 部署(单机 agent on `127.0.0.1:18800`)
- 私有 LAN / Tailscale / WireGuard 等网络本身可信的场景
- TLS 终止反向代理前端(nginx / Caddy / Traefik / Cloudflare Tunnel)

### 不适用于

- 无 TLS 直接暴露公网

### 如必须暴露 AgentWire 到不可信网络

1. **必须**: 在前端部署 TLS 终止反向代理,**或** 启动 CORE 时带 `--tls-cert` + `--tls-key`
2. **建议**: CORE 只绑 loopback(`--host 127.0.0.1`);反向代理对外暴露公网端口
3. **强烈建议**: 定期轮换 bearer token,使用 32+ 字符随机值
4. **可考虑**: 双向 mTLS(若你控制两端;AgentWire 暂不直接支持 mTLS——这是未来候选)

## 协议

- **A2A v1.0.1** —— <https://a2a-protocol.org/latest/specification/>
- **JSON-RPC 2.0** —— <https://www.jsonrpc.org/specification>

## 参考

- [A2A 协议规范](https://a2a-protocol.org/latest/specification/)
- [JSON-RPC 2.0 规范](https://www.jsonrpc.org/specification)
- [发布](https://github.com/DerekEXS/agentwire-core/releases)
- [问题](https://github.com/DerekEXS/agentwire-core/issues)

## 许可证

**MIT License** —— Copyright (c) 2026 DerekEXS。完整文本见 [LICENSE](LICENSE)。

可自由使用、修改、分发本软件(有或无修改),前提是保留版权声明和许可声明。
