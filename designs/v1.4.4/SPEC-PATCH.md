# AgentWire-Core v1.4.4 — SPEC-PATCH (symmetric to cue)

> **Date**: 2026-06-07
> **Tag**: `v1.4.4` (annotated, commit `e58d6e7`)
> **Owner**: 丝线 (SilkThread)
> **Companion**: [agentwire-cue v1.4.4 SPEC-PATCH](../../agentwire_cue/designs/v1.4.4/SPEC-PATCH.md)

---

## 🎯 Why this file exists

v1.4.4 cue 仓 has `designs/v1.4.4/SPEC-PATCH.md` documenting the owner-alert killer example + v1.4.3 sync debt closures. This file is the **symmetric counterpart** for the core side — it's intentionally short (≤30 lines) because v1.4.4's core-side work is minimal.

---

## 📦 Core-side v1.4.4 changes

### Documentation only (no code change)

- **`skill/PROTOCOL_QUICK_REF.md`**: append 6-step end-to-end `curl` walkthrough (discover → send → 2nd send → list peers → list history → export markdown) + troubleshooting table
- **`CHANGELOG.md`** (new, Keep-a-Changelog)
- **`STATUS_v1.4.4.md`** (new)
- **`designs/v1.4.3/SPEC-PATCH.md`** (new, retrospective)
- **`README.md` + `README_CN.md`**: status badge → green, link to v1.4.4 release

### No code change in core for v1.4.4

The core gateway was feature-complete in v1.4.3. v1.4.4 is purely about **making v1.4.3 easier to consume** (via the new walkthrough) and **closing the v1.4.3 spec-debt** (this file + companion cue SPEC-PATCH + CHANGELOG).

---

## 🔗 Related

- [agentwire-cue v1.4.4 SPEC-PATCH](../../agentwire_cue/designs/v1.4.4/SPEC-PATCH.md) (the main show)
- [agentwire-core v1.4.3 SPEC-PATCH](v1.4.3/SPEC-PATCH.md) (prior release's retrospective)
- [STATUS_v1.4.4.md](../../STATUS_v1.4.4.md) (delivery checklist)
- [CHANGELOG.md](../../CHANGELOG.md)

---

*Owner: 丝线 (SilkThread)*
*Series: v1.4.x FROZEN*
