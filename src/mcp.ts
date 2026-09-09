import { createHash, randomBytes } from "node:crypto";
import { hostname } from "node:os";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { RequestHandlerExtra } from "@modelcontextprotocol/sdk/shared/protocol.js";
import type { ServerNotification, ServerRequest } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import type { RequestMeClient } from "./client.js";
import type { Choice, Receipt, Sent, Source } from "./types.js";
import { THREAD_PATTERN } from "./codex/queue.js";

type ToolExtra = RequestHandlerExtra<ServerRequest, ServerNotification>;

export interface SourceResolver {
  source(threadId: string, signal?: AbortSignal): Promise<Source>;
}

const choiceSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  value: z.string().min(1),
});

export function createMcpServer(
  client: Pick<RequestMeClient, "send" | "close">,
  host = hostname(),
  resolver?: SourceResolver,
): McpServer {
  const server = new McpServer({ name: "request-me", version: "0.1.0" });

  server.registerTool(
    "request_user_response",
    {
      description:
        "Send a question to the user through their configured external messaging channel when work needs information, a decision, or confirmation that a physical action is complete. Write Markdown explaining work done, important findings, attempts, and the help needed. Optional choices contain id, label and the user's answer value; free text is always available. A sent receipt means the channel accepted the message. After sent success, finish the current turn. The user's response later arrives as a new user turn in this same task; continue the work using that response. Silence leaves the request pending.",
      inputSchema: z.object({
        markdown: z.string().min(1),
        options: z.array(choiceSchema).max(8).optional(),
      }),
    },
    async ({ markdown, options }, extra) => {
      if (!markdown.trim()) throw new Error("markdown is required");
      const { threadId, callId } = routing(extra._meta);
      const sent = await client.send(
        {
          id: messageId(threadId, callId, "request_human"),
          thread_id: threadId,
          markdown,
          options: options as Choice[] | undefined,
          source: await resolveSource(resolver, host, threadId, extra.signal),
        },
        true,
        extra.signal,
      );
      return toolResult(sent);
    },
  );

  server.registerTool(
    "send_user_notification",
    {
      description:
        "Send a progress update or result to the user through their configured external messaging channel. A sent receipt means the channel accepted the message. Continue the current work after sending; finish only when the task is complete. When progress depends on the user's information, decision, or action, use request_user_response to create an answerable request.",
      inputSchema: z.object({ markdown: z.string().min(1) }),
    },
    async ({ markdown }, extra) => {
      if (!markdown.trim()) throw new Error("markdown is required");
      const { threadId, callId } = routing(extra._meta);
      const sent = await client.send(
        {
          id: messageId(threadId, callId, "notify"),
          thread_id: threadId,
          markdown,
          source: await resolveSource(resolver, host, threadId, extra.signal),
        },
        false,
        extra.signal,
      );
      return toolResult(sent);
    },
  );

  server.registerTool(
    "close_user_request",
    {
      description:
        "Close a previously sent user request that has been resolved or is no longer needed. Use the request_id returned by request_user_response. Closing removes the pending question while preserving the original task; it does not enqueue a user message or start a new turn.",
      inputSchema: z.object({ request_id: z.string().min(1) }),
    },
    async ({ request_id: requestId }, extra) => {
      if (!requestId.trim() || /[\\/]/.test(requestId)) throw new Error("request_id is required");
      const { threadId } = routing(extra._meta);
      await client.close(requestId, threadId, extra.signal);
      return toolResult({ status: "closed" } satisfies Receipt);
    },
  );

  return server;
}

export function routing(meta: Record<string, unknown> | undefined): { threadId: string; callId: string } {
  if (!meta) throw new Error("per-call metadata is required");
  const direct = typeof meta.threadId === "string" ? meta.threadId.toLowerCase() : "";
  let nested = "";
  const nestedRaw = meta["x-codex-turn-metadata"];
  if (nestedRaw && typeof nestedRaw === "object" && !Array.isArray(nestedRaw)) {
    const candidate = (nestedRaw as Record<string, unknown>).thread_id;
    if (typeof candidate === "string") nested = candidate.toLowerCase();
  } else if (typeof nestedRaw === "string") {
    try {
      const decoded = JSON.parse(nestedRaw) as Record<string, unknown>;
      if (typeof decoded.thread_id === "string") nested = decoded.thread_id.toLowerCase();
    } catch {
      // The concrete direct identifier may still be valid.
    }
  }
  if (direct && nested && direct !== nested) throw new Error("conflicting thread identifiers");
  const threadId = direct || nested;
  if (!THREAD_PATTERN.test(threadId)) throw new Error("a concrete UUID threadId is required in _meta");
  return {
    threadId,
    callId: typeof meta.callId === "string" ? meta.callId : "",
  };
}

export function messageId(threadId: string, callId: string, tool: string): string {
  if (!callId) return randomBytes(16).toString("hex");
  return createHash("sha256").update(`${threadId}\0${callId}\0${tool}`).digest("hex");
}

async function resolveSource(
  resolver: SourceResolver | undefined,
  host: string,
  threadId: string,
  signal?: AbortSignal,
): Promise<Source> {
  if (resolver) {
    try {
      const source = await resolver.source(threadId, signal);
      return { ...source, host: source.host || host };
    } catch {
      // Source enrichment is optional; routing does not depend on it.
    }
  }
  return { host };
}

function toolResult(value: Sent | Receipt) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(value) }],
    structuredContent: value as unknown as Record<string, unknown>,
  };
}
