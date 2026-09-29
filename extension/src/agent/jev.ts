// In-extension Jev client — calls TypeSafe's official System-One wire API
// directly (POST /v1/systemone), with the API key stored in extension settings.
// No local backend. The request/response shapes match api.typesafe.ai v0.2.0.

export const DEFAULT_JEV_ENDPOINT = "https://api.typesafe.ai";

export type QuestionType = "choice" | "noul" | "score";

export interface ChoiceQuestion {
  type: "choice";
  instructions: string;
  criteria: Record<string, string | null>;
}
export interface NoulQuestion {
  type: "noul";
  instructions: string;
  criteria?: { true?: string; false?: string };
}
export type Question = ChoiceQuestion | NoulQuestion;

export interface ChoiceAnswer {
  type: "choice";
  choice: string;
  confidence: number;
  probabilities: Record<string, number>;
}
export interface NoulAnswer {
  type: "noul";
  noul: number;
  confidence?: number;
}
export type Answer = ChoiceAnswer | NoulAnswer;

export interface SystemOneResponse {
  model: string;
  answers: Record<string, Answer>;
  usage?: { input_tokens?: number; output_tokens?: number };
}

export interface JevConfig {
  apiKey: string;
  endpoint: string; // e.g. https://api.typesafe.ai
  model: string; // e.g. jev-latest
}

export class JevClient {
  constructor(private cfg: JevConfig) {}

  private url(path: string): string {
    return `${this.cfg.endpoint.replace(/\/$/, "")}${path}`;
  }

  async systemOne(
    state: unknown,
    questions: Record<string, Question>,
    signal?: AbortSignal,
  ): Promise<SystemOneResponse> {
    const r = await fetch(this.url("/v1/systemone"), {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${this.cfg.apiKey}`,
      },
      body: JSON.stringify({ state, model: this.cfg.model, questions }),
      signal,
    });
    if (!r.ok) {
      const text = await r.text().catch(() => "");
      throw new Error(`Jev ${r.status}: ${text.slice(0, 200)}`);
    }
    return (await r.json()) as SystemOneResponse;
  }

  /** A tiny call to verify the key/endpoint work (Test Connection). */
  async testConnection(): Promise<{ ok: boolean; model?: string; detail?: string }> {
    try {
      const resp = await this.systemOne("connection check", {
        ok: { type: "noul", instructions: "This is a connection test" },
      });
      return { ok: true, model: resp.model };
    } catch (e) {
      return { ok: false, detail: e instanceof Error ? e.message : String(e) };
    }
  }
}
