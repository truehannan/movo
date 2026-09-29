// Agent session state (PROMPT §9). Holds the current task, status, and the
// activity feed; wires the API client + WebSocket. No chain-of-thought is ever
// stored — only concise execution events.

import { useCallback, useRef, useState } from "react";

import { AgentClient } from "../api/client";
import type { ServerEvent, TaskStatus } from "../shared/protocol";
import type { BrowserPlatform } from "../platform/platform";

export interface ActivityLine {
  key: string;
  kind: ServerEvent["type"];
  text: string;
  verified?: boolean;
}

export interface SessionState {
  status: TaskStatus | "disconnected";
  taskId: string | null;
  activity: ActivityLine[];
  confirming: { operation?: string; target?: string; reason: string } | null;
}

export function useAgentSession(client: AgentClient | null, platform: BrowserPlatform) {
  const [state, setState] = useState<SessionState>({
    status: "idle",
    taskId: null,
    activity: [],
    confirming: null,
  });
  const closerRef = useRef<null | (() => void)>(null);
  const seq = useRef(0);

  const push = useCallback((line: Omit<ActivityLine, "key">) => {
    setState((s) => ({
      ...s,
      activity: [...s.activity, { ...line, key: `${seq.current++}` }].slice(-100),
    }));
  }, []);

  const onEvent = useCallback(
    (ev: ServerEvent) => {
      if (ev.status) setState((s) => ({ ...s, status: ev.status as TaskStatus }));
      if (ev.type === "agent.confirm") {
        setState((s) => ({
          ...s,
          confirming: { operation: ev.operation, target: ev.target, reason: ev.message },
        }));
      }
      if (ev.type === "agent.completed") {
        setState((s) => ({ ...s, status: (ev.outcome as TaskStatus) || s.status }));
      }
      if (ev.message) {
        push({ kind: ev.type, text: ev.message, verified: ev.verified });
      }
    },
    [push],
  );

  const run = useCallback(
    async (goal: string) => {
      if (!client) return;
      setState((s) => ({ ...s, activity: [], confirming: null, status: "running" }));
      const tab = await platform.getActiveTab();
      const res = await client.startTask({
        goal,
        context: { tab_id: tab.id, url: tab.url, title: tab.title },
      });
      setState((s) => ({ ...s, taskId: res.task.id }));
      closerRef.current?.();
      closerRef.current = client.streamEvents(res.ws, onEvent);
    },
    [client, platform, onEvent],
  );

  const control = useCallback(
    async (action: "stop" | "pause" | "resume") => {
      if (!client || !state.taskId) return;
      await client.control(state.taskId, action);
    },
    [client, state.taskId],
  );

  const confirm = useCallback(
    async (approved: boolean) => {
      if (!client || !state.taskId) return;
      await client.confirm(state.taskId, approved);
      setState((s) => ({ ...s, confirming: null }));
    },
    [client, state.taskId],
  );

  return { state, run, control, confirm, setStatus: (st: SessionState["status"]) => setState((s) => ({ ...s, status: st })) };
}
