import { spawn } from "node:child_process";
import type { Config } from "../config.js";
import type { Answer, Receipt } from "../types.js";

export const THREAD_PATTERN = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export function queueArgs(config: Config, answer: Answer): string[] {
  if (!THREAD_PATTERN.test(answer.thread_id) || !answer.text) {
    throw new Error("invalid answer route or empty answer");
  }
  const message = answer.request_id
    ? `针对 request_human 请求 ${answer.request_id} 的用户回复：\n\n${answer.text}`
    : answer.text;
  const args = ["queue", "--thread", answer.thread_id, "--message", message];
  if (config.app_server_url) args.push("--remote", config.app_server_url);
  if (config.app_server_token_env) args.push("--remote-auth-token-env", config.app_server_token_env);
  return args;
}

export class CodexQueue {
  constructor(
    private readonly config: Config,
    private readonly timeoutMs = 45_000,
  ) {}

  async deliver(answer: Answer, signal?: AbortSignal): Promise<Receipt> {
    let args: string[];
    try {
      args = queueArgs(this.config, answer);
    } catch (error) {
      return { status: "failed", detail: messageOf(error) };
    }
    return new Promise((resolve) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      const onAbort = () => controller.abort();
      signal?.addEventListener("abort", onAbort, { once: true });
      if (signal?.aborted) controller.abort();
      let started = false;
      let settled = false;
      const finish = (receipt: Receipt) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal?.removeEventListener("abort", onAbort);
        resolve(receipt);
      };
      const child = spawn(this.config.codex_binary, args, {
        shell: false,
        stdio: "ignore",
        signal: controller.signal,
        windowsHide: true,
      });
      child.once("spawn", () => {
        started = true;
      });
      child.once("error", () => {
        finish(
          started
            ? { status: "unknown", detail: "queue interrupted or timed out; verify before resubmission" }
            : { status: "failed", detail: "could not start codex queue" },
        );
      });
      child.once("exit", (code) => {
        if (controller.signal.aborted) {
          finish({ status: "unknown", detail: "queue interrupted or timed out; verify before resubmission" });
        } else if (code === 0) {
          finish({ status: "accepted", detail: "codex queue accepted the input" });
        } else {
          finish({ status: "unknown", detail: `codex queue exit ${code ?? "unknown"}; verify before resubmission` });
        }
      });
    });
  }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
