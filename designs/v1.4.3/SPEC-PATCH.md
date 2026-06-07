# AgentWire v1.4.3 — Retrospective SPEC-PATCH

> **Date**: 2026-06-07 (back-fill for v1.4.3 which shipped 2026-06-06)
> **Tag**: `v1.4.3` (annotated, see agentwire-core `fc478db` and agentwire-cue `798455c`)
> **Owner**: 丝线 (SilkThread)
> **Purpose**: This document captures the design intent of v1.4.3 features after the fact, since the v1.4.3 release shipped **code + tag + release page + STATUS** but lacked a formal SPEC-PATCH. v1.4.4 retroactively closes this gap.

---

## 🎯 v1.4.3 in one paragraph

v1.4.3 turns AgentWire from a stateless echo gateway into a **history-aware communication layer**. Every A2A message is persisted to per-peer JSONL (with sensitive-data redaction), the host can query/query/export history via JSON-RPC, and a downstream consumer (agentwire-cue) can subscribe to history changes via a new trigger type. A v1.0.1 Agent Card and a SKILL documentation library make the gateway discoverable and consumable.

## 📦 What's in v1.4.3

### Core (agentwire-core)
- **`server/history.py`** (new, 240 lines): per-peer JSONL persistence
  - peer UUID derived from `sha256(context_id)[:16]` (anti-rename)
  - round numbering: 1 outbound + 1 inbound = 1 round; global counter, no recycling
  - FIFO cap when `max_rounds_per_peer > 0`
  - per-peer file: `peer_<uuid>.jsonl`
  - index file: `index.json` with peer metadata
  - export formats: `jsonl` (raw) and `markdown` (human-readable dialogue)
  - thread-safe via `RLock`

- **`server/redact.py`** (new, 60 lines): built-in sensitive pattern catalog
  - 7 patterns: `anthropic_key`, `openai_key`, `github_pat`, `bearer_token`, `jwt`, `private_key_block`, `url_password`
  - served via `GET /redact/patterns` so downstream consumers share the same rules

- **`server/start.py`** (modified, +450 lines): rewritten to:
  - register previously-orphaned routes: `/.well-known/agent.json`, `/health`, `/a2a/jsonrpc`, `/redact/patterns`
  - handle 4 new JSON-RPC methods: `messages/{list,get,peers,export}`
  - record outbound + inbound on every `message/send`
  - inject history metadata into reply when `context_rounds > 0`
  - load `history:` config from `config.yaml` with safe defaults

- **`server/config.yaml.example`**: new `history:` section with full comments

### CUE (agentwire-cue)
- **`core/history_client.py`** (new, 75 lines): 30s LRU cache over CORE's history JSON-RPC
- **`core/history_proxy.py`** (new, 110 lines): `_PeersNamespace` / `_PeerProxy` / `_HistoryNamespace` for natural expression access
- **`core/redact.py`** (new, 90 lines): `RedactClient` — pulls `/redact/patterns` from CORE, 24h local cache, builtin fallback
- **`core/expression.py`**: 3 extensions
  - whitelist + 2 namespaces (`peers.*`, `history.*`)
  - method-call AST node + evaluate() dispatch (`a.b.c(args)`)
  - `_resolve_path` `getattr` fallback for object proxies
- **`core/statechart.py`**: `EvalEnv` accepts `history_client`; emits `peers` + `history` namespaces
- **`core/trigger_impl.py`**: `HistoryChangeTrigger` (cron / a2a / history_change is the full set)

### SKILL library
- `skill/` directory with 9 (core) + 5 (cue) documents
- Bilingual (EN + CN) READMEs
- See `STATUS_v1.4.3.md` for full inventory

## 🔄 Bump-the-schema miss (v1.4.3 sync debt)

**Bug**: v1.4.3 added the `history_change` trigger type at runtime (`trigger_impl.py`,
`host.py`), but **did not update** `schema/plugin.schema.json` to recognize it as a
valid trigger type. Plugins using `history_change` triggers could only be loaded if
schema validation was bypassed.

**Fix**: v1.4.4 `schema/plugin.schema.json` adds `history_change` to the trigger `type`
enum and a new `allOf` branch defining its config schema (required `peer` +
`granularity`, optional `poll_interval_seconds`).

## 🧪 Test coverage

- core: smoke-tested in implementation phase (no formal pytest suite yet — core is
  shell-tested via curl walkthrough in `skill/PROTOCOL_QUICK_REF.md`)
- cue: 234 → 241 tests (v1.4.4 adds 7 owner-alert tests on top of v1.4.3 baseline)
- pre-existing `tests/test_v142_regressions.py` is broken at v1.4.3 (syntax error,
  pre-existing — excluded from pytest run via `--ignore`)

## 🛡 Security

- All commit authors use the `silk-thread <silk-thread@agentwire.local>` pseudonym
- Sensitive data auto-redacted before any history persistence
- Bearer-token auth reused from v1.4.2; no auth breaking changes
- Internal error responses do not leak server-side details

## 🔗 Migration from v1.4.2

- **No breaking changes** for existing v1.4.2 users
- New `history:` config section has safe defaults (`enabled: true`, `max_rounds_per_peer: 0` = unlimited, `context_rounds: 5`)
- To disable history entirely: set `history.enabled: false` in `config.yaml`
- New API surface (`messages/*` JSON-RPC, `/redact/patterns`) is purely additive

## 🔗 Forward-looking

v1.4.4 (next release) is a micro-improvement:
- adds `owner-alert` example (killer scenario for `history_change`)
- adds end-to-end `curl` walkthrough in `PROTOCOL_QUICK_REF.md`
- retroactive `designs/v1.4.3/SPEC-PATCH.md` (this file) and `CHANGELOG.md`

---

*Owner: 丝线 (SilkThread)*
*Companion: [agentwire-cue v1.4.3 SPEC-PATCH](../../agentwire_cue/designs/v1.4.3/SPEC-PATCH.md)*
