import { createConnection } from "node:net";
import WebSocket from "ws";
import type { Source } from "../types.js";
import { THREAD_PATTERN } from "./queue.js";

interface RpcResponse {
  id?: number;
  result?: unknown;
  error?: unknown;
}

export class CodexSourceReader {
  constructor(
    private readonly endpoint: string,
    private readonly tokenEnv?: string,
  ) {}

  async source(threadId: string, signal?: AbortSignal): Promise<Source> {
    if (!THREAD_PATTERN.test(threadId)) throw new Error("invalid thread id");
    if (!this.endpoint) throw new Error("app-server endpoint not configured");
    const options: WebSocket.ClientOptions = { handshakeTimeout: 5_000 };
    let endpoint = this.endpoint;
    const parsed = new URL(endpoint);
    if (parsed.protocol === "unix:") {
      if (!parsed.pathname) throw new Error("explicit unix socket path required");
      const socketPath = decodeURIComponent(parsed.pathname);
      endpoint = "ws://localhost/";
      options.createConnection = () => createConnection(socketPath);
    } else if (!["ws:", "wss:"].includes(parsed.protocol)) {
      throw new Error("unsupported app-server endpoint");
    }
    if (this.tokenEnv) {
      const token = process.env[this.tokenEnv];
      if (!token) throw new Error("app-server token environment variable is empty");
      options.headers = { Authorization: `Bearer ${token}` };
    }
    const ws = new WebSocket(endpoint, options);
    const timeout = AbortSignal.timeout(5_000);
    const combinedSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
    const abort = () => ws.close();
    combinedSignal.addEventListener("abort", abort, { once: true });
    try {
      await opened(ws, combinedSignal);
      const rpc = createRpc(ws);
      await rpc(1, "initialize", { clientInfo: { name: "request_me", version: "0.1.0" } });
      ws.send(JSON.stringify({ method: "initialized", params: {} }));
      const result = (await rpc(2, "thread/read", { threadId, includeTurns: false })) as {
        thread?: { id?: string; name?: string; cwd?: string };
      };
      if (result.thread?.id !== threadId) throw new Error("app-server returned a different thread");
      return {
        title: result.thread.name || undefined,
        cwd: result.thread.cwd || undefined,
      };
    } finally {
      combinedSignal.removeEventListener("abort", abort);
      ws.close();
    }
  }
}

function opened(ws: WebSocket, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      ws.off("open", onOpen);
      ws.off("error", onError);
      ws.off("close", onClose);
      signal.removeEventListener("abort", onAbort);
    };
    const onOpen = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("app-server connection failed"));
    };
    const onClose = () => {
      cleanup();
      reject(new Error("app-server connection closed"));
    };
    const onAbort = () => {
      cleanup();
      reject(new Error("app-server connection timed out"));
    };
    ws.once("open", onOpen);
    ws.once("error", onError);
    ws.once("close", onClose);
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
  });
}

function createRpc(ws: WebSocket): (id: number, method: string, params: unknown) => Promise<unknown> {
  return (id, method, params) =>
    new Promise((resolve, reject) => {
      const onMessage = (data: WebSocket.RawData) => {
        let response: RpcResponse;
        try {
          response = JSON.parse(data.toString()) as RpcResponse;
        } catch {
          return;
        }
        if (response.id !== id) return;
        cleanup();
        if (response.error !== undefined && response.error !== null) {
          reject(new Error(`app-server ${method} failed`));
        } else {
          resolve(response.result);
        }
      };
      const onError = () => {
        cleanup();
        reject(new Error("app-server connection failed"));
      };
      const onClose = () => {
        cleanup();
        reject(new Error("app-server connection closed"));
      };
      const cleanup = () => {
        ws.off("message", onMessage);
        ws.off("error", onError);
        ws.off("close", onClose);
      };
      ws.on("message", onMessage);
      ws.once("error", onError);
      ws.once("close", onClose);
      ws.send(JSON.stringify({ id, method, params }), (error) => {
        if (error) onError();
      });
    });
}
