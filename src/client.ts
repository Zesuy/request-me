import type { Answer, Message, Receipt, Sent } from "./types.js";

const MAX_RESPONSE_BYTES = 1024 * 1024;

export class RequestMeClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
  ) {}

  async send(message: Message, human: boolean, signal?: AbortSignal): Promise<Sent> {
    const sent = await this.call<Sent>(
      "POST",
      human ? "/v1/requests" : "/v1/notifications",
      message,
      signal,
    );
    if (sent.id !== message.id || sent.status !== "sent") {
      throw new Error("server did not confirm message sent");
    }
    return sent;
  }

  async close(id: string, thread: string, signal?: AbortSignal): Promise<void> {
    await this.call("POST", `/v1/requests/${encodeURIComponent(id)}/close`, { thread_id: thread }, signal);
  }

  async answers(signal?: AbortSignal): Promise<Answer[]> {
    const result = await this.call<{ answers: Answer[] }>("GET", "/v1/answers?wait=25", undefined, signal);
    return result.answers;
  }

  async receipt(id: string, receipt: Receipt, signal?: AbortSignal): Promise<void> {
    await this.call("POST", `/v1/answers/${encodeURIComponent(id)}/receipt`, receipt, signal);
  }

  private async call<T = void>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const timeout = AbortSignal.timeout(40_000);
    const combinedSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        redirect: "manual",
        headers: {
          Authorization: `Bearer ${this.token}`,
          "Content-Type": "application/json",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: combinedSignal,
      });
    } catch (error) {
      const name = error instanceof Error ? error.name : "unknown";
      throw new Error(`request-me transport failed (${name})`);
    }
    if (!response.ok) {
      await response.body?.cancel();
      throw new Error(`request-me returned HTTP ${response.status}`);
    }
    if (response.status === 204) return undefined as T;
    const contentLength = Number(response.headers.get("content-length"));
    if (Number.isFinite(contentLength) && contentLength > MAX_RESPONSE_BYTES) {
      await response.body?.cancel();
      throw new Error("request-me response is too large");
    }
    const text = await response.text();
    if (Buffer.byteLength(text) > MAX_RESPONSE_BYTES) throw new Error("request-me response is too large");
    if (!text) return undefined as T;
    return JSON.parse(text) as T;
  }
}
