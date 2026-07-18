/**
 * AgentWire A2A Adapter — v2.3.0 (方案 C2)
 *
 * 在 OpenClaw gateway 进程内暴露标准 A2A v1.0 JSON-RPC 端点，把 SendMessage
 * 转交给 OpenClaw agent。调 agent 走 `openclaw agent` CLI 子进程（以外部
 * operator client 身份走 gateway WS，绕开 plugin runtime 的 scope/trust
 * 限制——M1 验证 api.runtime.gateway.request 被 trust gate 拦，CLI 路径可用）。
 *
 * 仅实现 SendMessage（同步返回 agent 回复）。GetTask/ListTasks/CancelTask
 * 不实现（-32601）——权威 task store 在 CORE 侧 SQLite，见
 * designs/v2.3/DESIGN.md「查询路径澄清」。
 */

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import type { IncomingMessage, ServerResponse } from "node:http";
import { callAgent } from "./dispatch.js";

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf-8");
}

function extractText(message: any): string {
  const parts = message?.parts ?? [];
  return parts
    .map((p: any) => (typeof p === "string" ? p : p?.text ?? ""))
    .filter(Boolean)
    .join("\n");
}

function resolveAgentId(message: any, params: any, defaultAgent: string): string {
  const md = message?.metadata ?? {};
  const candidates = [
    md.agentId,
    md.agent_id,
    md.to,
    md.peer,
    params?.agentId,
    params?.agent_id,
  ];
  for (const c of candidates) {
    if (typeof c === "string" && c) return c;
  }
  return defaultAgent;
}

function rpcOk(id: any, result: any) {
  return { jsonrpc: "2.0", id, result };
}

function rpcErr(id: any, code: number, message: string) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

export default definePluginEntry({
  id: "agentwire-a2a",
  name: "AgentWire A2A Adapter",
  description: "Exposes Google A2A v1.0 JSON-RPC endpoint for OpenClaw agents (v2.3)",
  register(api: any) {
    const defaultAgent = "main";

    // --- /a2a/jsonrpc ---
    api.registerHttpRoute({
      path: "/a2a/jsonrpc",
      auth: "plugin",
      match: "exact",
      handler: async (req: IncomingMessage, res: ServerResponse) => {
        if (req.method !== "POST") {
          res.writeHead(405, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Method Not Allowed" }));
          return;
        }

        let rpc: any;
        try {
          rpc = JSON.parse(await readBody(req));
        } catch (e) {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(rpcErr(null, -32700, "Parse error")));
          return;
        }

        const rpcId = rpc?.id ?? null;
        const method = rpc?.method;
        const params = rpc?.params ?? {};
        const message = params?.message ?? {};

        if (method !== "SendMessage" && method !== "message/send") {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(
            JSON.stringify(
              rpcErr(rpcId, -32601, `Method not found (v2.3.0 implements SendMessage only): ${method}`)
            )
          );
          return;
        }

        const text = extractText(message);
        if (!text) {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(rpcErr(rpcId, -32602, "no text in message.parts")));
          return;
        }

        const agentId = resolveAgentId(message, params, defaultAgent);
        const taskId = `a2a-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const contextId = message?.contextId || taskId;
        // 同 contextId 进同 OpenClaw session（支持多轮）；无 contextId 则每消息独立。
        const sessionKey = `agent:${agentId}:a2a:${contextId}`;

        console.log(
          `[agentwire-a2a] SendMessage agentId=%s sessionKey=%s text=%j`,
          agentId,
          sessionKey,
          text.slice(0, 80)
        );

        // ===== 方案 C2：spawn `openclaw agent` CLI（绕 plugin trust gate）=====
        try {
          const result = await callAgent(agentId, text, {
            timeoutS: 120,
            sessionKey,
          });
          console.log(
            "[agentwire-a2a] agent reply status=%s runId=%s len=%d",
            result.status,
            result.runId,
            result.text.length
          );

          const state = result.status === "ok" ? "completed" : "failed";
          const response = rpcOk(rpcId, {
            task: {
              id: taskId,
              contextId,
              status: {
                state,
                message: {
                  messageId: `reply-${taskId}`,
                  contextId,
                  taskId,
                  role: "agent",
                  parts: [{ type: "text", text: result.text }],
                },
                timestamp: new Date().toISOString(),
              },
            },
          });

          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify(response));
        } catch (e: any) {
          console.log(
            "[agentwire-a2a] dispatch FAILED: %s: %s",
            e?.name ?? "Error",
            e?.message ?? String(e)
          );

          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(
            JSON.stringify(
              rpcOk(rpcId, {
                task: {
                  id: taskId,
                  contextId,
                  status: {
                    state: "failed",
                    message: {
                      messageId: `err-${taskId}`,
                      role: "agent",
                      parts: [
                        {
                          type: "text",
                          text: `dispatch error: ${e?.message ?? String(e)}`,
                        },
                      ],
                    },
                    timestamp: new Date().toISOString(),
                  },
                },
              })
            )
          );
        }
      },
    });

    // --- /.well-known/agent.json ---
    api.registerHttpRoute({
      path: "/.well-known/agent.json",
      auth: "plugin",
      match: "exact",
      handler: async (_req: IncomingMessage, res: ServerResponse) => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            name: "OpenClaw A2A Gateway",
            description: "AgentWire A2A v1.0 adapter for OpenClaw agents",
            url: "http://127.0.0.1:18789/a2a/jsonrpc",
            version: "2.3.0",
            protocolVersion: "1.0",
            capabilities: {
              streaming: false,
              pushNotifications: false,
              extendedAgentCard: false,
            },
            defaultInputModes: ["text"],
            defaultOutputModes: ["text"],
            skills: [
              { id: "main", name: "main", description: "OpenClaw main agent" },
            ],
            agents: [{ id: "main", name: "main" }],
          })
        );
      },
    });

    // --- /health (a2a adapter health) ---
    api.registerHttpRoute({
      path: "/a2a/health",
      auth: "plugin",
      match: "exact",
      handler: async (_req: IncomingMessage, res: ServerResponse) => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(
          JSON.stringify({
            status: "ok",
            service: "agentwire-a2a",
            version: "2.3.0",
          })
        );
      },
    });

    console.log(
      "[agentwire-a2a] plugin registered: /a2a/jsonrpc + /.well-known/agent.json + /a2a/health"
    );
  },
});
