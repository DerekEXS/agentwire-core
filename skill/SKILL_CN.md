# AgentWire SKILL 中文版 — 通用协议指南

> **语言**: 简体中文 | [English](SKILL.md)

## 什么是 AgentWire?

AgentWire 是实现 [A2A (Agent-to-Agent) v1.0.1](https://a2a-protocol.org) 规范的**协议网关**。它让异构 AI agent 可以在统一的 JSON-RPC 接口上互相通信,无论宿主平台是 OpenClaw、QwenPaw、Hermes、Claude 还是任何自定义 agent 框架。

AgentWire **不是** agent 框架。它**不**生成回复、不规划任务、不维护会话状态。它是**线协议层**——纯粹的通讯基础设施,负责:

- 接收任何 agent 的 A2A 格式消息
- 鉴权与路由
- 持久化任务状态和消息历史
- 通过标准 A2A 语义转发给其他 agent
- 暴露 Agent Card 用于发现 (`/.well-known/agent.json`)

扩展点 (statechart 工作流、自定义路由、插件动作) **不属于 core 范围**。配套项目 [agentwire-cue](https://github.com/DerekEXS/agentwire-cue) 在 AgentWire 之上提供 YAML 驱动的插件 host。

## 何时该接入 AgentWire?

满足**任一**条件时建议接入:

- 你需要发送任务给远程 agent 并取回结构化响应
- 你需要持久化审计轨迹(谁对谁说了什么)——history
- 你需要一个稳定的 JSON-RPC 端点,任何第三方 agent 可发现
- 你在同一台机器上跑多个 agent,想让它们通过统一 wire 通信

**不要**接入的情况:

- 你构建的是单进程 agent,无 agent 间通信
- 你在构建低延迟流式管道(AgentWire 是 request/response,不是纯 push)

## 架构速览

```
┌────────────────────────────────────────────────┐
│         AgentWire A2A Gateway (CORE)          │
│  - Python aiohttp HTTP 服务                   │
│  - HTTP/1.1 上的 JSON-RPC 2.0                 │
│  - Bearer-token 鉴权                          │
│  - JSONL history 持久化(按 peer 分文件)      │
│  - 敏感数据脱敏(patterns 端点)              │
│  - A2A v1.0.1 协议                            │
└────────────────────────────────────────────────┘
        ▲                              ▲
        │ HTTP + Bearer token          │ HTTP + Bearer token
        │                              │
┌───────┴────────┐            ┌───────┴────────┐
│  任意 AI Agent  │            │  任意 AI Agent  │
│  (TS / Python │            │  (TS / Python │
│   / Rust / Go) │            │   / etc.)      │
└────────────────┘            └────────────────┘
```

AgentWire **两侧都开放插件**:任何 agent 平台都可以包装 JSON-RPC 接口。已提供开箱即用的平台集成:

- [OpenClaw](INTEGRATION_OpenClaw.md) — TypeScript
- [QwenPaw](INTEGRATION_QwenPaw.md) — Python
- [Hermes](INTEGRATION_Hermes.md) — 通用
- [Claude](INTEGRATION_Claude.md) — Python / TypeScript
- [通用 / 自定义](INTEGRATION_Generic.md) — 任何 HTTP 客户端

## 最小可运行集成(5 行)

```bash
# 发现 gateway
curl -s http://localhost:18800/.well-known/agent.json
```

```python
# 发送消息
import requests
r = requests.post(
    "http://localhost:18800/a2a/rest/message/send",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"message": {"parts": [{"type": "text", "text": "Hello"}]}},
)
print(r.json())
```

就这些——你已经能跟 AgentWire 对话了。

## 核心能力

| 能力 | API | 备注 |
|------|-----|------|
| 发现 | `GET /.well-known/agent.json` | 返回 Agent Card(v1.4.3+;v1.4.2 有路由 bug) |
| 发消息 | `POST /a2a/rest/message/send` | `message/send` JSON-RPC 的 REST 包装 |
| 健康检查 | `GET /health` | v1.4.3+;v1.4.2 有路由 bug |
| 列任务 | `tasks/list` (JSON-RPC) | v1.4.3+(完整 JSON-RPC 端点) |
| 取任务 | `tasks/get` (JSON-RPC) | v1.4.3+ |
| 取消任务 | `tasks/cancel` (JSON-RPC) | v1.4.3+ |
| 消息历史 | `messages/list`, `messages/get`, `messages/peers`, `messages/export` | **v1.4.3 新增** |
| 脱敏 patterns | `GET /redact/patterns` | **v1.4.3 新增**——与 plugin host 共享 |
| 指标 | `GET /a2a/metrics` | 任务计数 |

## 快速开始(运维视角)

```bash
# 1. 安装
cd server
pip install -r requirements.txt
cp config.yaml.example config.yaml  # 按需编辑
echo "my-token-123" > /tmp/agentwire.token

# 2. 运行(只监听 loopback,带 token)
python3 start.py --host 127.0.0.1 --port 18800 --token-file /tmp/agentwire.token

# 3. 测试
curl -s http://127.0.0.1:18800/.well-known/agent.json
curl -X POST http://127.0.0.1:18800/a2a/rest/message/send \
  -H "Authorization: Bearer my-token-123" \
  -H "Content-Type: application/json" \
  -d '{"message":{"parts":[{"type":"text","text":"ping"}]}}'
```

## 下一步阅读

| 如果你是… | 读… |
|----------|------|
| OpenClaw agent | [INTEGRATION_OpenClaw.md](INTEGRATION_OpenClaw.md) |
| QwenPaw agent | [INTEGRATION_QwenPaw.md](INTEGRATION_QwenPaw.md) |
| Hermes agent | [INTEGRATION_Hermes.md](INTEGRATION_Hermes.md) |
| Claude agent | [INTEGRATION_Claude.md](INTEGRATION_Claude.md) |
| 任何自定义 agent | [INTEGRATION_Generic.md](INTEGRATION_Generic.md) |
| 开发 cue 插件 | [PLUGIN_DEVELOPMENT.md](PLUGIN_DEVELOPMENT.md) |
| 查 JSON-RPC 方法签名 | [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md) |

## 许可证

MIT License。Copyright (c) 2026 DerekEXS。详见 [LICENSE](../LICENSE)。

## 协议与参考

- **A2A 协议**: v1.0.1 — <https://a2a-protocol.org/latest/specification/>
- **JSON-RPC 2.0**: <https://www.jsonrpc.org/specification>
- **仓库**: <https://github.com/DerekEXS/agentwire-core>
- **发布**: <https://github.com/DerekEXS/agentwire-core/releases>

## v1.4.2 已知问题(v1.4.3 修复)

- `GET /.well-known/agent.json` 和 `GET /health` 在 v1.4.2 没注册(handler 函数存在但 `_setup_routes()` 没调)
- `POST /a2a/jsonrpc` 没注册;只暴露 `/a2a/rest/message/send`
- 无消息历史端点
- 无 `redact/patterns` 端点

v1.4.3 全部修复。
