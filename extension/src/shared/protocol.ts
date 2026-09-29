// Shared protocol types — mirror of agent/api/protocol.py (PROMPT §24).
// Kept in one place so the extension never re-declares message schemas ad hoc.

export interface BrowserContextIn {
  tab_id: number | null;
  url: string;
  title: string;
}

export interface StartTaskRequest {
  goal: string;
  context: BrowserContextIn;
  max_steps?: number;
  max_runtime_ms?: number;
  max_failures?: number;
}

export interface TaskInfo {
  id: string;
  goal: string;
  status: TaskStatus;
  step_count: number;
  url: string;
  title: string;
}

export interface StartTaskResponse {
  task: TaskInfo;
  ws: string;
}

export interface Health {
  status: "ok";
  version: string;
  has_jev_key: boolean;
  has_text_model: boolean;
}

export type TaskStatus =
  | "idle"
  | "running"
  | "thinking"
  | "acting"
  | "waiting"
  | "paused"
  | "confirming"
  | "success"
  | "blocked"
  | "error"
  | "stopped";

export type ServerEventType =
  | "agent.status"
  | "agent.observed"
  | "agent.action"
  | "agent.acted"
  | "agent.message"
  | "agent.confirm"
  | "agent.verified"
  | "agent.error"
  | "agent.completed";

export interface ServerEvent {
  type: ServerEventType;
  task_id: string;
  step: number;
  message: string;
  status?: TaskStatus;
  operation?: string;
  target?: string;
  verified?: boolean;
  outcome?: string;
  ts: number;
}
