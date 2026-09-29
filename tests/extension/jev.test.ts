import { describe, expect, it, vi } from "vitest";

import { DecisionEngine, type Observation } from "../../extension/src/agent/engine";
import { JevClient } from "../../extension/src/agent/jev";

function mockJev(answers: Record<string, unknown>) {
  globalThis.fetch = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ model: "jev-1.13.0", answers, usage: { input_tokens: 42 } }),
    text: async () => "",
  })) as unknown as typeof fetch;
}

const OBS: Observation = {
  url: "https://ex.com",
  title: "Example",
  fingerprint: "fp",
  elements: [
    { index: 0, role: "textbox", name: "Search", value: "", editable: true, checked: null, disabled: false, can_click: false, can_type: true, can_select: false, options: [] },
    { index: 1, role: "button", name: "Search", value: null, editable: false, checked: null, disabled: false, can_click: true, can_type: false, can_select: false, options: [] },
  ],
};

describe("JevClient", () => {
  it("posts to /v1/systemone with the bearer key", async () => {
    let seen: { url?: string; auth?: string; body?: string } = {};
    globalThis.fetch = vi.fn(async (url: string, init?: RequestInit) => {
      seen = { url, auth: (init?.headers as Record<string, string>)?.authorization, body: init?.body as string };
      return { ok: true, status: 200, json: async () => ({ model: "m", answers: {} }), text: async () => "" } as Response;
    }) as unknown as typeof fetch;
    const c = new JevClient({ apiKey: "sk-x", endpoint: "https://api.typesafe.ai", model: "jev-latest" });
    await c.systemOne("state", { q: { type: "noul", instructions: "?" } });
    expect(seen.url).toBe("https://api.typesafe.ai/v1/systemone");
    expect(seen.auth).toBe("Bearer sk-x");
    expect(seen.body).toContain('"model":"jev-latest"');
  });

  it("testConnection returns ok on success", async () => {
    mockJev({ ok: { type: "noul", noul: 0.5 } });
    const c = new JevClient({ apiKey: "sk", endpoint: "https://api.typesafe.ai", model: "jev-latest" });
    const r = await c.testConnection();
    expect(r.ok).toBe(true);
    expect(r.model).toBe("jev-1.13.0");
  });

  it("testConnection reports failure detail", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 401, text: async () => "bad key", json: async () => ({}) })) as unknown as typeof fetch;
    const c = new JevClient({ apiKey: "bad", endpoint: "https://api.typesafe.ai", model: "jev-latest" });
    const r = await c.testConnection();
    expect(r.ok).toBe(false);
    expect(r.detail).toContain("401");
  });
});

describe("DecisionEngine", () => {
  it("parses CLICK with a resolved target", async () => {
    mockJev({
      operation: { type: "choice", choice: "CLICK", confidence: 0.9, probabilities: { CLICK: 0.9 } },
      target_click: { type: "choice", choice: "1", confidence: 0.9, probabilities: { "1": 0.9 } },
    });
    const eng = new DecisionEngine(new JevClient({ apiKey: "k", endpoint: "https://api.typesafe.ai", model: "jev-latest" }));
    const d = await eng.decide("go", OBS, []);
    expect(d.operation).toBe("CLICK");
    expect(d.targetIndex).toBe(1);
  });

  it("drops an out-of-range target", async () => {
    mockJev({
      operation: { type: "choice", choice: "CLICK", confidence: 0.9, probabilities: {} },
      target_click: { type: "choice", choice: "99", confidence: 0.9, probabilities: {} },
    });
    const eng = new DecisionEngine(new JevClient({ apiKey: "k", endpoint: "https://api.typesafe.ai", model: "jev-latest" }));
    const d = await eng.decide("go", OBS, []);
    expect(d.operation).toBe("CLICK");
    expect(d.targetIndex).toBeNull();
  });

  it("falls back to BLOCKED on invalid operation", async () => {
    mockJev({ operation: { type: "choice", choice: "FLY", confidence: 0.5, probabilities: {} } });
    const eng = new DecisionEngine(new JevClient({ apiKey: "k", endpoint: "https://api.typesafe.ai", model: "jev-latest" }));
    const d = await eng.decide("go", OBS, []);
    expect(d.operation).toBe("BLOCKED");
  });
});
