import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { DecisionEngine } from "../agent/engine";
import { JevClient } from "../agent/jev";
import { AgentLoop, type ActivityEvent, type AgentStatus } from "../agent/loop";
import { PageDriver } from "../agent/pageDriver";
import { ActivityFeed, StatusDot, StatusLabel } from "../components/parts";
import { DEFAULT_SETTINGS, Settings, type JevSettings } from "../components/Settings";
import { detectPlatform } from "../platform/platform";

type Status = AgentStatus | "idle";

interface Line {
  key: string;
  kind: ActivityEvent["kind"];
  text: string;
  verified?: boolean;
}

export function App() {
  const platform = useMemo(() => detectPlatform(), []);
  const [settings, setSettings] = useState<JevSettings>(DEFAULT_SETTINGS);
  const [showSettings, setShowSettings] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [activity, setActivity] = useState<Line[]>([]);
  const [confirming, setConfirming] = useState<{ text: string } | null>(null);
  const [goal, setGoal] = useState("");
  const loopRef = useRef<AgentLoop | null>(null);
  const confirmResolve = useRef<((v: boolean) => void) | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    (async () => {
      const saved = await platform.storageGet<JevSettings | null>("jev", null);
      if (saved && saved.apiKey) setSettings(saved);
      else setShowSettings(true);
    })();
  }, [platform]);

  // Focus the input as soon as the panel is interactive (fixes cursor focus).
  useEffect(() => {
    if (!showSettings) inputRef.current?.focus();
  }, [showSettings]);

  const push = useCallback((e: ActivityEvent) => {
    if (e.status) setStatus(e.status);
    if (e.kind === "confirm") setConfirming({ text: e.text });
    if (e.text) setActivity((a) => [...a, { key: `${seq.current++}`, kind: e.kind, text: e.text, verified: e.verified }].slice(-100));
  }, []);

  const saveSettings = useCallback(
    async (s: JevSettings) => {
      setSettings(s);
      await platform.storageSet("jev", s);
      setShowSettings(false);
    },
    [platform],
  );

  const run = useCallback(async () => {
    const g = goal.trim();
    if (!g || !settings.apiKey) return;
    setActivity([]);
    setConfirming(null);
    setStatus("running");
    // Ensure the extension can operate pages (grants host access on first run).
    const granted = await platform.ensureHostAccess();
    if (!granted) {
      push({ kind: "message", status: "error", text: "Host permission denied. Allow access to run on this page." });
      setStatus("error");
      return;
    }
    const tab = await platform.getActiveTab();
    if (tab.id == null) {
      push({ kind: "message", status: "error", text: "No active tab to control." });
      return;
    }
    const engine = new DecisionEngine(new JevClient(settings));
    const driver = new PageDriver(tab.id);
    const loop = new AgentLoop(engine, driver);
    loopRef.current = loop;
    await loop.run({
      goal: g,
      onEvent: push,
      confirm: (desc) =>
        new Promise<boolean>((resolve) => {
          confirmResolve.current = resolve;
          setConfirming({ text: desc });
        }),
    });
  }, [goal, settings, platform, push]);

  const stop = useCallback(() => {
    loopRef.current?.stop();
    setStatus("stopped");
  }, []);

  const answerConfirm = useCallback((approved: boolean) => {
    confirmResolve.current?.(approved);
    confirmResolve.current = null;
    setConfirming(null);
  }, []);

  const running = ["running", "thinking", "acting", "waiting", "confirming"].includes(status);
  const connected = !!settings.apiKey;

  if (showSettings) {
    return (
      <div className="app">
        <Settings initial={settings} onSave={saveSettings} onBack={() => setShowSettings(connected ? false : false)} />
      </div>
    );
  }

  return (
    <div className="app">
      <div className="titlebar">
        <StatusDot status={status} />
        <span className="name">Jev Agent</span>
        <span className="spacer" />
        <StatusLabel status={status} />
        <button className="icon-btn" onClick={() => setShowSettings(true)} title="Settings">⚙</button>
      </div>

      {!connected && (
        <div className="banner">
          Add your Jev API key to start.
          <div style={{ marginTop: 8 }}>
            <button className="ghost" onClick={() => setShowSettings(true)}>Open settings</button>
          </div>
        </div>
      )}

      <div className="section">
        <div className="label">Current task</div>
        <div className="task-goal">{running ? goal : "No task running"}</div>
      </div>

      <div className="label" style={{ padding: "8px 12px 0", color: "var(--faint)", fontSize: 11 }}>Agent activity</div>
      <ActivityFeed lines={activity} />

      {confirming && (
        <div className="confirm">
          <div className="q">{confirming.text}</div>
          <div className="row">
            <button className="primary" onClick={() => answerConfirm(true)}>Approve</button>
            <button className="ghost danger" onClick={() => answerConfirm(false)}>Deny</button>
          </div>
        </div>
      )}

      <div className="composer">
        <textarea
          ref={inputRef}
          placeholder="What should I do on this page?"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !running) {
              e.preventDefault();
              void run();
            }
          }}
          disabled={running}
        />
        <div className="row">
          <button className="primary" disabled={running || !connected || !goal.trim()} onClick={() => void run()}>
            Run →
          </button>
          <span className="spacer" />
          {running && <button className="ghost danger" onClick={stop}>Stop</button>}
        </div>
      </div>
    </div>
  );
}
