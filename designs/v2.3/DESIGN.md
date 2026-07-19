# AgentWire v2.3 — OpenClaw 原生 A2A Plugin

> **Date**: 2026-07-18
> **Target tag**: `v2.3.0`
> **Owner**: 丝线 (silk-thread)
> **Classification**: 设计文档（实施前评审）
> **依据**: [[openclaw-2026-7-1-a2a-plugin-contract]]（SDK 契约，已源码验证）
> **修订**: R1（2026-07-18）—— 5 项评审反馈落实，见文末「评审修订记录」

---

## 🎯 为什么需要 v2.3

### 触发事件（2026-07-18）

OpenClaw agent 集体报「Gateway 进程 476004 不存在」。诊断链：

1. `~/.openclaw/a2a-gateway/a2a-gateway.pid` = **476004** → 死亡。
2. 该进程是一个**独立 Python sidecar**（端口 18802），把 A2A 翻译成 OpenClaw 私有 `/tools/invoke`。最后日志 2026-07-10 03:15，且已出现 `OpenClaw HTTP error: 500 tool_error`。
3. 同时 CORE v2.2.0 的 `_dispatch_via_openclaw()` 打 `http://127.0.0.1:18789/rpc/agent` → **404**（OpenClaw 2026.7.1 删了该 HTTP RPC 端点，改 WebSocket）。
4. **双重断裂**：① CORE 打 18789→404；② 真正能翻译的 18802 sidecar 死了，且它依赖的 `/tools/invoke` 也 500。

### 根病灶

不是「某个端点没了」，而是**用翻译 sidecar 追逐 OpenClaw 私有 API**。OpenClaw 每升一次级，sidecar 坏一次：
- 2026-07-07：`activate()` → `definePluginEntry` 入口变
- 2026-07-18：`/rpc/agent` 删除、`/tools/invoke` 500

这是无限追逐，违反 CLAUDE.md 规则 4（不自造协议层）和「不要当中转器」教训。

### 彻底解法

写一个 **OpenClaw 原生 plugin**（`@agentwire/a2a-adapter`），跑在 OpenClaw gateway 进程内（18789），用 plugin SDK 公开契约暴露标准 A2A v1.0，用 `gateway.request("agent")` 进程内调 agent。**单一 A2A 边界，无 sidecar，无私有 API 追逐。**

```
外部 Agent ──► CORE 18880 ──► 18789/a2a/jsonrpc ──► [原生 plugin] ──► gateway.request("agent") ──► agent-main/agent-hound/agent-forge
                                  ↑ 标准 A2A 边界（稳定）              ↑ plugin SDK 公开契约
```

---

## 📐 架构

### 仓子结构（沿用 core 仓，重写 `plugin/` 子目录）

```
agentwire_core/
├── server_v2/          # Python A2A gateway（不变，v2.2.0）
├── plugin/             # ← 重写：TS OpenClaw 原生 A2A plugin
│   ├── openclaw.plugin.json   # manifest（新 schema）
│   ├── package.json           # ESM, openclaw.extensions
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts           # definePluginEntry 入口
│   │   ├── routes.ts          # /a2a/jsonrpc + /.well-known/agent.json 路由
│   │   ├── a2a.ts             # A2A JSON-RPC 方法处理（仅 SendMessage）
│   │   ├── dispatch.ts        # gateway.request("agent") 封装
│   │   └── config.ts          # plugin config schema + agent 列表
│   │   # 无 tasks.ts —— plugin 不维护 task store（见「查询路径澄清」）
│   └── dist/                  # 编译产物（.js，提交进仓以便无构建环境安装）
├── Dockerfile.v2      # Python 镜像（不变，只 COPY server_v2/）
└── docker/            # 配置（不变）
```

**关键隔离纪律**：`Dockerfile.v2` 只 `COPY server_v2/`，不碰 `plugin/`。TS 构建产物不混进 Python Docker 镜像。`plugin/` 有独立 `package.json`/构建，互不污染。

### 职责边界

| 组件 | 职责 | 语言 | 进程 |
|------|------|------|------|
| CORE `server_v2/` | A2A gateway：协议合规、路由、Task 状态机、持久化、metrics | Python | docker 18880 |
| plugin `plugin/` | OpenClaw 进程内 A2A 适配：暴露 `/a2a/jsonrpc` + `/.well-known/agent.json`，A2A ↔ `gateway.request("agent")` 翻译 | TypeScript | OpenClaw 18789 |
| CUE | 工作流引擎（不变） | Python | docker 18801 |

plugin **只做薄翻译**——A2A JSON-RPC ↔ OpenClaw `gateway.request("agent")`。业务逻辑（路由规则、Task 持久化、metrics）仍在 CORE/CUE（Python）。这是职责分离的关键：跨语言成本只付在薄翻译层。

### 数据流（入站 A2A → OpenClaw agent）

```
1. 外部 Agent POST /a2a/jsonrpc (SendMessage) 到 CORE 18880
2. CORE 路由 → peers.openclaw = http://127.0.0.1:18789/a2a/jsonrpc
3. plugin handler 收到，解析 JSON-RPC
4. plugin 调 api.runtime.gateway.request("agent", {
     message: <提取的 text>,
     agentId: <从 A2A metadata.agentId 解析，fallback main>,
     sessionKey: agent:<agentId>:a2a:<task-uuid>,
     deliver: false,
     timeout: 120
   })
5. gateway 同步返回 result.payloads[].text（agent 回复）
6. plugin 包成 A2A Task（COMPLETED + message.parts[].text=回复）
7. 返回 JSON-RPC result 给 CORE → 转发给外部 Agent
```

### 数据流（反向：OpenClaw agent → 外部 A2A）

v2.3.0 范围内**不做完整反向**。理由：现有 silk-bridge.py 已处理 Telegram→A2A 单向；反向（agent 主动发 A2A）依赖 plugin 暴露一个 tool/方法让 agent 调用，属 v2.3.1+。v2.3.0 先把入站闭环做扎实。

> ⚠️ 反向闭环的钩子预留：plugin manifest `contracts.tools` 预留 `a2a_send` 工具名，v2.3.1 实现 tool handler 调 CORE 的 `/a2a/jsonrpc`。

---

## 🔌 SDK 契约映射（已源码验证）

详见 [[openclaw-2026-7-1-a2a-plugin-contract]]。这里只列 v2.3 用到的：

| v2.3 用途 | SDK API | 来源 |
|-----------|---------|------|
| plugin 入口 | `definePluginEntry({ id, name, description, configSchema?, register(api){} })`，`default export` | `plugin-entry-R9cUrV0y.d.ts` |
| HTTP 路由 | `api.registerHttpRoute({ path, handler, auth:"plugin", match?:"exact" })` | `types-DaHgOqFX.d.ts:11710` |
| 读 JSON body | `readJsonWebhookBodyOrReject(req)` | `webhook-ingress.d.ts` |
| 调 agent | `api.runtime.gateway.request("agent", { message, agentId, sessionKey, deliver:false, timeout? })` | `agent-via-gateway-1KwjCa1L.js:406-430` |
| agent 回复 | `result.payloads[].text` | `agent-via-gateway-1KwjCa1L.js:480-489` |
| 安装 | `openclaw plugins install --link <plugin目录>` | CLI |

**关键纠正**（侦察 agent 搞错过）：调 agent 走 `gateway.request("agent")`，**不是** `api.runtime.subagent.run`。后者是派生子 agent 语义，且回复要二次 `getSessionMessages` 查询；前者同步返回 `result.payloads[].text`，是 CLI `openclaw agent` 走的同一条路。

---

## 📋 A2A 方法映射

| A2A JSON-RPC 方法 | plugin 实现 | OpenClaw 侧 |
|-------------------|------------|-------------|
| `SendMessage` | 调 `gateway.request("agent")` 同步 → 构造 A2A Task(COMPLETED + 回复) 返回 | `gateway.request("agent")` 同步 |
| `GetTask` | **不实现**，返回 `-32601`。权威源在 CORE SQLite（见上「查询路径澄清」） | — |
| `ListTasks` | **不实现**，返回 `-32601`。同上 | — |
| `CancelTask` | **不实现**，返回 `-32601`。gateway run 同步执行无法中途取消；取消语义由 CORE SQLite 状态承担 | — |
| `SendStreamingMessage` | v2.3.0 **不支持**，返回 `-32601`（`capabilities.streaming=false`） | — |

### Task 状态机 + 查询路径澄清（回应评审问题二）

**关键澄清**：GetTask/ListTasks 的查询路径——已验证 a2a-sdk 源码：

- `DefaultRequestHandler.on_get_task`（`default_request_handler.py:142-156`）→ `await self.task_store.get()` —— **CORE 本地查 SQLite，不转发给 peer**。
- `on_list_tasks`（同文件:158-172）→ `await self.task_store.list()` —— 同样本地查。

**所以**：外部 Agent 调 CORE 的 GetTask/ListTasks，CORE 自己查 SQLite TaskStore（权威源）。请求**不会**被转发到 plugin。plugin 重启丢失的「task 历史」与外部 Agent 的 GetTask 毫无关系。

**结论：plugin 不维护独立 task store。** v2.3 架构下外部 Agent 一律经 CORE（前置网关），GetTask 走 CORE SQLite；plugin 唯一职责是处理 SendMessage（同步调 agent 返回）。plugin 的 GetTask/ListTasks 方法要么不实现（返回 `-32601`），要么仅返回本次 SendMessage 的同步结果（无历史）。

> 原设计里 plugin 的 in-memory + JSONL task store **删除**。这消除了「plugin 重启 → GetTask 404」的伪问题，也消除了双源 task 数据的混乱。18802 adapter 的 `tasks.jsonl` 模式不沿用。

plugin 侧 SendMessage 的状态流转简化为无状态同步：

```
收到 SendMessage → 调 gateway.request("agent") → 成功: 返回 A2A Task(COMPLETED, parts[].text=回复)
                                         └→ 失败/超时: 返回 A2A Task(FAILED, message=错误)
```

Task 对象仅在本次 HTTP 响应里构造，不持久化。task_id 由 plugin 生成（uuid），回传给 CORE，CORE 存自己的 SQLite。

---

## ⚙️ plugin 配置（`openclaw.plugin.json` + `configSchema`）

```jsonc
{
  "id": "agentwire-a2a",
  "name": "AgentWire A2A Adapter",
  "description": "Exposes Google A2A v1.0 JSON-RPC endpoint for OpenClaw agents",
  "activation": { "onStartup": true },
  "contracts": { "tools": ["a2a_send"] },   // v2.3.1 反向工具预留
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {
      "authToken": {
        "type": "string",
        "description": "Bearer token required on /a2a/jsonrpc. Must match CORE peers.openclaw token.",
        "default": ""
      },
      "agents": {
        "type": "array",
        "description": "OpenClaw agent IDs exposed via A2A agent card. First = default.",
        "items": { "type": "string" },
        "default": ["main", "vidhound", "vidforge"]
      },
      "defaultAgent": { "type": "string", "default": "main" },
      "taskTimeoutSeconds": { "type": "integer", "default": 120 }
    }
  },
  "uiHints": {
    "authToken": { "label": "A2A Bearer Token", "sensitive": true },
    "agents": { "label": "Exposed Agent IDs" },
    "defaultAgent": { "label": "Default Agent" }
  }
}
```

**Token 策略**：`authToken` 默认空 = loopback 免认证（OpenClaw 18789 本就 loopback 绑定）。暴露 Tailscale 时必须设 `authToken`，与 CORE `peers.openclaw` 的 token 一致。Token 不写进仓（配置时填，走 OpenClaw config）。

---

## 🔗 CORE 侧改动（v2.3.0）

### Token 传递澄清（回应评审问题一，已验证源码）

`_dispatch_via_a2a`（`gateway_executor.py:280-326`）对**所有 peer 无条件**加 `Authorization: Bearer {peer_token}`（第 318 行），其中：
```python
peer_token = peer_info.get("resolved_token", self._openclaw_token)  # 第 293 行
```
- `peers.openclaw` 当前**未配** `token_file` → `resolved_token` 缺失 → fallback 到 `OPENCLAW_TOKEN` env → 空字符串 → 发出 `Authorization: Bearer `（空 token 头）。

**这就是评审担心的未定义行为源头**：plugin 若配了 `authToken` 会因「收到的 Bearer 值 ≠ 配置值」拒收（401）；plugin 若 `authToken` 为空（loopback 免认证）则收到带空 Bearer 头的请求，行为取决于 plugin 校验逻辑。

**v2.3 方案（明确化，消除未定义）**：

1. **plugin 侧**（`src/routes.ts` auth 校验）：
   - `authToken` 为空 → **不校验** Authorization 头（loopback 免认证），即使请求带空 Bearer 头也放行。
   - `authToken` 非空 → 严格校验 `Bearer {token}` 值匹配，不匹配 401。
2. **CORE 侧**（`docker/core-config.yaml`）：
   - loopback 部署（plugin `authToken` 空）→ `peers.openclaw` **不配** `token_file`，并修改 `_dispatch_via_a2a`：`peer_token` 为空时**不发** Authorization 头（而非发空 Bearer）。这是个小修，让行为干净。
   - Tailscale 暴露部署（plugin `authToken` 非空）→ `peers.openclaw` 配 `token_file` 指向与 plugin 相同的 token 文件。

**M3 前必须落地的改动**（小）：`_dispatch_via_a2a` 第 315-320 行，token 为空时跳过 Authorization 头：
```python
headers = {"Content-Type": "application/json", "A2A-Version": "1.0"}
if peer_token:
    headers["Authorization"] = f"Bearer {peer_token}"
```
这同时修了**所有 peer** 的空 token 行为（不只 openclaw），是个净改进。

### 改动清单

1. **`docker/core-config.yaml`** `peers.openclaw`：
   ```yaml
   openclaw:
     url: "http://127.0.0.1:18789/a2a/jsonrpc"   # ← 加 /a2a/jsonrpc 路径
     description: "OpenClaw A2A adapter plugin"
     # loopback 免认证：不配 token_file（配合下方 _dispatch_via_a2a 空token不发头）
   ```
2. **`gateway_executor.py`** `_dispatch_via_openclaw()`：**删除**，统一走 `_dispatch_via_a2a()`（OpenClaw 变成标准 A2A peer）。消除「OpenClaw 特殊路径」——所有 peer 一视同仁走 A2A HTTP。符合规则 2。
3. **`gateway_executor.py`** `_dispatch_via_a2a()`：空 token 不发 Authorization 头（上述小修）。
4. **`agent_router.py`** 路由规则里 `peer: "openclaw"` 语义不变（仍是 OpenClaw agents），底层从 OpenClaw RPC 变 A2A。

---

## 🧹 清理（v2.3.0 落地后）

| 清理项 | 动作 |
|--------|------|
| `~/.openclaw/a2a-gateway/` sidecar（PID 476004） | 停止 + 从开机自启移除 + 归档 server.py 到 `designs/v2.3/legacy-sidecar/` 留档 |
| silk-bridge.py | 确认 v2.3 入站闭环可用后下线 |
| CORE `plugin/` 旧 v1.5.5 反向代理骨架 | 重写覆盖（不保留） |
| CORE `_dispatch_via_openclaw()` | 删除 |

---

## ✅ 验收标准

1. **入站闭环**：`curl POST http://127.0.0.1:18789/a2a/jsonrpc -d '{"method":"SendMessage","params":{"message":{...,"parts":[{"text":"ping"}]}}}'` → 返回 A2A Task COMPLETED，`parts[].text` = agent-main真实回复（非 404/非 passthrough）。
2. **CORE→plugin 路由**：外部 Agent 经 CORE 18880 SendMessage，CORE 日志 `routed to agent=main peer=openclaw`，plugin 调 `gateway.request("agent")` 成功，外部 Agent 收到真实回复。
3. **agent 选择**：`metadata.agentId=vidhound` → 回复来自agent-hound；缺省 → main（agent-main）。
4. **agent card**：`GET http://127.0.0.1:18789/.well-known/agent.json` 返回含 `agents:[main,vidhound,vidforge]` 的标准 card。
5. **无 sidecar**：`ps aux | grep a2a-gateway` 无结果；`ss -tlnp | grep 18802` 无监听。
6. **CORE 测试**：`pytest tests/test_v2_core.py` 全绿（`_dispatch_via_openclaw` 删除后相关测试改走 `_dispatch_via_a2a`）。
7. **plugin 单测**：`plugin/` 有 vitest/jest 单测覆盖 A2A 方法解析、agent 解析、task 状态机（mock `gateway.request`）。
8. **OpenClaw 升级抗性**：plugin 只依赖 `definePluginEntry`/`registerHttpRoute`/`gateway.request("agent")` 三个公开 API，无私有端点。
9. **plugin 崩溃隔离（回应评审问题五）**：模拟 plugin handler 异常（向 `/a2a/jsonrpc` 注入会触发未捕获异常的 payload，如让 `gateway.request` 抛错且 handler 未 try/catch），验证：
   - OpenClaw gateway 进程**不跟随崩溃**（`ps -p 236` 仍在，`curl /health` 仍 200）。
   - plugin 路由在异常后**自动恢复可达**（OpenClaw 的 route handler 容错）或明确返回 5xx。
   - CORE 侧 `_dispatch_via_a2a` 收到非 200 时日志记录明确错误（`log.warning("plugin dispatch HTTP %d: %s", status, body)`），**不静默超时**——这比 sidecar 死亡更易发现（CORE 有 metrics `a2a_dispatch_total{status="error"}` 可告警）。
   - 实现要求：plugin handler 必须 try/catch 包裹 `gateway.request`，异常时返回 A2A Task(FAILED) + 500 状态，绝不向 OpenClaw 路由层抛未捕获异常。

---

## ⚠️ 风险与未决

1. **`gateway.request("agent")` 在 plugin 进程内是否可用**：SDK 类型说 `api.runtime.gateway.request` 存在，但「plugin 运行时是否真有 gateway 上下文」需实测验证。CLI 是独立进程走 WebSocket，plugin 是进程内——可能 `api.runtime.gateway.isAvailable()` 在某些时机返回 false。**缓解**：v2.3.0 第一个里程碑就是写一个 10 行 plugin 验证 `gateway.request("agent", {message:"ping", agentId:"main"})` 能返回回复。若不行，fallback 到 `subagent.run`（已知可用但需二次查回复）。
2. **回复文本提取**：`result.payloads[].text` 是 CLI 用的字段，但 gateway RPC 返回结构可能与 CLI 包装后不同。需实测确认 `api.runtime.gateway.request` 原始返回的字段名。**缓解**：里程碑 1 实测时 `console.log(JSON.stringify(result))` 打全量。
3. **agent 列表来源**：configSchema 硬编码 `agents:[main,vidhound,vidforge]`，非动态。若 OpenClaw 新增 agent 需改配置。**缓解**：v2.3.1 探索 `api.runtime.gateway.request("agents.list", ...)` 是否存在（未确认有此 method）。
4. **Token 暴露面**：plugin 挂在 18789（OpenClaw gateway 端口），与 OpenClaw 自有 HTTP 路由同端口。需确认 `registerHttpRoute` 注册的 `/a2a/jsonrpc` 不会与 OpenClaw 内置路由冲突，且 OpenClaw 的 gateway auth 不会先拦截。**缓解**：里程碑 1 验证 `auth:"plugin"` 下路由是否真对外可达。
5. **跨语言维护**：plugin 是 TS，AgentWire 历来 Python。需建 TS 构建流程（tsc + 提交 dist/）。**缓解**：plugin 极简（<300 行），构建一次成型，迭代少。
6. **plugin 崩溃比 sidecar 死亡更隐蔽（评审问题五）**：sidecar 死亡有 PID 可查（agents 报 476004 不存在）；plugin 跑在 OpenClaw 进程内，handler 异常若未被 OpenClaw 路由层捕获，路由可能静默失效而 OpenClaw 主进程仍活——比 sidecar 死亡更难发现。**缓解**：(a) plugin handler 严格 try/catch，异常转 A2A FAILED + 500，绝不外抛；(b) CORE 侧 `_dispatch_via_a2a` 非 200 记 warning 日志 + `a2a_dispatch_total{status="error"}` counter 自增（v2.2.0 已有 metrics），可配告警；(c) 验收标准 9 强制验证崩溃隔离。

---

## 🗺️ 里程碑（落地顺序）

### M0 — 止血（**跳过**，用户决定 2026-07-18）

用户确认：Agent 通讯链路有邮件回退，当前可正常通联。**不重启 18802 sidecar，跳过现有 A2A 修复**，直接进 M1 开发。开发期间 A2A 链路保持断开状态（agents 走邮件），plugin 上线（M3）即恢复 A2A。M4 清理时 sidecar 本已死亡，只需归档确认。

> 这反而更干净：无需维护临终 sidecar，不引入「sidecar 与 plugin 并行」的混淆期。代价是 M1-M3 期间 A2A 不通——可接受（邮件回退在用）。

### M1-M5 — v2.3 开发（与 M0 并行）

| # | 里程碑 | 验证物 | 阻断下一阶段？ |
|---|--------|--------|---------------|
| M1 | **可行性 spike**：10 行 plugin 验证 `gateway.request("agent")` 进程内可用 + 回复字段名 | `curl 18789/a2a/jsonrpc` 拿到agent-main回复，`console.log` 打全量 result 确认字段 | **是**（若失败转 subagent.run fallback） |
| M2 | plugin 主体：SendMessage + agent card + auth 校验 | M1 验收 + agent 选择 + auth 空/非空两种行为 | 否 |
| M3 | CORE 改动：peers.openclaw 加路径 + 删 `_dispatch_via_openclaw` + 空token不发头 | CORE 全链路经 plugin 通，外部 Agent 收到真实回复 | 否 |
| M4 | 清理：下线 18802 sidecar + silk-bridge + 旧 v1.5.5 骨架 | 验收标准 5/6/7/9 | 否 |
| M5 | 测试 + 文档 + release v2.3.0 | 验收标准全绿，tag/release | — |

**M1 是生死门**。若 `gateway.request("agent")` 进程内不可用，整个方案转 fallback（subagent.run + 二次查回复，或 WebSocket RPC client）。M1 验证后再投入 M2+。

---

## 📦 release 策略

- 单仓单 release：`agentwire-core` v2.3.0（含 server_v2 + plugin/dist）
- 不新开仓（已确认用户意图）
- plugin 不单独发 npm（私有部署，本地 `--link` 安装）
- CHANGELOG 补 v2.3.0 条目

### 部署指令（回应评审问题四）

AI-Claw 本机部署，plugin 目录在 core 仓内：

```bash
# 1. 拉取最新 core 仓（含 plugin/ 重写 + dist/ 编译产物）
cd /mnt/d/项目/A2A/agentwire_core && git pull

# 2. 链接安装（开发/本机部署用 --link，符号链接热重载）
openclaw plugins install --link /mnt/d/项目/A2A/agentwire_core/plugin

# 3. 验证加载
openclaw plugins list | grep agentwire-a2a
openclaw plugins inspect agentwire-a2a

# 4. 重启 OpenClaw gateway 使 activation.onStartup 生效
#    （或等 OpenClaw 热加载，若支持）
# 5. 验证路由
curl http://127.0.0.1:18789/.well-known/agent.json
curl -X POST http://127.0.0.1:18789/a2a/jsonrpc -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"SendMessage","params":{"message":{"messageId":"t1","role":"user","parts":[{"text":"ping"}]},"metadata":{"agentId":"main"}},"id":"t1"}'
```

> ⚠️ `--link` 要求路径在 OpenClaw 运行期间稳定（`/mnt/d/项目/A2A/` 是 WSL2 挂载，稳定）。若 plugin 迭代频繁，`--link` 免每次重新 install；改 `dist/` 后需 OpenClaw 重载 plugin。
>
> 远端 Pawly（<pawly-host>）不装此 plugin——plugin 只在 OpenClaw 所在本机（AI-Claw）。Pawly 经 Tailscale 打 CORE 18880，CORE 再路由到本机 plugin。

---

## 🚫 不做（v2.3.0 范围外）

- 反向闭环（agent 主动发 A2A）→ v2.3.1
- SendStreamingMessage / SSE → v2.3.2+
- 动态 agent 发现 → v2.3.1
- OpenClaw 升级自动化测试 → v2.4
- 重写 CUE → 不做（CUE v2.2.0 稳定，无关）

---

## 📝 评审修订记录

### R1（2026-07-18）—— 5 项反馈落实

| # | 反馈 | 落实位置 | 验证依据 |
|---|------|---------|---------|
| 1 | `_dispatch_via_a2a` 对 openclaw token 传递未定义 | 「Token 传递澄清」章节 + 改动 3 | 源码 `gateway_executor.py:293,318` 已验证：无条件发 Bearer，空 token 发空头 |
| 2 | plugin task store 与 CORE SQLite 关系不清 | 「Task 状态机 + 查询路径澄清」+ 方法表 GetTask/ListTasks 改不实现 | 源码 `default_request_handler.py:142-172` 已验证：GetTask 本地查 SQLite 不转发 → plugin 无需 task store |
| 3 | M0 时机不明 | 里程碑「M0 紧急止血」独立章节，明确立即执行、与 M1-M5 并行 | — |
| 4 | plugin 安装路径未写 | 「部署指令」章节，明确 `/mnt/d/项目/A2A/agentwire_core/plugin` + `--link` | — |
| 5 | 缺 plugin 崩溃恢复验收 | 验收标准第 9 条 + 风险第 6 条 | — |

**关键结论**：plugin **不维护 task store**（问题二证明 GetTask 走 CORE SQLite，plugin task store 是伪需求，删除）。CORE `_dispatch_via_a2a` **空 token 不发 Authorization 头**（问题一净改进，适用所有 peer）。
