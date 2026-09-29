import type { ActivityLine } from "../state/session";
import type { TaskStatus } from "../shared/protocol";

export function StatusDot({ status }: { status: TaskStatus | "disconnected" }) {
  return <span className={`status-dot ${status}`} title={status} />;
}

const STATUS_LABEL: Record<string, string> = {
  idle: "Ready",
  running: "Running",
  thinking: "Thinking",
  acting: "Acting",
  waiting: "Waiting",
  paused: "Paused",
  confirming: "Needs confirmation",
  success: "Done",
  blocked: "Blocked",
  error: "Error",
  stopped: "Stopped",
  disconnected: "Disconnected",
};

export function StatusLabel({ status }: { status: TaskStatus | "disconnected" }) {
  return <span className="muted">{STATUS_LABEL[status] ?? status}</span>;
}

export function ActivityFeed({ lines }: { lines: ActivityLine[] }) {
  return (
    <div className="activity">
      {lines.length === 0 && <div className="line"><span className="mark">·</span>No activity yet.</div>}
      {lines.map((l) => {
        const cls = l.verified === true ? "ok" : l.kind === "agent.error" ? "warn" : "";
        const mark = l.verified === true ? "✓" : l.kind === "agent.error" ? "!" : "•";
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
