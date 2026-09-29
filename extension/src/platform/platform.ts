// Browser platform adapter (PROMPT §5). The shared UI depends only on this
// interface; Chromium/Firefox differences live in the two implementations, so
// there are no scattered `if (chrome)` checks in the app.

import { ChromiumPlatform } from "../platform/chromium/chromium";
import { FirefoxPlatform } from "../platform/firefox/firefox";

export interface BrowserTab {
  id: number | null;
  url: string;
  title: string;
}

export interface BrowserPlatform {
  readonly name: "chromium" | "firefox";
  /** Return the active tab's id/url/title. */
  getActiveTab(): Promise<BrowserTab>;
  /** Persist a small preference value. */
  storageGet<T>(key: string, fallback: T): Promise<T>;
  storageSet<T>(key: string, value: T): Promise<void>;
}

export function detectPlatform(): BrowserPlatform {
  const g = globalThis as unknown as {
    browser?: { sidebarAction?: unknown };
  };
  if (g.browser && g.browser.sidebarAction) {
    return new FirefoxPlatform();
  }
  return new ChromiumPlatform();
}
