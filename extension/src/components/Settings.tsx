import { useState } from "react";

export interface Connection {
  baseUrl: string;
  token: string;
}

export function Settings({
  initial,
  onSave,
  onBack,
}: {
  initial: Connection;
  onSave: (c: Connection) => void;
  onBack: () => void;
}) {
  const [baseUrl, setBaseUrl] = useState(initial.baseUrl);
  const [token, setToken] = useState(initial.token);
  return (
    <div className="section">
      <div className="titlebar" style={{ padding: 0, border: "none", marginBottom: 12 }}>
        <button className="icon-btn" onClick={onBack}>‹ Back</button>
        <div className="name">Settings</div>
      </div>
      <div className="field">
        <label>Local agent URL</label>
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8766" />
      </div>
      <div className="field">
        <label>Request token (printed by the agent service)</label>
        <input value={token} onChange={(e) => setToken(e.target.value)} type="password" placeholder="paste token" />
      </div>
      <button className="primary" onClick={() => onSave({ baseUrl: baseUrl.trim(), token: token.trim() })}>
        Save & connect
      </button>
    </div>
  );
}
