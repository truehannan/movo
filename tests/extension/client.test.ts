import { describe, expect, it, vi } from "vitest";

import { AgentClient, waitForBackend } from "../../extension/src/api/client";
import type { Health, StartTaskResponse } from "../../extension/src/shared/protocol";

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const body = handler(url, init);
    return {
      ok: true,
      status: 200,
      json: async () => body,
    } as Response;
  });
}

describe("AgentClient", () => {
  it("sends the token header on start", async () => {
    let seenToken = "";
    globalThis.fetch = mockFetch((url, init) => {
      if (url.endsWith("/tasks")) {
        seenToken = (init?.headers as Record<string, string>)["x-agent-token"];
        return { task: { id: "t1", goal: "g", status: "running", step_count: 0, url: "", title: "" }, ws: "/events/t1" } as StartTaskResponse;
      }
      return {};
    }) as unknown as typeof fetch;

    const client = new AgentClient({ baseUrl: "http://127.0.0.1:8766", token: "secret" });
    const res = await client.startTask({ goal: "do it", context: { tab_id: 1, url: "u", title: "t" } });
    expect(seenToken).toBe("secret");
    expect(res.ws).toBe("/events/t1");
  });

  it("waitForBackend returns true when health is ok", async () => {
    globalThis.fetch = mockFetch(() => ({ status: "ok" }) as Health) as unknown as typeof fetch;
    expect(await waitForBackend("http://127.0.0.1:8766", 1)).toBe(true);
  });

  it("waitForBackend returns false when unreachable", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    expect(await waitForBackend("http://127.0.0.1:8766", 2)).toBe(false);
  });
});
