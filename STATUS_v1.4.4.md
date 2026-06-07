# AgentWire-Core v1.4.4 — Final Status

> **Released**: 2026-06-07
> **Tag**: `v1.4.4` (annotated; final SHA committed in task 32)
> **Owner**: 丝线 (SilkThread)
> **Series**: v1.4.x FROZEN — see [CHANGELOG.md](CHANGELOG.md) header
> **Protocol**: A2A v1.0.1 + JSON-RPC 2.0
> **License**: MIT
> **Companion**: [agentwire-cue v1.4.4](../../agentwire_cue) (downstream plugin host)

---

## 🎯 v1.4.4 定位：微改进 (Micro-Improvement)

**不是新功能** —— 是把 v1.4.3 已交付的能力**用得更好**。

v1.4.3 三个核心新增：history 持久化 / CUE 表达式命名空间 / `history_change` trigger。
v1.4.4 在此基础上做**杀手示例 + 文档 + 端到端可演示 + 同步债清理**。

---

## 🎯 完成清单 (4 项)

主人拍板 (2026-06-06): v1.4.4 = 混合初梦 4 候选 + 丝线自提项

| # | 项 | 出处 | 优先级 | 状态 |
|---|----|------|--------|------|
| 1 | killer 示例 `owner-alert` (cue yaml) | 初梦 候选 A | P0 | ✅ Done |
| 2 | `PROTOCOL_QUICK_REF.md` 增补端到端 curl walkthrough | 初梦 候选 B | P0 | ✅ Done |
| 3 | v1.4.3 同步债: `designs/v1.4.3/SPEC-PATCH.md` + 双仓 `CHANGELOG.md` | 初梦 + 丝线 | P0 | ✅ Done |
| 4 | v1.4 spec 收尾: DRAFT → FROZEN (双仓 CHANGELOG + ROADMAP) | 丝线 | P1 | ✅ Done |

**显式不做**（按"按需查阅"哲学 + 微改进定位）：
- ❌ `/messages/import` 端点（v1.5）
- ❌ `history.peers.*` 跨 peer 表达式（够用主义）
- ❌ Dockerfile / structlog / 跨 CUE 依赖（v1.5）
- ❌ 任何破坏 v1.4.x 兼容性的 schema 变更

---

## 📊 数字

| 维度 | 数字 |
|------|------|
| **Tag** | `v1.4.4` (annotated) |
| **Commits** | 3 (feat + docs×2) |
| **Files changed** | 4 modified (README + README_CN + PROTOCOL_QUICK_REF) + 4 new (CHANGELOG + designs/v1.4.3/SPEC-PATCH + STATUS + designs/v1.4.3/) |
| **+ 196 / -4 lines** | 主要在 PROTOCOL_QUICK_REF 增补 (~150 行 walkthrough) |
| **Audit** | 0 secrets / 0 personal email / 0 dev path in public files |
| **Author** | 丝线化名 (silk-thread@agentwire.local) |

---

## 📁 交付清单

| 文件 | 类型 | 改动 |
|------|------|------|
| `skill/PROTOCOL_QUICK_REF.md` | M | 末尾追加 "End-to-end curl walkthrough" 章节 (6 步 + troubleshooting 表) |
| `CHANGELOG.md` | A | Keep-a-Changelog 风格, v1.3 / v1.3.1 / v1.3.1.1 / v1.4.1 / v1.4.2 / v1.4.3 / v1.4.4 + v1.5 backlog |
| `STATUS_v1.4.4.md` | A | 本文件 |
| `designs/v1.4.3/SPEC-PATCH.md` | A | v1.4.3 设计意图定格 (含 schema-bump-miss 同步债) |
| `README.md` / `README_CN.md` | M | 即将更新: status badge → green, link to v1.4.4 release |

---

## 🧪 验收范围

按主人 2026-06-06 拍板:
- ✅ **cue 单测** (丝线自验)
  - 7 owner-alert 测试 (cue 仓 `tests/test_owner_alert.py`)
  - 41+ expression 表达式测试 (回归)
  - cue 全套 241/241 测试通过 (排除 v1.4.2 已坏的 test_v142_regressions.py)
- ✅ **core 文档**：PROTOCOL_QUICK_REF 6 步串联可跑（脚本可复制）
- ❌ **不验**：端到端 TG 通知（初梦 OpenClaw 改造，超 scope）

---

## 🔗 关联

- 初梦 `MEMORY-v1.4.4-proposal.md`（原始提案 5 候选）
- 丝线 `MEMORY-v1.4.4-decision.md`（v1.4.4 实施拍板）
- `designs/v1.4.4/SPEC-PATCH.md` in cue 仓（v1.4.4 spec 原始文档）

---

## 🎬 下一 session 起点

读本文件 + `CHANGELOG.md`。

**v1.5 backlog**:
- Dockerfile + docker-compose
- structlog observability
- 跨 CUE 依赖
- `/messages/import` 端点（如果主人换机器场景真实）
- 主 agent 全栈升级时（按主人 2026-06-06 提到的）

---

*冻结: 2026-06-07 丝线 (SilkThread)*
*Tag: v1.4.4 (双仓)*
