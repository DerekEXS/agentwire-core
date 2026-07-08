# AgentWire SKILL 中文版 — 通用协议指南

> **语言**: 简体中文 | [English](SKILL.md)
> **当前版本**: CORE v2.0.1 / CUE v2.0.0

## 什么是 AgentWire?

AgentWire 是实现 [A2A (Agent-to-Agent) v1.0.1](https://a2a-protocol.org) 规范的**协议网关**。它让异构 AI agent 在统一的 JSON-RPC 接口上互相通信，无论宿主平台是 OpenClaw、QwenPaw、Hermes、Claude 还是任何自定义 agent 框架。

AgentWire **不是** agent 框架。它**不**生成回复、不规划任务、不维护会话状态。它是**线协议层**——纯粹的通讯基础设施，负责:

- 接收任何 agent 的 A2A 格式消息
- 鉴权与路由
- 持久化任务状态和消息历史
- 通过标准 A2A 语义转发给其他 agent
- 暴露 Agent Card 用于发现 (`/.well-known/agent.json`)

扩展点 (statechart 工作流、自定义路由、插件动作) **不属于 core 范围**。配套项目 [agentwire-cue](https://github.com/DerekEXS/agentwire-cue) 在 AgentWire 之上提供 YAML 驱动的插件 host。

## 何时该接入 AgentWire?

满足**任一**条件时建议接入:

- 你需要发送任务给远程 agent 并取回结构化响应
- 你需要持久化审计轨迹（谁对谁说了什么）——history
- 你需要一个稳定的 JSON-RPC 端点，任何第三方 agent 可发现
- 你在同一台机器上跑多个 agent，想让它们通过统一 wire 通信

**不要**接入的情况:

- 你构建的是单进程 agent，无 agent 间通信
- 你在构建低延迟流式管道（AgentWire 是 request/response，不是纯 push）

## 架构速览

```
┌────────────────────────────────────────────────┐
│         AgentWire A2A Gateway (CORE)          │
│  - Python aiohttp HTTP 服务                   │
│  - HTTP/1.1 上的 JSON-RPC 2.0                 │
│  - Bearer-token 鉴权 (hmac.compare_digest)    │
│  - JSONL history 持久化(按 peer 分文件)      │
│  - 敏感数据脱敏(patterns 端点)              │
│  - TLS 支持 (--tls-cert / --tls-key)         │
│  - Docker Compose 部署                        │
└────────────────────────────────────────────────┘
        ▲                              ▲
        │ HTTP + Bearer token          │ HTTP + Bearer token
        │                              │
┌───────┴────────┐            ┌───────┴────────┐
│  任意 AI Agent  │            │  任意 AI Agent  │
│  (TS / Python │            │  (TS / Python │
│   / Rust / Go) │            │   / 等)         │
└────────────────┘            └────────────────┘
```

AgentWire 两端皆可插拔——任意 agent 平台均可封装 JSON-RPC 表面。预建平台接入:

- [OpenClaw](INTEGRATION_OpenClaw.md) — TypeScript
- [QwenPaw](INTEGRATION_QwenPaw.md) — Python
- [Hermes](INTEGRATION_Hermes.md) — 通用
- [Claude](INTEGRATION_Claude.md) — Python / TypeScript
- [通用 / 自定义](INTEGRATION_Generic.md) — 任意 HTTP 客户端

## 最简接入（5 行）

```bash
# 发现网关
curl -s http://127.0.0.1:18800/.well-known/agent.json
```

```python
# 通过标准 A2A JSON-RPC 发送消息
import requests
r = requests.post(
    "http://127.0.0.1:18800/a2a/jsonrpc",
    headers={
        "Authorization": f"Bearer {TOKEN}",
        "A2A-Version": "1.0",
        "Content-Type": "application/json",
    },
    json={
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "msg-001",
                "role": "user",
                "parts": [{"type": "text", "text": "你好"}],
            },
        },
    },
)
print(r.json())
```

至此，你已能与 AgentWire 对话。

## 核心能力

| 能力 | API | 备注 |
|------------|-----|-------|
| 发现 | `GET /.well-known/agent.json` (主) | 公开；返回标准 A2A Agent Card |
| 发现（兼容） | `GET /.well-known/agent-card.json` | 同上；来自 a2a-sdk |
| 发送消息 | `POST /a2a/jsonrpc` `SendMessage` | 标准 A2A gRPC 风格方法（PascalCase） |
| 取任务 | `POST /a2a/jsonrpc` `GetTask` | 需 Bearer auth；返回 Task 状态 |
| 列任务 | `POST /a2a/jsonrpc` `ListTasks` | 需 Bearer auth；支持分页 |
| 取消任务 | `POST /a2a/jsonrpc` `CancelTask` | 需 Bearer auth |
| 流式 | `POST /a2a/jsonrpc` `SendStreamingMessage` | SSE 流式(v2.0.0+) |
| 健康检查 | `GET /health` | 公开 |
| 脱敏规律 | `GET /redact/patterns` | 需 Bearer auth; 共享给插件 host |
| 指标 | `GET /a2a/metrics` | **v1.5.2**: 需要 Bearer auth（≤v1.5.1 时公开） |

> **版本说明 (v2.0.0)**: 标准 A2A 方法名采用 **PascalCase**（如 `SendMessage`，而不是 REST 风格的 `message/send`），与 a2a-sdk 的 protobuf 调度一致。`/a2a/rest/message/send` REST 路径已**移除**；请改用标准 `/a2a/jsonrpc` 加上 `SendMessage` 方法。旧的 `messages/list`、`messages/get`、`messages/peers`、`messages/import`、`messages/export` 方法在 v1.x server（端口 18800）仍可用以保持向后兼容，但不再是推荐路径。完整方法列表见 [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md)。

## 快速启动

### 推荐: Docker Compose

```bash
cd agentwire_cue
mkdir -p secrets
printf '%s\n' 'YOUR_A2A_TOKEN' > secrets/a2a-token.txt
printf '%s\n' 'YOUR_ADMIN_TOKEN' > secrets/cue-admin-token.txt
chmod 600 secrets/*.txt
docker compose up -d
curl -s http://127.0.0.1:18800/.well-known/agent.json
```

### 备选: Python 原生

```bash
cd server
pip install -r requirements.txt
echo "YOUR_A2A_TOKEN" > /tmp/agentwire.token
chmod 600 /tmp/agentwire.token
python3 start.py --host 127.0.0.1 --port 18800 --token-file /tmp/agentwire.token
```

## 安全默认值 (v1.5.x)

- **默认绑定**: `127.0.0.1`（仅 loopback）。如需暴露到 LAN/VPN，显式传 `--host 0.0.0.0`，服务器会打印警告并要求 token。
- **TLS**: 用 `--tls-cert` + `--tls-key` 启用 HTTPS (v1.4.9+)。
- **Token 卫生**: 启动时检查 UTF-8 BOM、CRLF 换行符、过宽的文件权限 (v1.4.8)。
- **日志脱敏**: 消息原文**永不进日志**——只记录消息长度 `len=` 和 sha256 前 16 位 `hash=`，以及经过哈希的 peer 标识 (v1.5.1+)。
- **导入/导出限制**: `messages/import` 每次最多 100 条，单条 64KB（硬上限 500/256KB 可通过环境变量调整）。`messages/export` 支持分页（默认 50 行，最大 200）。
- **指标接口鉴权**: `/a2a/metrics` 从 v1.5.2 起需要 Bearer auth。
- **工作流钩子**: 默认关闭；开启时 `allowed_commands` 白名单控制可执行的命令。

## 发布流程

所有 commit 使用 `silk-thread` 化名。当本地代理 (mihomo TUN) 拦截 SSH 时，使用 [Composio](https://composio.dev) `GITHUB_COMMIT_MULTIPLE_FILES` / `GITHUB_CREATE_A_RELEASE` 工具链 fallback 发布。两种路径产出相同的公开发布。

## 从哪里继续阅读

| 如果你是… | 读… |
|-------------|-------|
| OpenClaw agent | [INTEGRATION_OpenClaw.md](INTEGRATION_OpenClaw.md) |
| QwenPaw agent | [INTEGRATION_QwenPaw.md](INTEGRATION_QwenPaw.md) |
| Hermes agent | [INTEGRATION_Hermes.md](INTEGRATION_Hermes.md) |
| Claude agent | [INTEGRATION_Claude.md](INTEGRATION_Claude.md) |
| 使用任意语言的 agent 开发者 | [INTEGRATION_Generic.md](INTEGRATION_Generic.md) |
| CUE host 插件作者 | [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) |
| 查 JSON-RPC 方法签名 | [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md) |

## 开源许可

MIT License. Copyright (c) 2026 DerekEXS.

## 协议与参考

- **A2A 协议**: v1.0.1 — <https://a2a-protocol.org/latest/specification/>
- **JSON-RPC 2.0**: <https://www.jsonrpc.org/specification>
- **仓库**: <https://github.com/DerekEXS/agentwire-core>
- **Release**: <https://github.com/DerekEXS/agentwire-core/releases>

## 变更亮点

| 版本 | 关键变更 |
|---------|-------------|
| v1.4.3 | History 持久化、消息 API、脱敏目录 |
| v1.4.8 | `messages/import`、token 健康诊断 |
| v1.4.9 | TLS 支持、`CORE_LISTEN_HOST` 环境变量 |
| v1.5.0 | Docker + compose、`CORE_LISTEN_PORT` / `AGENTWIRE_TOKEN_FILE` 环境变量 |
| v1.5.1 | 日志脱敏 (`len= hash=`)、导入/导出大小限制与分页、插件入站鉴权 + loopback 绑定 |
| v1.5.2 | `/a2a/metrics` 鉴权、token 路径脱敏、workflow `allowed_commands`、compose loopback 发布、示例 token 替换 |
| v1.5.3 | 全部 SKILL 文件同步至当前功能状态 |
| v1.5.4 | 版本字符串统一 + 插件自加载 manifest 修复 |
| v1.5.5 | OpenClaw 2026.6.6 schema 适配(`additionalProperties`、`kind: "http-server"`、`uiHints`)、README 刷新 |
| v1.5.6 | CORE 实时推送 CUE（`_forward_to_cue()`）—— 恢复 `a2a_content_match` push 路径 |
| **v2.0.0** | **架构重写**：基于官方 `a2a-sdk>=1.1.0`。标准 A2A 方法（PascalCase `SendMessage`、`GetTask`、`ListTasks`、`CancelTask`、`SendStreamingMessage`），SQLite TaskStore，agent 路由（显式 → 规则 → 默认），Agent Card 在 `/.well-known/agent.json`，Bearer token 中间件（`hmac.compare_digest`），Dockerfile.v2 |
| **v2.0.1** | **Hotfix**：同时暴露 `/.well-known/agent.json`（标准 A2A 主路径）与 `/.well-known/agent-card.json`（SDK 兼容路径），两者返回内容相同，与 CUE v2.0 行为一致 |
