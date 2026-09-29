import type { AgentStatus } from "../agent/loop";

type Status = AgentStatus | "idle";

export interface ActivityLine {
  key: string;
  kind: string;
  text: string;
  verified?: boolean;
}

export function StatusDot({ status }: { status: Status }) {
  return <span className={`status-dot ${status}`} title={status} />;
}

const STATUS_LABEL: Record<string, string> = {
  idle: "Ready",
  running: "Running",
  thinking: "Thinking",
  acting: "Acting",
  waiting: "Waiting",
  confirming: "Needs confirmation",
  success: "Done",
  blocked: "Blocked",
  error: "Error",
  stopped: "Stopped",
};

export function StatusLabel({ status }: { status: Status }) {
  return <span className="muted">{STATUS_LABEL[status] ?? status}</span>;
}

export function ActivityFeed({ lines }: { lines: ActivityLine[] }) {
  return (
    <div className="activity">
      {lines.length === 0 && (
        <div className="line"><span className="mark">·</span>No activity yet.</div>
      )}
      {lines.map((l) => {
        const cls = l.verified === true ? "ok" : l.kind === "completed" ? "warn" : "";
        const mark = l.verified === true ? "✓" : l.kind === "action" ? "→" : "•";
        return (
          <div className={`line ${cls}`} key={l.key}>
            <span className="mark">{mark}</span>
            <span>{l.text}</span>
          </div>
        );
      })}
    </div>
  );
}
