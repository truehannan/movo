import { useCallback, useEffect, useMemo, useState } from "react";

import { AgentClient, waitForBackend } from "../api/client";
import { ActivityFeed, StatusDot, StatusLabel } from "../components/parts";
import { Settings, type Connection } from "../components/Settings";
import { detectPlatform } from "../platform/platform";
import { useAgentSession } from "../state/session";

const DEFAULT_CONN: Connection = { baseUrl: "http://127.0.0.1:8766", token: "" };

export function App() {
  const platform = useMemo(() => detectPlatform(), []);
  const [conn, setConn] = useState<Connection>(DEFAULT_CONN);
  const [showSettings, setShowSettings] = useState(false);
  const [connected, setConnected] = useState(false);
  const [goal, setGoal] = useState("");

  const client = useMemo(
    () => (conn.token ? new AgentClient({ baseUrl: conn.baseUrl, token: conn.token }) : null),
    [conn],
  );
  const session = useAgentSession(client, platform);

  // Load saved connection.
  useEffect(() => {
    (async () => {
      const saved = await platform.storageGet<Connection | null>("connection", null);
      if (saved) setConn(saved);
      else setShowSettings(true);
    })();
  }, [platform]);

  // Probe backend health with backoff.
  useEffect(() => {
    let active = true;
    if (!client) return;
    (async () => {
      const ok = await waitForBackend(conn.baseUrl);
      if (!active) return;
      setConnected(ok);
      if (!ok) session.setStatus("disconnected");
    })();
    return () => {
      active = false;
    };
  }, [client, conn.baseUrl]);

  const saveConn = useCallback(
    async (c: Connection) => {
      setConn(c);
      await platform.storageSet("connection", c);
      setShowSettings(false);
    },
    [platform],
  );

  const running = ["running", "thinking", "acting", "waiting", "confirming"].includes(session.state.status);

  if (showSettings) {
    return (
      <div className="app">
        <Settings initial={conn} onSave={saveConn} onBack={() => setShowSettings(false)} />
      </div>
    );
  }

  return (
    <div className="app">
      <div className="titlebar">
        <StatusDot status={session.state.status} />
        <span className="name">Jev Agent</span>
        <span className="spacer" />
        <StatusLabel status={connected ? session.state.status : "disconnected"} />
        <button className="icon-btn" onClick={() => setShowSettings(true)} title="Settings">⚙</button>
      </div>

      {!connected && (
        <div className="banner">
          Agent service unavailable. Start the local agent service and try again.
          <div style={{ marginTop: 8 }}>
            <button className="ghost" onClick={() => setShowSettings(true)}>Open settings</button>
          </div>
        </div>
      )}

      <div className="section">
        <div className="label">Current task</div>
        <div className="task-goal">{session.state.taskId ? goal || "—" : "No task running"}</div>
      </div>

      <div className="label" style={{ padding: "8px 12px 0", color: "var(--faint)", fontSize: 11 }}>
        Agent activity
      </div>
      <ActivityFeed lines={session.state.activity} />

      {session.state.confirming && (
        <div className="confirm">
          <div className="q">
            Confirm: {session.state.confirming.operation} {session.state.confirming.target ?? ""}
            <div className="muted">{session.state.confirming.reason}</div>
          </div>
          <div className="row">
            <button className="primary" onClick={() => session.confirm(true)}>Approve</button>
            <button className="ghost danger" onClick={() => session.confirm(false)}>Deny</button>
          </div>
        </div>
      )}

      <div className="composer">
        <textarea
          placeholder="What should I do on this page?"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          disabled={running || !connected}
        />
        <div className="row">
          <button
            className="primary"
            disabled={running || !connected || !goal.trim()}
            onClick={() => session.run(goal.trim())}
          >
            Run →
          </button>
          <span className="spacer" />
          {running && (
            <>
              <button className="ghost" onClick={() => session.control("pause")}>Pause</button>
              <button className="ghost danger" onClick={() => session.control("stop")}>Stop</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
