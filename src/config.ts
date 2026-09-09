import { readFile } from "node:fs/promises";
import { hostname } from "node:os";

export interface Config {
  server_url: string;
  token_env: string;
  host_label: string;
  codex_binary: string;
  app_server_url: string;
  app_server_token_env?: string;
}

export async function loadConfig(path: string): Promise<Config> {
  const parsed: unknown = JSON.parse(await readFile(path, "utf8"));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("configuration must be a JSON object");
  }
  const raw = parsed as Record<string, unknown>;
  const serverUrl = stringValue(raw.server_url);
  let url: URL;
  try {
    url = new URL(serverUrl);
  } catch {
    throw new Error("server_url must be an HTTP(S) origin without credentials, query or fragment");
  }
  if (
    !["http:", "https:"].includes(url.protocol) ||
    !url.host ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.pathname !== "/" && url.pathname !== "")
  ) {
    throw new Error("server_url must be an HTTP(S) origin without credentials, path, query or fragment");
  }
  const tokenEnv = stringValue(raw.token_env);
  if (!tokenEnv || !process.env[tokenEnv]) {
    throw new Error("token_env must name a nonempty environment variable");
  }
  return {
    server_url: serverUrl.replace(/\/+$/, ""),
    token_env: tokenEnv,
    host_label: stringValue(raw.host_label) || hostname(),
    codex_binary: stringValue(raw.codex_binary) || "codex",
    app_server_url: stringValue(raw.app_server_url),
    app_server_token_env: stringValue(raw.app_server_token_env) || undefined,
  };
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function parseCommandLine(argv: string[]): { configPath: string; once: boolean } {
  let configPath = "bridge.local.json";
  let once = false;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--once" || argument === "-once") {
      once = true;
    } else if (argument === "--config" || argument === "-config") {
      const value = argv[index + 1];
      if (!value) throw new Error(`${argument} requires a path`);
      configPath = value;
      index += 1;
    } else {
      throw new Error(`unknown argument: ${argument}`);
    }
  }
  return { configPath, once };
}
