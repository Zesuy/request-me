import type { RequestMeClient } from "./client.js";
import type { Answer, Receipt } from "./types.js";

export interface Dispatcher {
  deliver(answer: Answer, signal?: AbortSignal): Promise<Receipt>;
}

export class BridgeWorker {
  private readonly seen = new Map<string, Receipt>();
  private readonly awaiting = new Map<string, Receipt>();

  constructor(
    private readonly api: Pick<RequestMeClient, "answers" | "receipt">,
    private readonly dispatcher: Dispatcher,
  ) {}

  async step(signal?: AbortSignal): Promise<void> {
    await this.flush(signal);
    const answers = await this.api.answers(signal);
    for (const answer of answers) {
      if (!answer.id || !answer.request_id) throw new Error("server returned an answer without an identity");
      let receipt = this.seen.get(answer.id);
      if (!receipt) {
        receipt = await this.dispatcher.deliver(answer, signal);
        this.seen.set(answer.id, receipt);
      }
      this.awaiting.set(answer.id, receipt);
    }
    await this.flush(signal);
  }

  async run(signal?: AbortSignal): Promise<void> {
    let delay = 1_000;
    while (!signal?.aborted) {
      try {
        await this.step(signal);
        delay = 1_000;
      } catch (error) {
        if (signal?.aborted) break;
        console.error(`bridge cycle failed: ${messageOf(error)}`);
        await wait(delay, signal);
        delay = Math.min(delay * 2, 30_000);
      }
    }
  }

  private async flush(signal?: AbortSignal): Promise<void> {
    for (const [id, receipt] of this.awaiting) {
      await this.api.receipt(id, receipt, signal);
      this.awaiting.delete(id);
    }
  }
}

function wait(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", finish);
      resolve();
    };
    const timer = setTimeout(finish, milliseconds);
    signal?.addEventListener("abort", finish, { once: true });
    if (signal?.aborted) finish();
  });
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
