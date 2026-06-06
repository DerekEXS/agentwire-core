# Plugin Development Guide (for `agentwire-cue`)

> How to author statechart plugins for the [agentwire-cue](https://github.com/DerekEXS/agentwire-cue) plugin host. AgentWire CORE is the protocol layer; the *plugin host* (cue) is what interprets your YAML and turns it into agent behavior.

## What is a "plugin" here?

A **plugin** is a single YAML file that defines a statechart — a finite state machine that:

- Has named **states** (e.g. `idle`, `waiting`, `done`)
- Defines **transitions** between states (`when` condition → `target` state)
- Executes **actions** when entering states (HTTP requests, file writes, LLM calls, etc.)
- Is **triggered** by external events (cron, A2A message, history change, etc.)

You write the YAML once. The cue host loads it, watches for triggers, evaluates expressions, and executes actions. The plugin host handles A2A communication with the AgentWire CORE gateway.

## Minimum viable plugin

```yaml
# plugins/hello.yaml
id: hello
version: 1.0.0
description: Echo "Hello, world!" when triggered.

states:
  idle:
    on_enter:
      - action: log
        params: { message: "Hello, world!" }
    transitions:
      - { when: "event.type == 'a2a_message'", target: done }

triggers:
  - name: any_a2a_message
    type: a2a_message_type
    match: "*"
```

That's a complete plugin. It will print "Hello, world!" the first time any A2A message arrives, then transition to `done`.

## The 4 primitives

### 1. States

Named nodes in the state machine. A state can have:

- `on_enter` — list of actions to run when the state is entered
- `on_exit` — list of actions to run when the state is exited
- `transitions` — list of `when` conditions and target states

```yaml
states:
  collecting_info:
    on_enter:
      - action: http_request
        params: { url: "https://api.example.com/data", method: GET }
    on_exit:
      - action: log
        params: { message: "leaving collecting_info" }
    transitions:
      - when: "context.data_loaded == true"
        target: processing
      - when: "context.data_loaded == false"
        target: error
```

### 2. Transitions

```yaml
transitions:
  - when: "expression involving event/context/state"
    target: state_name
```

Expressions are evaluated against the `env` object:

- `event.*` — the triggering event
- `context.*` — user-defined state across the statechart
- `state.*` — current state metadata
- `meta.*` — agent metadata
- `now()` — current timestamp
- `peers.*` — known peer agents (v1.4.3+)
- `history.*` — recent message history (v1.4.3+)

Example:

```yaml
- when: "history.peer('Pawly').last_inbound_contains('project:')"
  target: project_kickoff
```

### 3. Actions

Predefined action types. The cue host provides:

| Action | Purpose |
|--------|---------|
| `http_request` | Make an HTTP call |
| `write_file` | Write a file (sandboxed) |
| `read_file` | Read a file (sandboxed) |
| `spawn_subprocess` | Run a command (sandboxed) |
| `log` | Log a message |
| `send_a2a` | Send an A2A message to a peer |

Example:

```yaml
on_enter:
  - action: http_request
    params:
      url: "https://api.example.com/notify"
      method: POST
      body:
        template: |
          {{ state.name }} finished for {{ context.user }}
```

### 4. Triggers

What makes the statechart react to the world.

| Trigger type | Fires when… |
|--------------|-------------|
| `cron` | A cron expression matches current time |
| `a2a_message_type` | An A2A message of a given type arrives |
| `history_change` | A history round completes (v1.4.3+) |
| `manual` | Operator calls `cue trigger <plugin> <event>` |

Example:

```yaml
triggers:
  - name: morning_digest
    type: cron
    expression: "0 8 * * *"

  - name: pawly_replied
    type: history_change
    peer: "Pawly"
    granularity: round
```

## Working example: morning digest

```yaml
# plugins/morning_digest.yaml
id: morning_digest
version: 1.0.0
description: At 8am, summarize the last 24h of agent traffic and post to a digest channel.

states:
  gathering:
    on_enter:
      - action: read_file
        params:
          path: "~/.cache/agentwire/digest_template.md"
        save_as: context.template
    transitions:
      - when: "context.template != null"
        target: summarizing

  summarizing:
    on_enter:
      - action: http_request
        params:
          url: "http://127.0.0.1:18800/a2a/jsonrpc"
          method: POST
          body:
            jsonrpc: "2.0"
            id: 1
            method: "messages/list"
            params: { limit: 100 }
        save_as: context.recent_messages
    transitions:
      - when: "context.recent_messages != null"
        target: posting

  posting:
    on_enter:
      - action: send_a2a
        params:
          peer: "初梦"
          text: "Morning digest: {{ context.recent_messages | count }} messages in last 24h."
    transitions:
      - when: "true"
        target: done

  done: {}

triggers:
  - name: morning
    type: cron
    expression: "0 8 * * *"
```

## How to test a plugin locally

```bash
# 1. Start AgentWire CORE
cd /mnt/d/项目/A2A/agentwire_core/server
python3 start.py --host 127.0.0.1 --port 18800 --token-file /tmp/token.txt

# 2. Start the cue host with your plugin
cd /mnt/d/项目/A2A/agentwire_cue
python3 -m agentwire_cue host --plugin-dir ../plugins --a2a-url http://127.0.0.1:18800 --a2a-token-file /tmp/token.txt

# 3. Trigger manually
cue trigger morning_digest manual
```

## Debugging tips

- Set `LOG_LEVEL=DEBUG` to see all transition evaluations
- Use `action: log` liberally; logs go to stdout of the cue host
- The `meta` namespace exposes internal state for inspection: `meta.plugin_id`, `meta.current_state`, `meta.last_transition_ts`

## See also

- [SKILL.md](SKILL.md) — protocol background
- [INTEGRATION_Generic.md](INTEGRATION_Generic.md) — alternative: write a custom agent in any language instead of a plugin
- [PROTOCOL_QUICK_REF.md](PROTOCOL_QUICK_REF.md) — JSON-RPC methods
- agentwire-cue `PLUGIN_AUTHORING.md` — the cue host's own detailed reference (in the agentwire-cue repo)
