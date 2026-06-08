# Changelog

All notable changes to AgentWire-Core are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v1.4.x series (2026-06 — FROZEN)

The v1.4 series implements per-peer message history persistence, sensitive-data
redaction, an agent-facing SKILL documentation library, and the protocol surface
required for downstream plugin hosts to consume that history. v1.4 is the **stable
baseline** going into v1.5; no further v1.4.x work is planned.

---

## [v1.4.6] - 2026-06-07

### Security
- `server/start.py::_check_auth`: use `hmac.compare_digest` for constant-time Bearer token comparison (L1 from initial security audit; mitigates very low-risk timing-side-channel token recovery)
- `server/proxy.py::health_handler`: don't leak `str(e)` in 503 response — log internally, return fixed `{"status": "downstream_unreachable"}` only (L2 from audit; prevents network-topology disclosure like "Connection refused to 127.0.0.1:18800")

### Documentation
- `README.md` + `README_CN.md`: new **Deployment** section explicitly states HTTP-not-HTTPS limitation, lists loopback/LAN/VPN as suitable, public-internet as NOT suitable without TLS-terminating reverse proxy (D1 from audit)

### Audit clarification
- M1 from initial audit (context-injection redact coverage) is a **false positive** — `HistoryManager.get_context_for_peer` returns messages that were already redacted at `record_outbound` write time; no double-application needed
- L3 (OpenAI key regex over-broad, `sk-[a-zA-Z0-9]{40,}`) acknowledged as low risk; not fixed in v1.4.6

### Notes
- v1.4.6 is a **security audit closure** release — fixes 3 low-severity findings (L1, L2, D1) from initial audit, 1 medium finding (M1) confirmed as false positive
- No new features, no breaking changes, no schema changes
- All 243 cue tests still pass (cue unchanged in v1.4.6)

## [v1.4.5] - 2026-06-07

### Changed
- `STATUS_v1.4.4.md`: 真 SHA 校准 (tag `v1.4.4` commit `e58d6e7`) + prior v1.4.3 SHA `cf6d5ed` 引用; 修订 A2A 测试措辞 (明确"协议层基线验证基于 v1.4.2 echo 模板, 非 v1.4.4 端到端验收")

### Added
- `designs/v1.4.4/SPEC-PATCH.md` (新 ≤30 行): symmetric counterpart to cue 仓 v1.4.4 SPEC-PATCH (v1.4.4 core 侧只做文档增补, 不引入新代码或新设计)

### Notes
- v1.4.5 is a **cleanup / spec-debt closure** release — 初梦 P1/P2 行动清单 (commit 拆分 / SHA 校准 / scope 声明 / 设计对称补)
- v1.4.5 acceptance: 243 cue 单测 (从 v1.4.4 继承) 全过 + 4 阶段 leak prevention 扫描 v1.4.5 scope 0 命中
- v1.4.5 commit history (按初梦 P1 建议拆分):
  - core 仓 1 commit (`7f2c931`): SHA 校准 + v1.4.4 SPEC-PATCH 对称补
  - cue 仓 2 commits (`75a830d` + `8ce3e03`): STATUS 校准 + scope 声明

## [v1.4.4] - 2026-06-07

### Added
- `skill/PROTOCOL_QUICK_REF.md`: end-to-end `curl` walkthrough (6 steps from zero to working A2A session)
- `STATUS_v1.4.4.md`: complete delivery checklist
- `CHANGELOG.md` (this file)
- `designs/v1.4.3/SPEC-PATCH.md`: retrospective SPEC for v1.4.3

### Notes
- v1.4.4 is a **micro-improvement** release — no new endpoints, no new triggers, no new expression namespaces
- v1.4.4 acceptance: cue unit tests only (no end-to-end TG notification verification — that belongs to OpenClaw main agent's A2A→TG routing, out of v1.4.4 scope)

## [v1.4.3] - 2026-06-06

### Added
- `server/history.py`: per-peer JSONL history persistence (auto-redacted, round-numbered, FIFO-capable)
- `server/redact.py`: built-in sensitive pattern catalog (7 patterns: API keys, tokens, JWTs, private keys, URL-embedded passwords)
- `server/start.py`: registered previously-orphaned routes (`/.well-known/agent.json`, `/health`, `/a2a/jsonrpc`, `/redact/patterns`)
- JSON-RPC methods: `messages/list`, `messages/get`, `messages/peers`, `messages/export`
- Context auto-injection into `message.metadata.agentwire_history` when `context_rounds > 0`
- `skill/` directory with 9 documents (SKILL+CN, PROTOCOL_QUICK_REF, 5 INTEGRATION_*, PLUGIN_DEVELOPMENT)
- Bilingual `README.md` / `README_CN.md`
- `STATUS_v1.4.3.md`

### Fixed
- Routing bug from v1.4.2: `/.well-known/agent.json`, `/health`, `POST /a2a/jsonrpc` not registered (handlers existed, not wired)
- `server/config.yaml` untracked in v1.4.2 audit #2; now consistent

## [v1.4.2] - 2026-06-05

### Added
- BOM auto-strip on token file reads (`encoding='utf-8-sig'`)
- systemd user unit files: `agentwire.service` + `agentwire-proxy.service`
- `server/proxy.py`: loopback reverse proxy (18802 → 18800)
- CUE: `--a2a-token-env` / `--a2a-token-file` flags (4-source token resolution)

### Security
- v1.4.2 AUDIT (3 commits): 10 issues fixed + 2 follow-ups (CORS allowlist, internal error non-leakage)

## [v1.4.1] - 2026-06-04

### Added
- Plugin host skeleton (Python aiohttp)
- Admin API: 3 endpoints on port 19000 (`/status`, `/plugins`, `/trigger`)
- 5 example cue plugins (echo, echo-with-persist, cron-driven, a2a-with-fallback, file-watcher)
- 6 BUG fixes found during v1.4 P0 implementation
- 9 regression tests
- Total: 235/235 tests green

## [v1.3.1.1] - 2026-05-15

### Fixed
- Sandbox tightening
- Trigger await pattern
- Peer card cache (10min TTL)

## [v1.3.1] - 2026-05-10

### Security
- P0-1: persist.path sandbox (4-layer defense + dotdot/symlink escape)
- P0-2: target validation (loader + statechart runtime)

## [v1.3] - 2026-05-01

### Added
- Initial public release: 154 tests, 1522 lines of core code
- A2A v0.3.0 protocol implementation (TypeScript plugin + Python service)
- End-to-end smoke verification

---

## v1.5 backlog (NOT in v1.4 series)

Items deferred from v1.4 → v1.5:
- Dockerfile + docker-compose (deployment)
- structlog observability (P1)
- Cross-cue plugin dependencies (P1)
- `/messages/import` endpoint (history restore scenario)
- `history.peers.*` cross-peer expression namespace (was deferred from v1.4.4 candidate D)
