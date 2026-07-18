# Legacy: OpenClaw A2A Gateway Sidecar (已下线)

2026-07-18 v2.3 落地后下线。这是 v2.3 之前的临时 A2A adapter：
- 独立 Python 进程，端口 18802
- 把 A2A JSON-RPC 翻译成 OpenClaw 私有 `/tools/invoke`
- 依赖 OpenClaw 私有 API，2026-07-10 起 `/tools/invoke` 返回 500，sidecar 失效
- PID 476004 死亡后未重启

## 被 v2.3 替代

v2.3 用 OpenClaw 原生 plugin（`agentwire-a2a`，TS）替代本 sidecar：
- plugin 跑在 OpenClaw gateway 进程内（18789），无独立进程
- 通过 `openclaw agent` CLI 调 agent（绕开私有 API）
- 标准 A2A v1.0 边界，不追逐 OpenClaw 私有端点

## 留档原因

记录"翻译 sidecar 追逐私有 API"的失败模式，避免重蹈。详见
`../DESIGN.md`「为什么需要 v2.3」。

## 不要重新启用

本目录代码已过时，依赖的 `/tools/invoke` 已被 OpenClaw 移除。
重新启用无意义，且会与 v2.3 plugin 端口/职能冲突。
