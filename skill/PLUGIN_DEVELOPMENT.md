# Plugin Development Guide (for `agentwire-cue`)

> How to author statechart plugins for [agentwire-cue](https://github.com/DerekEXS/agentwire-cue).
> For the complete v1.5 reference, see [PLUGIN_AUTHORING.md](../agentwire_cue/skill/PLUGIN_AUTHORING.md) in the CUE repository.

## Overview

A **plugin** is a single YAML file (`apiVersion: agentwire/v1.2`) that defines a statechart — a finite state machine that:

- Has named **states** (e.g. `idle`, `watching`, `done`)
- Defines **transitions** between states (guard expression → `target` state)
- Executes **actions** on transition (log, set_context, reply_a2a, send_a2a)
- Is **triggered** by external events (cron, A2A message, history_change)

The CUE host loads plugins from a directory, watches for triggers, evaluates expressions (including `peers.*` and `history.*` namespaces), and executes actions. The plugin host handles A2A communication with the AgentWire CORE gateway.

## Minimum viable plugin (v1.2 schema)

```yaml
apiVersion: agentwire/v1.2
kind: plugin

metadata:
  name: my-first
  version: 1.0.0

spec:
  triggers:
    - id: any-incoming
      type: a2a_message_type
      config: { match: "*" }

  statechart:
    initial: idle
    states:
      idle:
        "on":
          MESSAGE_RECEIVED:
            target: reply
            actions:
              - type: log
                with: { level: info, message: "got a message" }

      reply:
        type: final
        actions:
          - type: reply_a2a
            with:
              template: "[{{meta.name}}] echo"

  secrets: []
  permissions:
    network: { http_egress: [], raw_socket: false }
    filesystem: []
    subprocess: { allow: [] }
    env: []
    peers: []
    timers: { max_concurrent: 1, min_interval_ms: 1000 }
```

## Key concepts

### Trigger types

| Type | Triggered by |
|------|-------------|
| `cron` | Recurring schedule (`expression: "0 * * * *"`) |
| `a2a_message_type` | Inbound A2A message on the CUE listener (port 18801) |
| `history_change` | New round detected in CORE peer history (polls `messages/peers`) |

### Expressions

```jinja2
# Guard
guard: "event.new_round > context.last_notified_round"

# Template in action
message: "[{{meta.name}}] received from {{event.peer}}"

# History-aware
guard: "peers.Pawly.history.last_inbound_contains('urgent:')"
```

Full reference: [EXPRESSION_REFERENCE.md](../agentwire_cue/skill/EXPRESSION_REFERENCE.md)

### Security (v1.5.5+)

- **permissions.peers**: When non-empty, `send_a2a` is restricted to the listed peer ids. Empty = legacy permissive behavior.
- **A2A listener**: Defaults to `127.0.0.1`; requires Bearer `admin_token` on inbound messages.
- **Admin API**: Token-gated at `19000`; defaults to `127.0.0.1`.

### From v1.4.8: Peer aliases

```yaml
spec:
  peers:
    Pawly:
      uuid: "pawly-demo-uuid"
      url: "http://agentwire-core:18800"
      description: "小爪 - QwenPaw"
```

### From v1.5.2: Cross-plugin dependencies

```yaml
spec:
  requires:
    plugins: [cron-driven]
    peers: [Pawly]
    capabilities: [metadata]
```

## See also

- [PLUGIN_AUTHORING.md](../agentwire_cue/skill/PLUGIN_AUTHORING.md) — detailed field reference
- [EXPRESSION_REFERENCE.md](../agentwire_cue/skill/EXPRESSION_REFERENCE.md) — expression grammar
- [SKILL.md](SKILL.md) — CORE gateway guide
