import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const dir = resolve(__dirname, "../../extension/manifest");
const load = (n: string) => JSON.parse(readFileSync(resolve(dir, n), "utf8"));

describe("manifests", () => {
  it("chromium uses MV3 side panel, not a popup", () => {
    const m = load("chromium.json");
    expect(m.manifest_version).toBe(3);
    expect(m.side_panel).toBeDefined();
    expect(JSON.stringify(m)).not.toContain("default_popup");
    expect(m.permissions).toContain("sidePanel");
    expect(m.permissions).toContain("scripting");
  });

  it("firefox uses MV3 sidebar_action and declares no data collection", () => {
    const m = load("firefox.json");
    expect(m.manifest_version).toBe(3);
    expect(m.sidebar_action).toBeDefined();
    expect(JSON.stringify(m)).not.toContain("sidePanel");
    const gecko = m.browser_specific_settings.gecko;
    expect(gecko.data_collection_permissions.required).toEqual(["none"]);
    expect(parseFloat(gecko.strict_min_version)).toBeGreaterThanOrEqual(140);
  });

  it("both share name and description", () => {
    const c = load("chromium.json");
    const f = load("firefox.json");
    expect(c.name).toBe(f.name);
    expect(c.description).toBe(f.description);
  });
});
