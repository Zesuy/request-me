import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import test from "node:test";
import { Client as McpClient } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { WebSocketServer } from "ws";
import { BridgeWorker } from "../bridge.js";
import { RequestMeClient } from "../client.js";
import { loadConfig, parseCommandLine, type Config } from "../config.js";
import { CodexQueue, queueArgs } from "../codex/queue.js";
import { CodexSourceReader } from "../codex/source.js";
import { createMcpServer, messageId, routing } from "../mcp.js";
import type { Answer, Message, Receipt } from "../types.js";

const thread = "01a07bde-f801-7992-bb5d-b80b58adac3f";
const baseConfig: Config = {
  server_url: "http://127.0.0.1:8080",
  token_env: "REQUEST_ME_TEST_TOKEN",
  host_label: "test",
  codex_binary: "codex",
  app_server_url: "",
};

test("configuration remains compatible with the Go JSON format", async () => {
  const directory = await mkdtemp(join(tmpdir(), "request-me-"));
  const path = join(directory, "bridge.json");
  process.env.REQUEST_ME_TEST_TOKEN = "secret";
  await writeFile(
    path,
    JSON.stringify({ server_url: "https://example.test", token_env: "REQUEST_ME_TEST_TOKEN" }),
  );
  try {
    const config = await loadConfig(path);
    assert.equal(config.server_url, "https://example.test");
    assert.equal(config.codex_binary, "codex");
    assert.deepEqual(parseCommandLine(["-config", path, "--once"]), { configPath: path, once: true });
  } finally {
    delete process.env.REQUEST_ME_TEST_TOKEN;
    await rm(directory, { recursive: true });
  }
});

test("HTTP client preserves Markdown, choices, auth and strict sent receipt", async () => {
  const server = createServer(async (request, response) => {
    assert.equal(request.headers.authorization, "Bearer test-token");
    assert.equal(request.url, "/v1/requests");
    const chunks: Buffer[] = [];
    for await (const chunk of request) chunks.push(Buffer.from(chunk));
    const message = JSON.parse(Buffer.concat(chunks).toString()) as Message;
    assert.equal(message.markdown, "## 原文\n```\nraw\n```");
    assert.equal(message.options?.[0]?.value, "继续检查");
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({ id: message.id, status: "sent", message_id: "qq-id" }));
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert(address && typeof address === "object");
  try {
    const client = new RequestMeClient(`http://127.0.0.1:${address.port}`, "test-token");
    const sent = await client.send(
      {
        id: "request",
        thread_id: thread,
        markdown: "## 原文\n```\nraw\n```",
        options: [{ id: "a", label: "继续", value: "继续检查" }],
        source: {},
      },
      true,
    );
    assert.equal(sent.message_id, "qq-id");
  } finally {
    server.close();
  }
});

test("routing accepts concrete branch metadata and rejects conflicts", () => {
  assert.equal(routing({ threadId: thread }).threadId, thread);
  assert.equal(
    routing({ "x-codex-turn-metadata": JSON.stringify({ thread_id: thread, session_id: "root" }) }).threadId,
    thread,
  );
  assert.throws(() =>
    routing({
      threadId: thread,
      "x-codex-turn-metadata": { thread_id: "01a07bde-f801-7992-bb5d-b80b58adac30" },
    }),
  );
  assert.throws(() => routing(undefined));
  assert.equal(messageId(thread, "call", "notify"), messageId(thread, "call", "notify"));
  assert.equal(messageId(thread, "call", "notify").length, 64);
});

test("MCP exposes only the three tools and keeps routing metadata out of schemas", async () => {
  const messages: Array<{ message: Message; human: boolean }> = [];
  let closedThread = "";
  const api = {
    async send(message: Message, human: boolean) {
      messages.push({ message, human });
      return { id: message.id, status: "sent" };
    },
    async close(_id: string, targetThread: string) {
      closedThread = targetThread;
    },
  };
  const server = createMcpServer(api, "WSL", {
    async source() {
      return { title: "检查连接", cwd: "/work/tmp" };
    },
  });
  const client = new McpClient({ name: "test", version: "1" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  try {
    const listed = await client.listTools();
    assert.deepEqual(
      listed.tools.map((tool) => tool.name).sort(),
      ["close_user_request", "request_user_response", "send_user_notification"],
    );
    for (const tool of listed.tools) {
      const schema = JSON.stringify(tool.inputSchema);
      assert(!schema.includes("threadId"));
      assert(!schema.includes("thread_id"));
      assert(!schema.includes("callId"));
    }
    const result = await client.callTool({
      name: "request_user_response",
      arguments: {
        markdown: "**keep**",
        options: [{ id: "a", label: "A", value: "alpha" }],
      },
      _meta: { threadId: thread, callId: "c1" },
    });
    assert.equal(result.isError, undefined);
    assert.equal(messages[0]?.message.markdown, "**keep**");
    assert.equal(messages[0]?.message.source.host, "WSL");
    assert.equal(messages[0]?.message.options?.[0]?.value, "alpha");
    await client.callTool({
      name: "close_user_request",
      arguments: { request_id: "m1" },
      _meta: { threadId: thread },
    });
    assert.equal(closedThread, thread);
    const invalid = await client.callTool({ name: "send_user_notification", arguments: { markdown: "x" } });
    assert.equal(invalid.isError, true);
  } finally {
    await client.close();
    await server.close();
  }
});

test("queue arguments preserve input and associate the original request", async () => {
  const raw = "--help ; $(something)\n你好";
  const answer: Answer = { id: "a", request_id: "question-2", thread_id: thread, text: raw };
  const config = {
    ...baseConfig,
    app_server_url: "unix:///tmp/control.sock",
    app_server_token_env: "REMOTE_TOKEN",
  };
  assert.deepEqual(queueArgs(config, answer), [
    "queue",
    "--thread",
    thread,
    "--message",
    `针对 request_human 请求 question-2 的用户回复：\n\n${raw}`,
    "--remote",
    config.app_server_url,
    "--remote-auth-token-env",
    "REMOTE_TOKEN",
  ]);
  const receipt = await new CodexQueue({ ...baseConfig, codex_binary: "__missing_request_me_binary__" }).deliver(answer);
  assert.equal(receipt.status, "failed");
});

test("bridge does not replay queue delivery after a lost receipt", async () => {
  const answer: Answer = { id: "a", request_id: "q", thread_id: thread, text: "reply" };
  let receiptFails = true;
  let deliveries = 0;
  const receipts: Receipt[] = [];
  const api = {
    async answers() {
      return [answer];
    },
    async receipt(_id: string, receipt: Receipt) {
      if (receiptFails) throw new Error("offline");
      receipts.push(receipt);
    },
  };
  const worker = new BridgeWorker(api, {
    async deliver() {
      deliveries += 1;
      return { status: "accepted" };
    },
  });
  await assert.rejects(worker.step());
  receiptFails = false;
  await worker.step();
  assert.equal(deliveries, 1);
  assert.equal(receipts.length, 2);
});

test("source enrichment uses only initialize and read-only thread/read", async () => {
  const http = createServer();
  const websocket = new WebSocketServer({ server: http });
  const methods: string[] = [];
  websocket.on("connection", (socket) => {
    socket.on("message", (raw) => {
      const request = JSON.parse(raw.toString()) as { id?: number; method: string; params: Record<string, unknown> };
      methods.push(request.method);
      if (request.method === "initialized") return;
      const result =
        request.method === "thread/read"
          ? { thread: { id: thread, name: "检查连接", cwd: "/work/tmp" } }
          : {};
      socket.send(JSON.stringify({ id: request.id, result }));
    });
  });
  http.listen(0, "127.0.0.1");
  await once(http, "listening");
  const address = http.address();
  assert(address && typeof address === "object");
  try {
    const source = await new CodexSourceReader(`ws://127.0.0.1:${address.port}`, "").source(thread);
    assert.deepEqual(source, { title: "检查连接", cwd: "/work/tmp" });
    assert.deepEqual(methods, ["initialize", "initialized", "thread/read"]);
  } finally {
    websocket.close();
    http.close();
  }
});

test("Python request center routes two Bridges independently", { skip: !process.env.REQUEST_ME_TEST_PYTHON }, async () => {
  const child = spawn(process.env.REQUEST_ME_TEST_PYTHON!, ["-m", "tests.http_fixture"], {
    cwd: process.cwd(),
    stdio: ["ignore", "pipe", "inherit"],
    windowsHide: true,
  });
  const lines = createInterface({ input: child.stdout! });
  const portLine = await Promise.race([
    once(lines, "line").then(([line]) => String(line)),
    new Promise<never>((_, reject) => setTimeout(() => reject(new Error("fixture startup timeout")), 10_000)),
  ]);
  const port = Number(portLine);
  assert(Number.isInteger(port) && port > 0);
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    for (let attempt = 0; attempt < 100; attempt += 1) {
      try {
        const response = await fetch(`${baseUrl}/openapi.json`);
        if (response.ok) break;
      } catch {
        if (attempt === 99) throw new Error("fixture startup timeout");
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    const clients = [new RequestMeClient(baseUrl, "token-one"), new RequestMeClient(baseUrl, "token-two")];
    const threads = [thread, "01a07bde-f801-7992-bb5d-b80b58adac30"];
    for (let index = 0; index < clients.length; index += 1) {
      await clients[index]!.send(
        {
          id: `q${index}`,
          thread_id: threads[index]!,
          markdown: "工作已完成一部分，请补充信息。",
          source: {},
        },
        true,
      );
    }
    await assert.rejects(clients[1]!.close("q0", threads[0]!));
    for (const index of [1, 0]) {
      const response = await fetch(`${baseUrl}/test/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bridge: ["one", "two"][index], text: `/respond q${index} 人工回答${index}` }),
      });
      assert.equal(response.status, 200);
    }
    for (let index = 0; index < clients.length; index += 1) {
      const delivered: Answer[] = [];
      const worker = new BridgeWorker(clients[index]!, {
        async deliver(answer) {
          delivered.push(answer);
          return { status: "accepted" };
        },
      });
      await worker.step();
      assert.equal(delivered.length, 1);
      assert.equal(delivered[0]?.thread_id, threads[index]);
      assert.equal(delivered[0]?.text, `人工回答${index}`);
    }
  } finally {
    lines.close();
    child.kill();
    await once(child, "exit");
  }
});
