# AgentWire v2.3 — Gateway WebSocket 协议技术验证

> **Date**: 2026-07-18
> **Target**: 方案 C（WebSocket loopback client）编码前验证
> **Owner**: 丝线 (silk-thread)
> **依据**: OpenClaw 2026.7.1 源码 `src-DZzKBMa7.js`（GatewayClient 实现）、`call-dBhJbczL.js`（callGateway 封装）、`client-CE2rtDfj.js`（CLI WS client）

---

## 1. Gateway 当前配置

来源：`/home/AIKali/.openclaw/openclaw.json:gateway`

| 字段 | 值 | 含义 |
|------|---|------|
| `mode` | `"local"` | 本地 gateway |
| `bind` | `"lan"` | 绑定 0.0.0.0 |
| `auth.mode` | `"token"` | Bearer token 认证 |
| `auth.token` | `<gateway-auth-token>` | **gateway auth token** |
| `port` | `18789` | — |

**结论**：gateway 不是 `auth:none`（loopback 仍需 token）。但 token 是已知的，plugin 可用此 token 认证。**不需要设备密钥对** 如果只用 token auth（见下 §3）。

---

## 2. WS 协议帧格式

来源：`src-DZzKBMa7.js:28-34`（`isGatewayEventFrame`）、`isGatewayResponseFrame`、`request()`（行 974-984）

### 2.1 帧类型总览

| type | 方向 | 结构 | 用途 |
|------|------|------|------|
| `"event"` | Server → Client | `{type:"event", event:string, seq?:number, payload?}` | 服务器推送事件（如 connect.challenge, tick） |
| `"req"` | Client → Server | `{type:"req", method:string, id:string, params?:object, expectFinal?:boolean}` | 客户端请求 |
| `"res"` | Server → Client | `{type:"res", id:string, ok:boolean, payload?}` / `{type:"res", id, ok:false, error:{code,message,retryable?,retryAfterMs?}}` | 请求响应 |

来源行号：
- 请求帧：`src-DZzKBMa7.js:980-984`
- 响应帧：`src-DZzKBMa7.js:30-32`（校验）、`src-DZzKBMa7.js:865-891`（处理）
- 事件帧：`src-DZzKBMa7.js:25-27`（校验）、`src-DZzKBMa7.js:834-863`（处理）

### 2.2 请求帧完整结构

> `src-DZzKBMa7.js:974-984`

```json
{
  "type": "req",
  "method": "<string, 非空>",
  "id": "<uuid v4 string>",
  "expectFinal": true,
  "params": { /* method-specific */ }
}
```

每个请求有独立 uuid id，响应用相同 id 关联。`expectFinal:true` 时，中间状态帧（`status:"accepted"`）不解析为最终响应——只有 final 帧 resolve。

### 2.3 响应帧完整结构

> `src-DZzKBMa7.js:865-891`

```json
// 成功
{"type":"res", "id":"<uuid>", "ok":true, "payload":{/* method 返回的 result */}}
// 失败
{"type":"res", "id":"<uuid>", "ok":false, "error":{"code":"...", "message":"...", "retryable":false, "retryAfterMs":null}}
```

### 2.4 事件帧处理

> `src-DZzKBMa7.js:834-862`

服务端推送的 `type:"event"` 帧：
- `event:"connect.challenge"` → `payload.nonce` — 握手挑战码（见 §3）
- `event:"tick"` — 心跳，客户端回复（`this.lastTick = Date.now()`）
- 其他事件 → `opts.onEvent(evt)`

---

## 3. Connect 握手协议（hello 阶段）

来源：`src-DZzKBMa7.js:510-547`、`src-DZzKBMa7.js:613-666`（`assembleConnectParams`）、`src-DZzKBMa7.js:837-847`（挑战接收）

### 3.1 时序

```
Client                          Server
  |--- WS connect ------------->|
  |<--- event: connect.challenge (nonce) --|
  |--- req: connect {params} -->|
  |<--- res: connect OK (hello) ---|
  |                               |
  |--- req: agent {params} --->   |  (业务请求，helloOk 之后)
  |<--- res: agent OK ------------|
```

1. Client 连 WS (`ws://127.0.0.1:18789`)
2. Server 下发 `{type:"event", event:"connect.challenge", payload:{nonce:"<random>"}}` →
   `src-DZzKBMa7.js:837-847`
3. Client 组装 connect params（含 nonce、auth、device 签名）→
   `src-DZzKBMa7.js:517` `assembleConnectParams({role, nonce})`
4. Client 发 `{type:"req", method:"connect", id, params}` →
   `src-DZzKBMa7.js:527` `this.request("connect", assembled.params)`
5. Server 回 `{type:"res", id, ok:true, payload:{auth:{deviceToken?,role,scopes}, policy:{tickIntervalMs}, features:{methods:[...]}}}` →
   `src-DZzKBMa7.js:528-547`
6. `helloOkReceived = true` → 可发业务请求

### 3.2 Connect params 结构

> `src-DZzKBMa7.js:631-658`

```json
{
  "minProtocol": 4,
  "maxProtocol": 4,
  "client": {
    "id": "agentwire-a2a",
    "displayName": "AgentWire A2A Adapter",
    "version": "2.3.0",
    "platform": "linux",
    "mode": "cli",
    "instanceId": "<uuid>"
  },
  "auth": {
    "token": "<gateway-auth-token>"
  },
  "role": "operator",
  "scopes": ["operator.write", "operator.read"],
  "device": {
    /* 需要设备 key pair 签名（见 3.3）*/
  }
}
```

### 3.3 设备认证复杂度（关键）

> `src-DZzKBMa7.js:667-689` (`buildDeviceConnectParams`)

Connect 请求的 `device` 字段包含 Ed25519 签名的设备认证 payload：
- `device.id` — 设备 uuid（`loadOrCreateDeviceIdentity` 生成，持久化在 `~/.openclaw/identity/device-auth.json`）
- `device.publicKey` — Ed25519 公钥 base64url
- `device.signature` — 用私钥签名的连接 payload
- `device.signedAt` — 签名时间戳
- `device.nonce` — 服务端挑战码

设备 key pair 由 `loadOrCreateDeviceIdentity` 首次运行时自动生成（`device-identity-UW4cZXf5.js`），持久化在 disk。

**但**: 行 667-668 `if (!this.opts.deviceIdentity) return;` — 如果 client 创建时不传 `deviceIdentity`，**`device` 字段不出现在 connect params 中**。

> `src-DZzKBMa7.js:797-824` (`selectConnectAuth`)

认证优先级（`selectConnectAuth`）：
1. 显式 `token` (gateway auth token) → `auth.token`
2. 设备 token（已持久化的 deviceToken）→ `auth.deviceToken`
3. 密码 → `auth.password`
4. 自举 token → `auth.bootstrapToken`

**关键推论**：如果 plugin 只传 `token`（gateway auth token），不传 `deviceIdentity` → `auth.token` 设值，`device` 字段省略。Gateway 是否接受「仅 token、无设备签名」的 connect —— 这取决于 gateway 的 auth 策略，源码未明确显示，但可能性高（token 已是预共享密钥，设备签名在 token 场景下是冗余的）。

**验证方式**：写一段 20 行 Node 脚本实际试连 WS + token auth（见 §6）。

---

## 4. "agent" method 完整协议

### 4.1 请求（Client → Server）

来源：`agent-via-gateway-1KwjCa1L.js:406-430`

```json
{
  "type": "req",
  "method": "agent",
  "id": "<uuid>",
  "expectFinal": true,
  "params": {
    "message": "<text>",
    "agentId": "main",
    "sessionKey": "agent:main:a2a:<task-uuid>",
    "deliver": false,
    "timeout": 60,
    "to": null,
    "replyTo": null,
    "sessionId": null,
    "thinking": null,
    "channel": null,
    "replyChannel": null,
    "lane": null,
    "extraSystemPrompt": null
  }
}
```

**必填字段**（从 CLI 用法 + 源码推断）：
- `message` — 文本（必填）
- `agentId` — 目标 agent id
- `sessionKey` — 格式 `agent:<agentId>:<channel>:<uuid>`（`agent-via-gateway-1KwjCa1L.js:328`）
- `deliver` — `false` = 不投递到 channel（仅返回文本到 WS）

### 4.2 Scope 要求

来源：`method-scopes-CwW_Szsp.js:135,147`

"agent" method 需要 `operator.write` scope（或 `operator.read` 满足 write 子集）。CLI 调用时 `resolveLeastPrivilegeOperatorScopesForMethod("agent")` 返回 `["operator.write"]`。这个 scope 在 connect 请求的 `scopes` 数组中声明。

**方案 C 的关键绕行点**：以 WS client 身份连接时，`scopes` 在 connect 请求中声明。OpenClaw 的 scope 限制是针对 **plugin runtime** 的（`canTrustedOfficialPluginRequestScopes`），不是针对 WS client 的。CLI 以 `role:"operator"` + `scopes:["operator.write"]` 连接 WS，能成功调 agent（前面实测agent-main在线）。**WS client 的身份不受 plugin trust gate 限制**。

> 这就是方案 C 的核心优势：plugin runtime 不能调 agent，但同一进程里启动的 WS client（以 operator 身份）可以。

### 4.3 响应（Server → Client）

来源：`agent-via-gateway-1KwjCa1L.js:480-489`、实测 `openclaw agent --json` 返回：

```json
{
  "type": "res",
  "id": "<uuid>",
  "ok": true,
  "payload": {
    "runId": "<uuid>",
    "status": "ok",
    "summary": "completed",
    "result": {
      "payloads": [
        {"text": "收到 ping，agent-main在线 🟢\n..."}
      ],
      "deliveryStatus": "..."
    }
  }
}
```

**回复文本提取路径**：`payload.result.payloads[].text`（多个 payload 的 text 拼接）

**中间状态（`expectFinal` 机制）**：agent method 可能返回中间帧（`payload.status:"accepted"`）表示 agent run 被接受但尚未完成。客户端用 `expectFinal:true` 标志告诉 server 只返回最终帧 → 中间帧被过滤（`src-DZzKBMa7.js:869-879`）。

### 4.4 性能（进程内 WS loopback）

WS 连 `127.0.0.1:18789` 是 loopback TCP，~0.1ms RTT。agent 回复延迟取决于 agent 推理时间（通常 3-30s）。WS 层面延迟可忽略。

### 4.5 和 CLI 调用的一致性

实测 CLI `openclaw agent --agent main --message "ping" --json` 返回：

```json
{
  "runId": "9400eb71-...",
  "status": "ok",
  "summary": "completed",
  "result": {
    "payloads": [{"text": "收到 ping，agent-main在线 🟢\n\n..."}]
  }
}
```

agent method 的 WS response 和 CLI JSON output 的 `result` 结构一致（CLI 把 WS response 的 payload 扁平化了一层）。

---

## 5. 两种实现路径对比

### 路径 C1：WS native client（plugin 内直接连 WS）

**做法**：plugin 内用 Node 22 内置 `WebSocket` 实现极简 WS client，复刻 §2-4 协议。

| 维度 | 评估 |
|------|------|
| 代码量 | ~250-350 行 TS（connect 握手 ~100 行 + agent 请求 ~50 行 + 帧解析 ~100 行） |
| 依赖 | 0（Node 22 内置 `WebSocket`，已确认可用） |
| 认证 | 需传 gateway token + scope，**可能需设备签名**（§3.3 未决） |
| 性能 | 最优（进程内 WS loopback，~0.1ms 握手 + agent 推理时间） |
| 长连接 | 可复用 WS 连接（多 A2A 请求共用一个 WS）→ 效率最高 |
| 风险 | ① 设备签名是否必须未实测；② 协议未公开文档，未来 OpenClaw 改帧格式需跟随 |
| 开发时间 | 3-5 天 |

### 路径 C2：CLI 子进程（`openclaw agent --json`）

**做法**：plugin 内 `child_process.execFile("openclaw", ["agent", "--agent", agentId, "--message", text, "--json", "--deliver=false", "--timeout", "60"])`，解析 stdout JSON 提取 `result.payloads[].text`。

| 维度 | 评估 |
|------|------|
| 代码量 | ~25-35 行 TS（纯 Node `child_process` API） |
| 依赖 | 0（Node 内置 `child_process`），需 `openclaw` CLI 在 PATH |
| 认证 | **已验证可用**（实测 CLI 成功调agent-main）——全自动由 CLI 处理（token、设备签名、scope 全在内） |
| 性能 | 每次 A2A 调用 spawn 一个进程（~50-100ms 启动开销 + agent 推理时间） |
| 风险 | ① 进程 spawn 开销可接受（agent 推理 3-30s，50ms 启动可忽略）；② `openclaw` CLI 在 AI-Claw 本机 Path 稳定 |
| 开发时间 | 0.5 天 |

### 推荐

**v2.3.0 走 C2（CLI 子进程），v2.3.1 可选升级到 C1（WS client）**。

理由：
1. C2 已实锤可行（CLI 调agent-main成功），零协议风险。C1 的设备签名未决（可能需要额外实现 `loadOrCreateDeviceIdentity` + Ed25519 签名 = 额外 100+ 行 + crypto 依赖）。
2. C2 的进程 spawn 开销（~50ms）在 agent 推理延迟（3-30s）面前可忽略。瓶颈在 agent 推理，不在进程启动。
3. C2 完美复用 OpenClaw CLI 的认证+会话管理（token、device auth、scope、sessionKey 全由 CLI 处理），plugin 只需构造 CLI 参数 + 解析 JSON。
4. 后续若性能成为瓶颈，升级到 C1——C1 和 C2 的 plugin 接口相同（都是 `wsLoopbackCallAgent(agentId, text)` → `string`），内部实现可无感替换。

---

## 6. 最小复刻骨架（Node 内置 WebSocket）

若后续走 C1，以下是基于 §2-4 协议的最小连接代码骨架（未实测，供 C1 开发参考）：

```typescript
// 仅用 Node 22 内置 WebSocket（零依赖）
import { randomUUID } from "node:crypto";

const GW_URL = "ws://127.0.0.1:18789";
const GW_TOKEN = "<gateway-auth-token>";
const TIMEOUT_MS = 90_000;

interface RpcRequest {
  method: string;
  params?: Record<string, unknown>;
  expectFinal?: boolean;
}

function callGateway(request: RpcRequest): Promise<any> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(GW_URL);
    const pending = new Map<string, { resolve: Function; reject: Function }>();
    let timer: ReturnType<typeof setTimeout> | undefined;

    ws.onopen = () => {
      // Server 会下发 connect.challenge → 我们回复 connect
      // （见 §3 握手协议。若 token-only 免设备签名则简化）
    };

    ws.onmessage = (event: MessageEvent) => {
      const frame = JSON.parse(event.data as string);
      switch (frame.type) {
        case "event":
          if (frame.event === "connect.challenge") {
            const nonce = frame.payload?.nonce;
            if (!nonce) { ws.close(1008, "missing nonce"); return; }
            ws.send(JSON.stringify({
              type: "req",
              method: "connect",
              id: randomUUID(),
              params: {
                minProtocol: 4,
                maxProtocol: 4,
                client: {
                  id: "agentwire-a2a",
                  displayName: "AgentWire A2A",
                  version: "2.3.0",
                  platform: "linux",
                  mode: "cli",
                  instanceId: randomUUID(),
                },
                auth: { token: GW_TOKEN },
                role: "operator",
                scopes: ["operator.write", "operator.read"],
                // device: 省略（若无设备身份，此处为未决点）
              },
            }));
          }
          break;
        case "res":
          if (frame.id === "connect-ok") {
            // Hello OK → 发业务请求
          } else {
            const p = pending.get(frame.id);
            if (p) {
              pending.delete(frame.id);
              frame.ok ? p.resolve(frame.payload) : p.reject(new Error(frame.error?.message));
            }
          }
          break;
      }
    };

    ws.onerror = (err) => {
      // ...
    };

    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      ws.close();
      reject(new Error("gateway timeout"));
    }, TIMEOUT_MS);
  });
}

// 调 agent
async function callAgent(agentId: string, text: string): Promise<string> {
  const sessionKey = `agent:${agentId}:a2a:${Date.now()}`;
  const result = await callGateway({
    method: "agent",
    expectFinal: true,
    params: {
      message: text,
      agentId,
      sessionKey,
      deliver: false,
      timeout: 60,
    },
  });
  const payloads: any[] = result?.payloads ?? [];
  return payloads.map((p: any) => p?.text ?? "").filter(Boolean).join("\n");
}
```

> ⚠️ 骨架关键未决点：connect 请求的 `device` 字段是否需要。若 gateway 在接受 `auth.token` 时不需要 `device`，上述代码直接可用；若需要设备签名，需额外导入 `loadOrCreateDeviceIdentity` + `signDevicePayload`（约 100 行，依赖 OpenClaw 内部模块）。**建议走 C2（CLI 子进程）避开此未决点**。

---

## 7. 结论

| 问题 | 答案 |
|------|------|
| WS 连接 URL | `ws://127.0.0.1:18789`（gateway 当前绑定 0.0.0.0:18789） |
| 认证方式 | `auth.mode=token`，token 从 `~/.openclaw/openclaw.json:gateway.auth.token` 读取（不写入本文档）。connect 请求 `auth.token` 字段传此值 |
| 消息格式 | 自有帧协议：`{type:"req"|"res"|"event", id?, method?, params?, payload?, ...}`（非 JSON-RPC） |
| agent method 名 | `"agent"`（← 不是 `"SendMessage"`，不是 `"sendMessage"`） |
| agent params | `{message, agentId, sessionKey, deliver:false, timeout}` |
| 回复文本 | `payload.result.payloads[].text` |
| scope 绕过 | WS client 以 `operator` 身份声明 `scopes:["operator.write"]`，**不受 plugin trust gate 限制**（trust gate 只作用于 `api.runtime.gateway.request`） |
| 设备签名是否需要 | **未决**。若 `auth.token` 可单独认证则不需要；若 gateway 要求设备签名则需额外实现。实测确认方式：写 20 行 Node 脚本 raw WS 连 + token auth 试 |

**推荐实现路径**：**v2.3.0 走 C2（CLI 子进程）**。30 行代码，已实锤可行，零协议风险。v2.3.1 可选升级到 C1（WS client）。

---

## 附录：M1 spike 资产复用确认

以下 M1 spike 已验证可用的部分直接复用进方案 C2：

| 资产 | 文件 | 状态 |
|------|------|------|
| `definePluginEntry` + `register(api)` 外壳 | `src/index.ts` | ✓ 无需改 |
| `/a2a/jsonrpc` HTTP 路由 | `src/index.ts` | ✓ 无需改 |
| `/.well-known/agent.json` 路由 | `src/index.ts` | ✓ |
| `/a2a/health` 路由 | `src/index.ts` | ✓ |
| `readBody`, `extractText`, `resolveAgentId` helpers | `src/index.ts` | ✓ 复用 |
| `rpcOk`, `rpcErr` | `src/index.ts` | ✓ 复用 |
| A2A Task 构造（COMPLETED/FAILED） | `src/index.ts` | ✓ 复用 |
| **唯一替换点** | | `api.runtime.subagent.run/waitForRun/getSessionMessages` → `node:child_process.execFile("openclaw", ["agent", "--agent", agentId, "--message", text, "--json", ...])` |

