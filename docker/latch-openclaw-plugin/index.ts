import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

type GatePluginConfig = {
  approveUrl?: string;
  timeoutMs?: number;
  failClosed?: boolean;
};

type LatchDecision = {
  decision: "allow-once" | "deny";
  reason: string;
};

const DEFAULT_APPROVE_URL = "http://127.0.0.1:18890/approve";
const DEFAULT_TIMEOUT_MS = 120000;
const LATCH_HOOK_SESSION_MARKER = ":hook:latch:";

function resolveApproveReplyUrl(approveUrl: string): string {
  try {
    const u = new URL(approveUrl);
    const path = u.pathname.replace(/\/+$/, "");
    if (path.endsWith("/approve")) {
      u.pathname = `${path}/reply`;
      return u.toString();
    }
    u.pathname = `${path || ""}/approve/reply`;
    return u.toString();
  } catch {
    const trimmed = approveUrl.replace(/\/+$/, "");
    if (trimmed.endsWith("/approve")) return `${trimmed}/reply`;
    return `${trimmed}/approve/reply`;
  }
}

function parseBoolean(value: string | undefined): boolean | undefined {
  if (!value) return undefined;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return undefined;
}

function parseTimeout(value: string | undefined): number | undefined {
  if (!value) return undefined;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1000 || parsed > 120000) return undefined;
  return parsed;
}

function resolveConfig(pluginConfig: unknown): {
  approveUrl: string;
  timeoutMs: number;
  failClosed: boolean;
} {
  const cfg = (pluginConfig ?? {}) as GatePluginConfig;
  const approveUrl = (
    cfg.approveUrl ??
    process.env.LATCH_APPROVE_URL ??
    process.env.LATCH_URL ??
    DEFAULT_APPROVE_URL
  ).trim();
  const timeoutMs =
    cfg.timeoutMs ?? parseTimeout(process.env.LATCH_APPROVE_TIMEOUT_MS) ?? DEFAULT_TIMEOUT_MS;
  const failClosed =
    cfg.failClosed ?? parseBoolean(process.env.LATCH_FAIL_CLOSED) ?? true;
  return { approveUrl, timeoutMs, failClosed };
}

async function requestLatchDecision(params: {
  approveUrl: string;
  timeoutMs: number;
  toolName: string;
  toolInput: Record<string, unknown>;
  runId?: string;
  toolCallId?: string;
  sessionKey?: string;
}): Promise<LatchDecision> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), params.timeoutMs);

  try {
    const response = await fetch(params.approveUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        command: params.toolName,
        tool_input: params.toolInput,
        run_id: params.runId,
        tool_call_id: params.toolCallId,
        session_key: params.sessionKey,
      }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Latch returned HTTP ${response.status}`);
    }

    const body = (await response.json()) as {
      decision?: string;
      reason?: string;
    };
    const decision = String(body?.decision ?? "").trim().toLowerCase();
    const reason = String(body?.reason ?? "").trim();
    if (decision === "allow-once") {
      return { decision: "allow-once", reason: reason || "Approved by latch" };
    }
    if (decision === "deny") {
      return { decision: "deny", reason: reason || "Denied by latch" };
    }
    throw new Error(`Invalid latch decision: ${JSON.stringify(body)}`);
  } finally {
    clearTimeout(timer);
  }
}

export default function register(api: OpenClawPluginApi) {
  const { approveUrl, timeoutMs, failClosed } = resolveConfig(api.pluginConfig);
  const approveReplyUrl = resolveApproveReplyUrl(approveUrl);
  api.logger.info?.(
    `latch-approval-gate enabled: approveUrl=${approveUrl} approveReplyUrl=${approveReplyUrl} timeoutMs=${timeoutMs} failClosed=${String(failClosed)}`,
  );

  api.on("message_received", async (event, ctx) => {
    const content = typeof event.content === "string" ? event.content.trim() : "";
    if (!content) return;
    if (!ctx.channelId || !ctx.conversationId) return;

    try {
      const response = await fetch(approveReplyUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel: ctx.channelId,
          conversation_id: ctx.conversationId,
          content,
          account_id: ctx.accountId,
          from: event.from,
          timestamp: event.timestamp,
        }),
      });
      if (!response.ok) {
        api.logger.debug?.(
          `latch-approval-gate: approve reply bridge returned HTTP ${response.status}`,
        );
      }
    } catch (error) {
      api.logger.debug?.(
        `latch-approval-gate: approve reply bridge unavailable: ${String(error)}`,
      );
    }
  });

  api.on("before_tool_call", async (event, ctx) => {
    // Broad recursion guard: skip re-gating only for Latch-generated hook sessions.
    // This keeps normal user tool calls fully gated while preventing approval loops.
    if (typeof ctx.sessionKey === "string" && ctx.sessionKey.includes(LATCH_HOOK_SESSION_MARKER)) {
      return;
    }

    try {
      const decision = await requestLatchDecision({
        approveUrl,
        timeoutMs,
        toolName: event.toolName,
        toolInput: event.params ?? {},
        runId: event.runId,
        toolCallId: event.toolCallId,
        sessionKey: ctx.sessionKey,
      });
      if (decision.decision === "allow-once") {
        return;
      }
      return {
        block: true,
        blockReason: `Latch denied "${event.toolName}": ${decision.reason}`,
      };
    } catch (error) {
      const reason = `Latch check failed for "${event.toolName}": ${String(error)}`;
      api.logger.warn?.(reason);
      if (failClosed) {
        return { block: true, blockReason: reason };
      }
      return;
    }
  });
}
