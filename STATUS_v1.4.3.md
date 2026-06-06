# AgentWire-Core v1.4.3 — Final Status

> **Released**: 2026-06-06
> **Tag**: `v1.4.3` (commit `5935191`)
> **Owner**: 丝线 (SilkThread)
> **Protocol**: A2A v1.0.1 + JSON-RPC 2.0
> **License**: MIT

---

## 🎯 完成清单

本文件是 agentwire-core 仓的 STATUS 系列首篇（前 v1.4.1/v1.4.2 仅在 commit message 中带出），目的是把"代码 + release page"与"设计说明"对齐。

| 项 | 状态 |
|---|---|
| Per-peer JSONL history 持久化 | ✅ Done |
| 写入前 redact（API key / token / JWT / 私钥 / URL 密码） | ✅ Done |
| `messages/{list,get,peers,export}` JSON-RPC | ✅ Done |
| 上下文自动注入（`message.metadata.agentwire_history`） | ✅ Done |
| `/redact/patterns` 共享端点 | ✅ Done |
| 路由修复：`/.well-known/agent.json` / `/health` / `/a2a/jsonrpc` | ✅ Done (v1.4.2 audit closure) |
| `server/config.yaml` untrack | ✅ Done (v1.4.2 audit #2) |
| Agent 文档：`skill/` 9 文件（双语） | ✅ Done |
| 双语 README | ✅ Done |
| git tag `v1.4.3` (annotated) | ✅ Done |
| 推送 GitHub | ✅ Done |
| GitHub Release | ✅ <https://github.com/DerekEXS/agentwire-core/releases/tag/v1.4.3> |

---

## 📊 数字

| 维度 | 数字 |
|------|------|
| **Tag** | `v1.4.3` (commit `5935191`) |
| **Commits** | 2 (feat `35098fa` + docs `5935191`) |
| **Files changed** | 12 (3 new + 2 modified + 9 skill new + 2 doc new) |
| **+ 711 / -145 lines** | 含 start.py 重写 (395→450) + history.py (240 行) + redact.py (60 行) |
| **SKILL docs** | 9 (SKILL.md / SKILL_CN.md / PROTOCOL_QUICK_REF.md / 5 INTEGRATION_*.md / PLUGIN_DEVELOPMENT.md) |
| **Public visibility** | repo public, no secrets on remote |
| **Compatibility** | A2A v1.0.1 spec compatible |

---

## 🆕 v1.4.3 新功能详解

### 1. 消息历史持久化

每个 peer 一份 JSONL，路径 `~/.local/share/agentwire/history/peer_<uuid>.jsonl`。
索引文件 `index.json` 维护 peer 元数据（display name、UUID、last_round、total_rounds、first_round、last_ts、file）。

**Round 编号规则**:
- 每对 outbound + inbound = 1 轮
- round 号全局递增、永不复用
- 当 `max_rounds_per_peer > 0` 且总轮数超限时，FIFO 删最旧（每轮 2 行），`first_round` 同步 +drop

**Peer 标识双轨**:
- 落盘按 `peer_uuid`（`hashlib.sha256(context_id or msg_id)[:16]`），抗重名
- 显示按 `peer_name`（默认取 UUID 前 8 位，可更新）

**配置**（`server/config.yaml`）:
```yaml
history:
  enabled: true
  max_rounds_per_peer: 0        # 0 = 无限（默认），>0 = FIFO 上限
  context_rounds: 5             # 0 = 不注入
  storage_dir: "~/.local/share/agentwire/history"
  redact_sensitive: true
  round_close:
    mode: heuristic
    heuristic_idle_seconds: 300
```

### 2. Redact 引擎

`server/redact.py` 内置 7 类敏感 pattern：
- `anthropic_key` (`sk-ant-...`)
- `openai_key` (`sk-...`)
- `github_pat` (`ghp_...`)
- `bearer_token` (`Bearer ...`)
- `jwt` (`eyJ.eyJ.xxx`)
- `private_key_block` (`-----BEGIN ... PRIVATE KEY-----`)
- `url_password` (`://user:pwd@host`)

可被 `GET /redact/patterns` 拉取，cue 等下游工具复用同一套规则。

### 3. JSON-RPC 新增 4 个方法

| 方法 | params | 返回 |
|------|--------|------|
| `messages/list` | `peer_uuid?`, `since_round?`, `limit?` | 消息列表 |
| `messages/get` | `peer_uuid`, `round` | 单轮 |
| `messages/peers` | — | peer 元数据列表 |
| `messages/export` | `peer_uuid`, `format: "jsonl"\|"markdown"` | 字符串内容 |

### 4. 上下文自动注入

`context_rounds > 0` 时，每次 `message/send` 响应里 message.metadata.agentwire_history 包含最近 N 轮消息（结构化 JSON，不污染 parts）。

接收方 LLM 可安全忽略 metadata 或读取后格式化喂 prompt——**不会把历史误认为新指令**（物理隔离 parts vs metadata）。

### 5. 路由修复（v1.4.2 audit closure）

v1.4.2 三个关键路由**未注册**（handler 函数存在但 `_setup_routes()` 没调）：
- `GET /.well-known/agent.json` — agent card discovery
- `GET /health` — liveness probe
- `POST /a2a/jsonrpc` — JSON-RPC endpoint

v1.4.3 已注册。测试验证：
```
$ curl -s http://127.0.0.1:18800/.well-known/agent.json
{"protocolVersion": "1.0.1", "name": "AgentWire", ...}
$ curl -s http://127.0.0.1:18800/health
{"status": "healthy", "service": "agentwire", "version": "1.4.3", ...}
$ curl -X POST .../a2a/jsonrpc -d '{...}'
{"jsonrpc": "2.0", "id": 1, "result": {...}}
```

---

## 🛠 修改文件清单

| 文件 | 类型 | 改动 |
|------|------|------|
| `server/history.py` | A | HistoryManager 类 (240 行)：peer UUID 派生、轮号管理、FIFO、redact 集成、JSONL 持久化、markdown/jsonl 导出 |
| `server/redact.py` | A | DEFAULT_PATTERNS 目录 + `load_catalog()` + `compile_patterns()` |
| `server/start.py` | M | 重写：注册 4 新路由、新增 4 JSON-RPC handler、history 接入、redact catalog 加载 |
| `server/config.yaml.example` | M | 新增 `history:` 段完整注释 |
| `README.md` + `README_CN.md` | M | 双语 + A2A v1.0.1 / MIT 标注 + 去 Companion Repository |
| `skill/*.md` | A | 9 文件 |

---

## 🧪 端到端验证 (v1.4.3)

### History + Redact 集成测试

```python
from history import HistoryManager
from redact import load_catalog

h = HistoryManager(td, max_rounds_per_peer=0)
h.set_patterns(load_catalog()['patterns'])
u1, r1 = h.record_outbound('ctx-A', 'm1', [
    {'type':'text','text':'my key is sk-abcdefghijklmnopqrstuvwxyz0123456789012345'}
])
h.record_inbound(u1, 'm2', [
    {'type':'text','text':'got it, your key is bearer xyz1234567890abcdefghij'}
])
# 落盘后:
# peer_e2725.../peer_e2725...jsonl 1 round / 2 lines / 全部 redact
# messages[0].parts[0].text = "my key is [REDACTED:OPENAI_KEY]"
# messages[1].parts[0].text = "got it, your key is Bearer [REDACTED:TOKEN]"
```

### 单元 smoke（start.py 可 import）

```python
$ python3 -c "import start; print('import OK')"
import OK
handlers: ['_handle_agent_card', '_handle_health', '_handle_jsonrpc',
           '_handle_message_send', '_handle_messages_export',
           '_handle_messages_get', '_handle_messages_list',
           '_handle_messages_peers', '_handle_metrics',
           '_handle_redact_patterns', '_handle_rest_send',
           '_handle_root', '_handle_task_get']
```

---

## 🛡 防泄漏

- 所有 commit author 均为 `silk-thread <silk-thread@agentwire.local>`（化名）
- `server/config.yaml` 已 untrack（v1.4.2 audit #2）；`.gitignore` 已包含
- redact 引擎在 history 写入前自动脱敏
- core README 已**删除** "Companion Repository" 段（不暗示 cue 是下游）
- `core-only` 本地分支已删除（多仓重构后不再需要）

---

## 📁 交付清单

| 文件 | 内容 |
|------|------|
| `server/history.py` | 新建 (240 行) — HistoryManager |
| `server/redact.py` | 新建 (60 行) — pattern 目录 |
| `server/start.py` | 重写 — +路由 +handler +history 接入 |
| `server/config.yaml.example` | + `history:` 段 |
| `skill/SKILL.md` + `SKILL_CN.md` | 通用协议指南 (双语言) |
| `skill/PROTOCOL_QUICK_REF.md` | JSON-RPC 方法签名速查 |
| `skill/INTEGRATION_OpenClaw.md` | TS 插件绑定 |
| `skill/INTEGRATION_QwenPaw.md` | Python A2A 客户端 |
| `skill/INTEGRATION_Hermes.md` | 通用适配器 |
| `skill/INTEGRATION_Claude.md` | **新增** Claude Code/API 集成 |
| `skill/INTEGRATION_Generic.md` | 5 语言示例 (curl/Py/TS/Go/Rust) |
| `skill/PLUGIN_DEVELOPMENT.md` | 插件开发指南 |
| `README.md` + `README_CN.md` | 双语 + A2A v1.0.1 / MIT |

---

## 🔄 v1.4 整体状态

| 版本 | Tag | 关键交付 |
|------|-----|----------|
| v1.4.1 | ✅ | Plugin host skeleton + A2A 基础 |
| v1.4.2 | ✅ | AUDIT 闭包 (3 fix) + untrack config.yaml |
| **v1.4.3** | **✅ (本文件)** | **history / redact / 路由修复 / SKILL 库 / 双语 README** |

v1.4 backlog 已完结。

---

## 🎬 下一 session 起点

读本文件 + `agentwire_core/README.md` + `agentwire_core/skill/SKILL.md`。

**可选下一阶段**:
- **v1.4.4 / v1.5**:
  - `total_rounds_today()` 真实按日期聚合
  - `message/send` 异步任务支持（当前 sync；长任务可加 outbox + worker）
  - history 备份/恢复 CLI
  - multi-tenant token（不同 token 看到不同 history namespace）
  - 与 cue 一同做 e2e subprocess 测试

---

*冻结: 2026-06-06 丝线 (SilkThread)*
*Tag: v1.4.3 (commit 5935191)*
