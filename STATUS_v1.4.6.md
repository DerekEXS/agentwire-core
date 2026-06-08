# AgentWire-Core v1.4.6 — Security Audit Closure

> **Released**: 2026-06-07
> **Tag**: `v1.4.6` (commit fixed at push time)
> **Owner**: 丝线 (SilkThread)
> **Series**: v1.4.x FROZEN — see [CHANGELOG.md](CHANGELOG.md) header
> **Protocol**: A2A v1.0.1 + JSON-RPC 2.0
> **License**: MIT
> **Companion**: [agentwire-cue v1.4.5](https://github.com/DerekEXS/agentwire-cue/releases/tag/v1.4.5) (no v1.4.6 changes — cue 仓 already shipped v1.4.5 收口)

---

## 🎯 v1.4.6 定位：安全审计修复 (Security Audit Closure)

v1.4.6 = 初次公开仓安全审计 (3 个低危 + 1 个部署注意) 修复。**没新功能，没破兼容性，没 schema 变更**。

---

## 🐛 修复清单

| ID | 严重度 | 项 | 修复 |
|----|--------|------|------|
| **L1** | 低危 | `_check_auth` 用 `==` 比较 Bearer token 非恒定时间 | `hmac.compare_digest` |
| **L2** | 低危 | `proxy.health_handler` 503 响应里返 `str(e)`, 可能泄漏网络拓扑 | log exc_info, 响应不含 str(e) |
| **D1** | 部署注意 | README 没明确"HTTP 无 TLS, 公网暴露需前置 TLS 终止" | README 双语加 **Deployment** 章节 |
| M1 | 误报 (中危) | 审计员猜测"context 注入 redact 覆盖不完整" | 验证: `record_outbound` 写入前已 redact, `get_context_for_peer` 读出来仍是 redact 后, 无需双 redact |
| L3 | 极低危 | OpenAI key 正则 `sk-[a-zA-Z0-9]{40,}` 可能误杀非真 OpenAI key | 不修 (实际几乎不会触发) |

---

## 📊 数字

| 维度 | 数字 |
|------|------|
| **Files changed** | 4 (server/start.py + server/proxy.py + README.md + README_CN.md) |
| **+ 47 / -4 lines** | README 双语部署段占大头 |
| **Code change** | 6 行实质 (L1: 5 行, L2: 3 行) |
| **Tests** | 243 passed (cue 仓继承, v1.4.6 core 无 Python 测试套件) |
| **Audit findings addressed** | 3 of 5 (L1/L2/D1 fixed, M1 false positive documented, L3 deferred) |
| **Breaking changes** | 0 |
| **Schema changes** | 0 |

---

## 📁 交付清单

| 文件 | 改动 |
|------|------|
| `server/start.py` | L1: `import hmac` + `_check_auth` 改 `hmac.compare_digest` (5 行) |
| `server/proxy.py` | L2: `health_handler` 改 catch + log exc_info, 响应不含 str(e) (3 行) |
| `README.md` | D1: 加 **Deployment** 段 (loopback / LAN / public 三场景, TLS 终止要求) |
| `README_CN.md` | D1: 同上中文版 |
| `CHANGELOG.md` | 加 `v1.4.6` entry |

---

## 🔍 Audit findings (initial report)

完整审计报告见 master 2026-06-07 review。5 项发现中:
- **2 真 + 1 部署注意** → 修
- **1 误报** → 文档化（commit message 写明）
- **1 极低危** → 接受（不修）

---

## 🛡 防泄漏

- L1/L2 修复不引入新 secret pattern
- L1 用标准库 `hmac.compare_digest`, 无新依赖
- L2 不返 `str(e)`, 反而降低信息泄漏面
- D1 文档化约束, 不引入代码

---

## 🎬 下一 session 起点

读本文件 + [CHANGELOG.md](CHANGELOG.md)。

**v1.5 backlog (NOT in v1.4)**:
- Dockerfile + docker-compose (deployment automation)
- structlog observability
- Cross-cue plugin dependencies
- TLS termination built-in (aiohttp ssl_context)
- mTLS support

---

*冻结: 2026-06-07 丝线 (SilkThread)*
*Tag: v1.4.6 (core 仓 only)*
