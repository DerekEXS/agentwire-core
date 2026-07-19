/**
 * AgentWire A2A Adapter — dispatch (v2.3, 方案 C2)
 *
 * 把 A2A SendMessage 转交给 OpenClaw agent。实现方式：spawn `openclaw agent`
 * CLI 子进程（以外部 operator client 身份走 gateway WS，绕开 plugin runtime
 * 的 scope/trust 限制——M1 验证 `api.runtime.gateway.request` 被信任门拦截，
 * CLI 路径已实战可用）。
 *
 * v2.3.1 可选升级：把本模块内部换成进程内 WS loopback client（见
 * designs/v2.3/WS-PROTOCOL-VERIFICATION.md），对外接口 callAgent() 不变。
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

/**
 * openclaw 二进制路径。
 *
 * 默认 `"openclaw"` 依赖 PATH 解析（Node execFile 在 file 不含路径分隔符时
 * 会查 PATH）。plugin 跑在 OpenClaw gateway 进程内，该进程的 PATH 通常含
 * openclaw 所在目录（它自己从那里启动），所以 PATH 解析可靠。
 *
 * 覆盖优先级：plugin config > env AGENTWIRE_OPENCLAW_BIN > PATH 解析。
 */
function resolveOpenclawBin(configBin?: string): string {
  if (configBin && configBin.trim()) return configBin.trim();
  const envBin = process.env.AGENTWIRE_OPENCLAW_BIN;
  if (envBin && envBin.trim()) return envBin.trim();
  return "openclaw";
}

export interface CallAgentOptions {
  /** CLI --timeout，秒。默认 120。 */
  timeoutS?: number;
  /** 显式 session key（格式 agent:<id>:<scope>）。不传则让 CLI 用 agent 默认 session。 */
  sessionKey?: string;
  /** openclaw 二进制路径覆盖（来自 plugin config）。 */
  openclawBin?: string;
}

export interface CallAgentResult {
  /** agent 回复文本（多个 payload 的 text 拼接，换行分隔）。 */
  text: string;
  /** CLI 返回的 runId。 */
  runId?: string;
  /** CLI 返回的 status（"ok" | "error" | ...）。 */
  status: string;
  /** CLI 返回的 summary。 */
  summary?: string;
}

/**
 * 调 OpenClaw agent 拿回复文本。
 *
 * 失败时抛 Error（含 stderr/stdout 片段），调用方负责包成 A2A Task(FAILED)。
 */
export async function callAgent(
  agentId: string,
  text: string,
  opts?: CallAgentOptions
): Promise<CallAgentResult> {
  const timeoutS = opts?.timeoutS ?? 120;
  const bin = resolveOpenclawBin(opts?.openclawBin);

  const args: string[] = [
    "agent",
    "--agent", agentId,
    "--message", text,
    "--json",
    "--timeout", String(timeoutS),
  ];
  if (opts?.sessionKey) {
    args.push("--session-key", opts.sessionKey);
  }
  // --deliver 不传（默认 false，不投递到 channel，仅返回文本）

  // execFile timeout 略大于 CLI --timeout，给 CLI 缓冲退出。
  const execTimeoutMs = (timeoutS + 15) * 1000;

  let stdout: string;
  let stderr: string;
  try {
    const r = await execFileAsync(bin, args, {
      timeout: execTimeoutMs,
      maxBuffer: 16 * 1024 * 1024, // 16MB，agent 回复 + 记忆可能很长
      env: { ...process.env, FORCE_COLOR: "0", NO_COLOR: "1" }, // 禁 ANSI 着色
    });
    stdout = r.stdout ?? "";
    stderr = r.stderr ?? "";
  } catch (e: any) {
    // execFile 在非0退出码或超时时 reject，但 stdout/stderr 仍可能在 e 上
    stdout = e?.stdout ?? "";
    stderr = e?.stderr ?? "";
    const msg =
      e?.killed && e?.signal === "SIGTERM"
        ? `openclaw agent timed out after ${execTimeoutMs}ms`
        : `openclaw agent exited: ${e?.name}: ${e?.message}`;
    throw new Error(
      `${msg}\n--stderr--\n${String(stderr).slice(0, 800)}\n--stdout--\n${String(stdout).slice(0, 800)}`
    );
  }

  // CLI --json 输出纯 JSON（非 TTY + NO_COLOR 已确保）。但 stderr 可能有日志，
  // stdout 才是 JSON。取 stdout 末尾的 JSON 对象（防止前面有 warning 行）。
  const jsonText = extractJsonObject(stdout);
  if (!jsonText) {
    throw new Error(
      `openclaw agent --json: no JSON in stdout\n--stderr--\n${stderr.slice(0, 800)}\n--stdout--\n${stdout.slice(0, 800)}`
    );
  }

  let parsed: any;
  try {
    parsed = JSON.parse(jsonText);
  } catch (e: any) {
    throw new Error(
      `openclaw agent --json: parse error: ${e?.message}\n--stdout--\n${stdout.slice(0, 800)}`
    );
  }

  const payloads: any[] = parsed?.result?.payloads ?? [];
  const replyText = payloads
    .map((p: any) => (typeof p === "string" ? p : p?.text ?? ""))
    .filter(Boolean)
    .join("\n");

  return {
    text: replyText || `[no text in result.payloads]`,
    runId: parsed?.runId,
    status: parsed?.status ?? "unknown",
    summary: parsed?.summary,
  };
}

/** 从可能混杂日志的 stdout 里提取最外层 JSON 对象。 */
function extractJsonObject(s: string): string | null {
  const start = s.indexOf("{");
  if (start < 0) return null;
  // 从第一个 { 开始，配对 } 找完整对象（容忍字符串内的括号）
  let depth = 0;
  let inStr = false;
  let escape = false;
  for (let i = start; i < s.length; i++) {
    const ch = s[i];
    if (inStr) {
      if (escape) escape = false;
      else if (ch === "\\") escape = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return s.slice(start, i + 1);
    }
  }
  return null;
}
