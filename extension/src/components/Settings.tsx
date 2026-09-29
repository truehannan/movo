import { useState } from "react";

import { DEFAULT_JEV_ENDPOINT, JevClient } from "../agent/jev";

export interface JevSettings {
  apiKey: string;
  endpoint: string;
  model: string;
}

export const DEFAULT_SETTINGS: JevSettings = {
  apiKey: "",
  endpoint: DEFAULT_JEV_ENDPOINT,
  model: "jev-latest",
};

export function Settings({
  initial,
  onSave,
  onBack,
}: {
  initial: JevSettings;
  onSave: (s: JevSettings) => void;
  onBack: () => void;
}) {
  const [apiKey, setApiKey] = useState(initial.apiKey);
  const [endpoint, setEndpoint] = useState(initial.endpoint || DEFAULT_JEV_ENDPOINT);
  const [model, setModel] = useState(initial.model || "jev-latest");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const current = (): JevSettings => ({ apiKey: apiKey.trim(), endpoint: endpoint.trim(), model: model.trim() });

  async function testConnection() {
    setTesting(true);
    setResult(null);
    const client = new JevClient(current());
    const r = await client.testConnection();
    setTesting(false);
    setResult({ ok: r.ok, text: r.ok ? `Connected · ${r.model ?? model}` : `Failed: ${r.detail ?? "error"}` });
  }

  return (
    <div className="section">
      <div className="titlebar" style={{ padding: 0, border: "none", marginBottom: 12 }}>
        <button className="icon-btn" onClick={onBack}>‹ Back</button>
        <div className="name">Settings</div>
      </div>

      <div className="field">
        <label>Jev API key</label>
        <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" placeholder="paste your TypeSafe / Jev key" />
      </div>
      <div className="field">
        <label>Endpoint</label>
        <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder={DEFAULT_JEV_ENDPOINT} />
      </div>
      <div className="field">
        <label>Model</label>
        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="jev-latest" />
      </div>

      {result && (
        <div className="banner" style={{ margin: "4px 0 10px", borderColor: result.ok ? "var(--ok)" : "var(--err)", color: result.ok ? "var(--ok)" : "var(--err)" }}>
          {result.text}
        </div>
      )}

      <div className="row">
        <button className="ghost" disabled={testing || !apiKey.trim()} onClick={testConnection}>
          {testing ? "Testing…" : "Test connection"}
        </button>
        <span className="spacer" />
        <button className="primary" disabled={!apiKey.trim()} onClick={() => onSave(current())}>
          Save
        </button>
      </div>
    </div>
  );
}
