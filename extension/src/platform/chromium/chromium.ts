// Chromium adapter (PROMPT §3): tabs, storage, sidePanel live here.

import type { BrowserPlatform, BrowserTab } from "../platform";

declare const chrome: any;

export class ChromiumPlatform implements BrowserPlatform {
  readonly name = "chromium" as const;

  async getActiveTab(): Promise<BrowserTab> {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const t = tabs && tabs[0];
    return { id: t?.id ?? null, url: t?.url ?? "", title: t?.title ?? "" };
  }

  async storageGet<T>(key: string, fallback: T): Promise<T> {
    const obj = await chrome.storage.local.get(key);
    return (obj?.[key] as T) ?? fallback;
  }

  async storageSet<T>(key: string, value: T): Promise<void> {
    await chrome.storage.local.set({ [key]: value });
  }

  async ensureHostAccess(): Promise<boolean> {
    try {
      const req = { origins: ["<all_urls>"] };
      if (await chrome.permissions.contains(req)) return true;
      return await chrome.permissions.request(req);
    } catch {
      // permissions API not available: rely on manifest host_permissions.
      return true;
    }
  }
}
