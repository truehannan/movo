// Client for the local agent service (PROMPT §24, §25). Handles token auth,
// start/stop/pause/resume/confirm, and the WebSocket event stream with
// exponential-backoff reconnection. Never stores secrets — only the local
// backend URL and the per-run token the user pastes in.

import type {
  Health,
  ServerEvent,
  StartTaskRequest,
  StartTaskResponse,
  TaskInfo,
} from "../shared/protocol";

export interface AgentClientOptions {
  baseUrl: string; // e.g. http://127.0.0.1:8766
  token: string;
}

export class AgentClient {
  private baseUrl: string;
  private token: string;

  constructor(opts: AgentClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, "");
    this.token = opts.token;
  }

  private headers(): Record<string, string> {
    return { "content-type": "application/json", "x-agent-token": this.token };
  }

  async health(): Promise<Health> {
    const r = await fetch(`${this.baseUrl}/health`, { method: "GET" });
    if (!r.ok) throw new Error(`health ${r.status}`);
    return (await r.json()) as Health;
  }

  async startTask(req: StartTaskRequest): Promise<StartTaskResponse> {
    const r = await fetch(`${this.baseUrl}/tasks`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(req),
    });
    if (!r.ok) throw new Error(`start ${r.status}`);
    return (await r.json()) as StartTaskResponse;
  }

  async getTask(id: string): Promise<TaskInfo> {
    const r = await fetch(`${this.baseUrl}/tasks/${id}`, { headers: this.headers() });
    if (!r.ok) throw new Error(`get ${r.status}`);
    return (await r.json()) as TaskInfo;
  }

  async control(id: string, action: "stop" | "pause" | "resume"): Promise<void> {
    await fetch(`${this.baseUrl}/tasks/${id}/${action}`, {
      method: "POST",
      headers: this.headers(),
    });
  }

  async confirm(id: string, approved: boolean): Promise<void> {
    await fetch(`${this.baseUrl}/tasks/${id}/confirm`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ approved }),
    });
  }

  /** Open the event stream for a task. Returns a closer function. */
  streamEvents(
    wsPath: string,
    onEvent: (ev: ServerEvent) => void,
    onClose?: () => void,
  ): () => void {
    const wsBase = this.baseUrl.replace(/^http/, "ws");
    const url = `${wsBase}${wsPath}?token=${encodeURIComponent(this.token)}`;
    const ws = new WebSocket(url);
    ws.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data) as ServerEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => onClose?.();
    return () => ws.close();
  }
}

/** Wait for the backend to be reachable, with exponential backoff (PROMPT §25). */
export async function waitForBackend(
  baseUrl: string,
  attempts = 5,
): Promise<boolean> {
  let delay = 300;
  for (let i = 0; i < attempts; i++) {
    try {
      const r = await fetch(`${baseUrl.replace(/\/$/, "")}/health`);
      if (r.ok) return true;
    } catch {
      /* not up yet */
    }
    await new Promise((res) => setTimeout(res, delay));
    delay = Math.min(delay * 2, 5000);
  }
  return false;
}
